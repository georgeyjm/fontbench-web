import re
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import pyvips
from glyphsLib import GSFont
from fontbench import FontProxy, metrics
from sqlalchemy.orm import Session

from app.config import DATA_DIR, CHARSET_FILES
from app.db import SessionLocal
from app.models import Job, Font, FontMetric, Metric, Typeface


# Regex for matching Chinese characters
CHINESE_RE = re.compile(r'[⺀-⺙⺛-⻳⼀-⿕々〇〡-〩〸-〺〻㐀-䶵一-鿃豈-鶴侮-頻並-龎]', re.UNICODE)


@lru_cache(maxsize=32)
def get_allowed_chars(charset: str) -> frozenset[str]:
    """Get allowed characters for a charset (cached)."""
    if charset == 'chinese':
        return frozenset()  # Empty set means use regex
    return frozenset(CHARSET_FILES[charset].read_text(encoding='utf-8').splitlines())


@lru_cache(maxsize=128)
def load_grayscale_jsonl_cached(jsonl_file: str, charset: Literal['3500', '7000', 'chinese'] = '3500', sort: bool = True) -> tuple:
    """
    Process a JSONL file and return grayscale data (cached).
    Returns a tuple for hashability.
    """
    allowed_chars = get_allowed_chars(charset)
    use_regex = charset == 'chinese'

    data = []
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            line_data = json.loads(line)
            char = line_data['string']
            if not char:
                continue

            # Filter by charset
            if use_regex:
                if not CHINESE_RE.match(char):
                    continue
            else:
                if char not in allowed_chars:
                    continue

            grayscales = line_data.get('grayscale', {})
            for master_name, value in grayscales.items():
                data.append({
                    'string': char,
                    'master': master_name,
                    'grayscale': value,
                })

    # Sort by grayscale if requested
    if sort:
        data.sort(key=lambda x: x['grayscale'])

    return tuple(data)


def load_grayscale_jsonl(jsonl_file: str, charset: Literal['3500', '7000', 'chinese'] = '3500', sort: bool = True) -> pd.DataFrame:
    """
    Process a JSONL file and return a DataFrame of grayscale values.
    Uses caching for performance.
    """
    data = load_grayscale_jsonl_cached(jsonl_file, charset, sort)
    return pd.DataFrame(data)


def analyze_glyphs_file(file_path: Path) -> dict[str, Any]:
    """
    Analyze a .glyphs file and return structured data for visualization.

    Args:
        file_path: Path to the .glyphs or .glyphx file

    Returns:
        Dictionary containing analysis results
    """
    font = GSFont(str(file_path))

    # Basic font info
    font_info = {
        "family_name": font.familyName,
        "designer": font.designer,
        "copyright": font.copyright,
        "units_per_em": font.upm,
        "version_major": font.versionMajor,
        "version_minor": font.versionMinor,
    }

    # Masters info
    masters = []
    for master in font.masters:
        masters.append(
            {
                "id": master.id,
                "name": master.name,
                "weight_value": master.weightValue if hasattr(master, "weightValue") else None,
                "width_value": master.widthValue if hasattr(master, "widthValue") else None,
                "custom_value": master.customValue if hasattr(master, "customValue") else None,
                "ascender": master.ascender,
                "descender": master.descender,
                "cap_height": master.capHeight,
                "x_height": master.xHeight,
            }
        )

    # Glyph statistics
    glyph_count = len(font.glyphs)
    glyph_names = [g.name for g in font.glyphs]

    # Analyze glyph metrics (for the first master)
    widths = []
    node_counts = []
    component_counts = []

    for glyph in font.glyphs:
        if glyph.layers:
            layer = glyph.layers[0]
            widths.append(layer.width)

            # Count nodes across all paths
            total_nodes = sum(len(path.nodes) for path in layer.paths)
            node_counts.append(total_nodes)

            # Count components
            component_counts.append(len(layer.components))

    # Calculate statistics
    widths_array = np.array(widths)
    nodes_array = np.array(node_counts)

    stats = {
        "width": {
            "min": float(np.min(widths_array)) if len(widths_array) > 0 else 0,
            "max": float(np.max(widths_array)) if len(widths_array) > 0 else 0,
            "mean": float(np.mean(widths_array)) if len(widths_array) > 0 else 0,
            "std": float(np.std(widths_array)) if len(widths_array) > 0 else 0,
        },
        "nodes": {
            "min": int(np.min(nodes_array)) if len(nodes_array) > 0 else 0,
            "max": int(np.max(nodes_array)) if len(nodes_array) > 0 else 0,
            "mean": float(np.mean(nodes_array)) if len(nodes_array) > 0 else 0,
            "total": int(np.sum(nodes_array)) if len(nodes_array) > 0 else 0,
        },
    }

    # Width distribution for histogram
    width_histogram = create_histogram(widths, bins=20, label="Width")

    # Node count distribution
    node_histogram = create_histogram(node_counts, bins=20, label="Node Count")

    return {
        "font_info": font_info,
        "masters": masters,
        "glyph_count": glyph_count,
        "glyph_names": glyph_names[:100],  # Limit for response size
        "statistics": stats,
        "charts": {
            "width_distribution": width_histogram,
            "node_distribution": node_histogram,
        },
        "raw_data": {
            "widths": widths,
            "node_counts": node_counts,
            "component_counts": component_counts,
        },
    }


