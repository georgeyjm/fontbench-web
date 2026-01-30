import json
import hashlib
from datetime import datetime
from pathlib import Path

import pyvips
from glyphsLib import GSFont
from fontbench import FontProxy, metrics
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.db import SessionLocal
from app.models import Job, Font, FontMetric, Metric, Typeface


def calculate_file_checksum(filepath: Path) -> str:
    '''
    Calculate SHA-256 checksum of a file.
    '''
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def process_metrics_job(job_id: int, filepath: Path, metric_names: list[str]):
    '''
    Background task to process a font file.
    Implements deduplication:
    1. If file checksum matches existing font, reuse it
    2. If requested metrics are already calculated, skip them
    '''
    db: Session = SessionLocal()

    # Data Validation
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
        # Calculate checksum and check for duplicate
        checksum = calculate_file_checksum(filepath)
        existing_font = db.query(Font).filter(Font.checksum == checksum).first()

        if existing_font:
            # Reuse existing font - delete the new upload
            filepath.unlink(missing_ok=True)
            job.font_id = existing_font.id
            job.progress = 10
            db.commit()

            # Filter out already-calculated metrics
            existing_metric_ids = {fm.metric_id for fm in existing_font.font_metrics}
            metrics_to_calculate = [m for m in metrics_list if m.id not in existing_metric_ids]

            if not metrics_to_calculate:
                # All metrics already calculated - complete immediately
                completed = [m.name for m in metrics_list]
                job.completed_metrics = completed
                job.status = 'completed'
                job.progress = 100
                job.completed_at = datetime.now()
                db.commit()
                return

            # Process only missing metrics
            # We need to reload the font file to calculate new metrics
            # Find the original file path from an existing FontMetric
            existing_fm = existing_font.font_metrics[0] if existing_font.font_metrics else None
            if not existing_fm or not existing_fm.data_path:
                raise ValueError('Cannot find data for existing font')

            # TODO: For now, we'll skip processing new metrics for existing fonts
            for fm in existing_font.font_metrics:
                if fm.metric and fm.metric.name in [m.name for m in metrics_list]:
                    completed = list(job.completed_metrics) if job.completed_metrics else []
                    if fm.metric.name not in completed:
                        completed.append(fm.metric.name)
                        job.completed_metrics = completed
            db.commit()
        
        else:
            # New font - process normally
            if filepath.suffix.lower() in ('.ttf', '.otf'):
                _process_opentype_file(db, job, filepath, metrics_list, checksum)
            elif filepath.suffix.lower() in ('.glyphs',):
                _process_glyphs_file(db, job, filepath, metrics_list, checksum)
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


def _process_opentype_file(db, job: Job, filepath: Path, metrics_list: list[Metric], checksum: str):
    try:
        font = FontProxy(filepath)
    except Exception as e:
        job.status = 'failed'
        job.error = str(e)
        job.completed_at = datetime.now()
        db.commit()
        raise ValueError(f'Failed to load font: {e}')

    # Fetch and update font information
    typeface = db.query(Typeface).filter(Typeface.name == font.typographic_family).first()
    if not typeface:
        typeface = Typeface(name=font.typographic_family)
        db.add(typeface)
        db.flush()

    font_obj = Font(
        typeface_id=typeface.id,
        name=font.full_name,
        subfamily=font.typographic_subfamily,
        postscript_name=font.postscript_name,
        version=font.version,
        filename=filepath.name,
        checksum=checksum,
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
        jsonl_file = DATA_DIR / metric.name / f'{font_obj.name}.jsonl'  # TODO: Make sure filename is valid
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
            data_path=jsonl_file.relative_to(DATA_DIR).as_posix(),
        )
        db.add(font_metric)
        db.commit()


def _process_glyphs_file(db, job: Job, filepath: Path, metrics_list: list[Metric], checksum: str):
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
    full_name = f'{family_name} {first_master_name}'
    postscript_name = font.properties['postscriptFullNames'] or font.properties['postscriptFontName']
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

    font_obj = Font(
        typeface_id=typeface.id,
        name=full_name,
        subfamily=first_master_name,
        postscript_name=postscript_name,
        version=version_string,
        filename=filepath.name,
        checksum=checksum,
    )
    db.add(font_obj)
    db.flush()
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
        jsonl_file = DATA_DIR / metric.name / f'{font_obj.name}.jsonl'
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
            data_path=jsonl_file.relative_to(DATA_DIR).as_posix(),
        )
        db.add(font_metric)
        db.commit()
