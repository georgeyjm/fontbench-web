from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from fontbench.utils import get_font_weight_value

from app.models import Font, FontMetric, Metric, Typeface
from app.db import SessionDep
from app.data import load_metric_data


router = APIRouter(prefix='/api/data', tags=['data'])


def get_metric_obj(db: Session, metric: str) -> Metric:
    '''Get the Metric object, raising HTTPException if not found.'''
    db_metric = db.query(Metric).filter(Metric.name == metric).first()
    if not db_metric:
        valid_metrics = [m.name for m in db.query(Metric).all()]
        raise HTTPException(
            status_code=400, detail=f'Invalid metric: {metric}. Available: {valid_metrics}'
        )
    return db_metric


@router.get('')
async def list_available_metrics(db: SessionDep):
    '''List all available metrics.'''
    metrics = db.query(Metric).all()
    return {'metrics': [m.name for m in metrics]}


@router.get('/{metric}')
async def list_typefaces_with_metric(db: SessionDep, metric: str):
    '''List typefaces that have at least one font with the specified metric computed.'''
    metric_obj = get_metric_obj(db, metric)

    # Query fonts that have this metric computed, grouped by typeface
    font_metrics = (
        db.query(FontMetric)
        .filter(FontMetric.metric_id == metric_obj.id)
        .join(Font)
        .all()
)

    # Get unique typefaces
    typeface_map = {}
    for fm in font_metrics:
        if fm.font and fm.font.typeface:
            tf = fm.font.typeface
            if tf.id not in typeface_map:
                typeface_map[tf.id] = {'id': tf.id, 'name': tf.name}

    # Sort by name
    typefaces = sorted(typeface_map.values(), key=lambda t: t['name'])
    return {'typefaces': typefaces, 'metric': metric}


@router.get('/{metric}/{typeface_id:int}')
async def get_typeface_fonts(db: SessionDep, metric: str, typeface_id: int, charset: Literal['3500', '7000', 'chinese'] = '3500'):
    '''
    Get all fonts in a typeface that have the specified metric computed.
    Returns font list with their masters.
    '''
    metric_obj = get_metric_obj(db, metric)

    # Find the typeface
    typeface = db.query(Typeface).filter(Typeface.id == typeface_id).first()
    if not typeface:
        raise HTTPException(status_code=404, detail='Typeface not found')

    # Get all fonts in this typeface that have this metric
    font_metrics = (
        db.query(FontMetric)
        .filter(FontMetric.metric_id == metric_obj.id)
        .join(Font)
        .filter(Font.typeface_id == typeface_id)
        .all()
    )

    if not font_metrics:
        raise HTTPException(
            status_code=404, detail=f'{metric.capitalize()} data not found for this typeface'
        )

    # Build fonts list with masters
    fonts = []
    for fm in font_metrics:
        if not fm.font or not fm.data_path:
            continue

        df = load_metric_data(fm, charset=charset)
        masters = df['master'].unique().tolist()
        masters = sorted(masters, key=get_font_weight_value, reverse=True)

        fonts.append({
            'id': fm.font.id,
            'name': fm.font.name,
            'masters': masters,
        })

    return {
        'metric': metric,
        'typeface_id': typeface.id,
        'typeface_name': typeface.name,
        'fonts': fonts,
    }


@router.get('/{metric}/{typeface_id:int}/{font_id:int}')
async def get_font_metric_data(db: SessionDep, metric: str, typeface_id: int, font_id: int, charset: Literal['3500', '7000', 'chinese'] = '3500', master: str | None = None):
    '''
    Get metric data for a specific font within a typeface.
    Returns data formatted for visualization.
    '''
    metric_obj = get_metric_obj(db, metric)

    # Find the font and verify it belongs to the typeface
    font = db.query(Font).filter(Font.id == font_id, Font.typeface_id == typeface_id).first()
    if not font:
        raise HTTPException(status_code=404, detail='Font not found in this typeface')

    font_metric = (
        db.query(FontMetric)
        .filter(FontMetric.font_id == font.id, FontMetric.metric_id == metric_obj.id)
        .first()
    )

    df = load_metric_data(font_metric, charset=charset)
    if df is None:
        raise HTTPException(status_code=404, detail=f'{metric} data not found for this font')

    # Filter by master if specified
    masters = df['master'].unique().tolist()
    masters = sorted(masters, key=get_font_weight_value, reverse=True)

    if master and master in masters:
        df = df[df['master'] == master]
    elif master and master not in masters:
        raise HTTPException(status_code=400, detail=f'Master {master} not found. Available: {masters}')

    # Format for Plotly scatter plot
    value_column = metric

    return {
        'metric': metric,
        'typeface_id': typeface_id,
        'font_id': font.id,
        'font_name': font.name,
        'masters': masters,
        'selected_master': master or masters[0] if masters else None,
        'total_chars': len(df),
        'chart_data': {
            'x': list(range(len(df))),
            'y': df[value_column].tolist(),
            'text': df['string'].tolist(),
            'type': 'scatter',
            'mode': 'markers',
            'marker': {'size': 4},
            'hovertemplate': f'%{{text}}<br>{metric.capitalize()}: %{{y:.4f}}<extra></extra>',
        },
    }