def create_histogram(
    data: list[float | int], bins: int = 20, label: str = "Value"
) -> dict[str, Any]:
    """Create histogram data for Plotly."""
    if not data:
        return {"x": [], "type": "histogram", "name": label}

    return {
        "x": data,
        "type": "histogram",
        "nbinsx": bins,
        "name": label,
    }


def process_metrics_job(job_id: int, filepath: Path, metric_names: list[str]):
    '''
    Background task to process a font file.
    '''
    db: Session = SessionLocal()

    # Data Validation (not really necessary)
    job = db.query(Job).get(job_id)
    if not job:
        raise ValueError(f'Job {job_id} not found')
    if not filepath.exists():
        raise ValueError(f'File {filepath} not found')

    metrics_list = []
    for metric_name in metric_names:
        metric_obj = db.query(Metric).filter(Metric.name == metric_name).first()
        if not metric_obj:
            raise ValueError(f'Metric {metric_name} not found')
        metrics_list.append(metric_obj)

    job.status = 'processing'
    job.started_at = datetime.now()
    db.commit()

    try:
        if filepath.suffix.lower() in ('.ttf', '.otf'):
            _process_opentype_file(db, job, filepath, metrics_list)

        elif filepath.suffix.lower() in ('.glyphs',):
            _process_glyphs_file(db, job, filepath, metrics_list)
        
        else:
            raise ValueError(f'Unsupported file type: {filepath.suffix}')
        
        job.status = 'completed'
        job.progress = 100
        job.current_metric = None
        job.completed_at = datetime.now()
        db.commit()
        
    except Exception as e:
        db.rollback()
        job.status = 'failed'
        job.error = str(e)
        job.completed_at = datetime.now()
        db.commit()

    finally:
        db.close()
        # Clean up upload file
        # filepath.unlink(missing_ok=True)


def _process_opentype_file(db, job: Job, filepath: Path, metrics_list: list[Metric]):
    try:
        font = FontProxy(filepath)
    except Exception as e:
        job.status = 'failed'
        job.error = str(e)
        job.completed_at = datetime.now()
        db.commit()
        raise ValueError(f'Failed to load font: {e}')

    # Fetch and update font information
    typeface = db.query(Typeface).filter(Typeface.name == font.family_name).first()
    if not typeface:
        typeface = Typeface(name=font.family_name)
        db.add(typeface)
        db.flush()

    # TODO: Deduplication
    font_obj = Font(
        typeface_id=typeface.id,
        name=font.full_name,
        subfamily=font.subfamily,
        postscript_name=font.postscript_name,
        version=font.version,
        filename=filepath.name,
    )
    db.add(font_obj)
    db.flush()
    job.font_id = font_obj.id
    job.progress = 10
    db.commit()

    metric_progress = 90 / len(metrics_list)
    total_glyphs = sum(len(master.glyphs) for master in font.masters.values())
    update_interval = max(1, int(total_glyphs / metric_progress))

    for metric in metrics_list:
        job.current_metric = metric.display_name
        counter = 0

        # TODO: Update in the future
        if metric.name != 'grayscale':
            raise ValueError(f'Metric {metric.name} not supported')

        data = {}
        for master_name, master in font.masters.items():
            for glyph in master.iter_glyphs():
                counter += 1
                if counter % update_interval == 0:
                    job.progress += 1
                    db.commit()

                # Calculate grayscale
                # TODO: Because layer_to_svg takes a layer object, I am rewriting the exact same logic here manually
                # We should find a way to better simplify the two processes.
                svg_code = glyph.to_svg_code()
                try:
                    im = pyvips.Image.svgload_buffer(bytes(svg_code, 'utf-8'), scale=1.0)
                except Exception as e:
                    if glyph.width == 0 or glyph.height == 0:
                        continue
                    print(f'Error loading SVG for glyph {glyph.glyph_id}: {e}')
                    continue
                arr = im.numpy()[:, :, 3]
                height, width = arr.shape
                total_sum = arr.sum().item()
                grayscale = total_sum / (width * height) / 255

                if glyph.glyph_id in data:
                    data[glyph.glyph_id]['grayscale'][master_name] = grayscale
                else:
                    data[glyph.glyph_id] = {'id': glyph.glyph_id, 'string': glyph.string, 'grayscale': {master_name: grayscale}}

        # Save data to JSONL file
        jsonl_file = DATA_DIR / metric.name / f'{font.full_name}.jsonl'  # TODO: Make sure filename is valid
        jsonl_file.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_file.open('w', encoding='utf-8') as f:
            for line in data.values():
                f.write(json.dumps(line, ensure_ascii=False) + '\n')

        # Update completed metrics (JSON fields need reassignment)
        completed = list(job.completed_metrics) if job.completed_metrics else []
        completed.append(metric.name)
        job.completed_metrics = completed

        # Create FontMetric record
        font_metric = FontMetric(
            font_id=font_obj.id,
            metric_id=metric.id,
            job_id=job.id,
            data_path=jsonl_file.as_posix(),
        )
        db.add(font_metric)
        db.commit()


