"""
Glyphs file processing and analysis.
"""

from pathlib import Path
from typing import Any

import numpy as np
from glyphsLib import GSFont


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