def _process_glyphs_file(db, job: Job, filepath: Path, metrics_list: list[Metric]):
    try:
        font = GSFont(filepath)
    except Exception as e:
        job.status = 'failed'
        job.error = str(e)
        job.completed_at = datetime.now()
        db.commit()
        raise ValueError(f'Failed to load Glyphs file: {e}')

    version_string = f'{font.versionMajor}.{font.versionMinor}' if font.versionMajor is not None else None
    # For Glyphs files, use familyName as the name (instances define specific styles)
    # The first master's name can serve as a subfamily indicator
    first_master_name = font.masters[0].name if font.masters else None
    master_ids = {master.id for master in font.masters}

    # Get localized family name
    family_name = font.familyName
    full_name = font.properties['postscriptFullNames'] or font.properties['postscriptFontName']
    for prop in font.properties:
        if prop.key == 'familyNames':
            if hasattr(prop, '_localized_values') and prop._localized_values and prop._localized_values.get('ZHS'):  # There might be more than ZHS
                family_name = prop._localized_values['ZHS']
                break

    # Fetch and update font information
    typeface = db.query(Typeface).filter(Typeface.name == family_name).first()
    if not typeface:
        typeface = Typeface(name=family_name)
        db.add(typeface)
        db.flush()

    # TODO: Deduplication
    font_obj = Font(
        typeface_id=typeface.id,
        name=family_name,
        subfamily=first_master_name,
        postscript_name=full_name,
        version=version_string,
        filename=filepath.name,
    )
    db.add(font_obj)
    job.font_id = font_obj.id
    job.progress = 20
    db.commit()

    metric_progress = 80 / len(metrics_list)
    total_glyphs = len(font.glyphs) * len(font.masters)
    update_interval = max(1, total_glyphs // int(metric_progress))

    for metric in metrics_list:
        job.current_metric = metric.display_name
        counter = 0

        # TODO: Update in the future
        if metric.name != 'grayscale':
            raise ValueError(f'Metric {metric.name} not supported')

        data = {}
        for glyph in font.glyphs:
            glyph_data = {
                'id': glyph.name,
                'string': glyph.string,
                'unicode': glyph.unicode,
                'grayscale': {},
            }

            for layer in glyph.layers:
                # Skip non-master layers (backup layers, brace layers, etc.)
                # In glyphsLib, master layers have layerId matching a master's id
                if layer.layerId not in master_ids:
                    continue

                counter += 1
                if counter % update_interval == 0:
                    job.progress += 1
                    db.commit()

                try:
                    grayscale = metrics.grayscale(layer)
                except Exception as e:
                    print(f'Error calculating grayscale for layer {layer.name} of glyph {glyph.name}: {e}')
                    continue
                glyph_data['grayscale'][layer.master.name] = grayscale

            # Only add if we have grayscale data
            if glyph_data['grayscale']:
                data[glyph.name] = glyph_data

        # Save data to JSONL file
        jsonl_file = DATA_DIR / metric.name / f'{family_name}.jsonl'
        jsonl_file.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_file.open('w', encoding='utf-8') as f:
            for line in data.values():
                f.write(json.dumps(line, ensure_ascii=False) + '\n')

        # Update completed metrics
        completed = list(job.completed_metrics) if job.completed_metrics else []
        completed.append(metric.name)
        job.completed_metrics = completed

        # Create FontMetric record
        font_metric = FontMetric(
            font_id=font_obj.id,
            metric_id=metric.id,
            job_id=job.id,
            data_path=jsonl_file.as_posix(),
        )
        db.add(font_metric)
        db.commit()
