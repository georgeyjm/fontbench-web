from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from fontbench.utils import get_font_weight_value

from app.config import DATA_DIR
from app.models import Metric
from app.db import SessionDep
from app.handler import load_grayscale_jsonl


router = APIRouter(prefix='/api/data', tags=['data'])


def get_metric_dir(db: Session, metric: str) -> Path:
    '''Get the data directory for a specific metric.'''
    # Validate metric exists in database
    db_metric = db.query(Metric).filter(Metric.name == metric).first()
    if not db_metric:
        valid_metrics = [m.name for m in db.query(Metric).all()]
        raise HTTPException(
            status_code=400, detail=f'Invalid metric: {metric}. Available: {valid_metrics}'
        )
    return DATA_DIR / metric


def load_metric_data(metric: str, jsonl_path: Path, charset: Literal['3500', '7000', 'chinese'] = '3500'):
    '''
    Load data for a specific metric from a JSONL file.
    This is a generic loader that can be extended for different metrics.
    '''
    if metric == 'grayscale':
        return load_grayscale_jsonl(str(jsonl_path), charset=charset)
    else:
        raise HTTPException(status_code=400, detail=f'Loading for metric {metric} not yet implemented')


@router.get('')
async def list_available_metrics(db: SessionDep):
    '''List all available metrics.'''
    metrics = db.query(Metric).all()
    return {'metrics': [m.name for m in metrics]}


@router.get('/{metric}/{font_name}')
async def get_metric_data(db: SessionDep, metric: str, font_name: str, charset: Literal['3500', '7000', 'chinese'] = '3500', master: str | None = None):
    '''
    Get data for a specific metric and font.
    Returns data formatted for visualization.
    '''
    metric_dir = get_metric_dir(metric, db)
    jsonl_path = metric_dir / f'{font_name}.jsonl'

    if not jsonl_path.exists():
        raise HTTPException(
            status_code=404, detail=f'{metric.capitalize()} data not found for {font_name}'
        )

    df = load_metric_data(metric, jsonl_path, charset=charset)

    # Filter by master if specified
    masters = df['master'].unique().tolist()
    # Sort masters by canonical font weight (thickest to lightest)
    masters = sorted(masters, key=get_font_weight_value, reverse=True)

    if master and master in masters:
        df = df[df['master'] == master]
    elif master and master not in masters:
        raise HTTPException(status_code=400, detail=f'Master {master} not found. Available: {masters}')

    # Format for Plotly scatter plot
    value_column = metric  # Assume column name matches metric name

    return {
        'metric': metric,
        'font_name': font_name,
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


@router.get('/{metric}')
async def list_metric_files(db: SessionDep, metric: str):
    '''List available precomputed files for a specific metric.'''
    metric_dir = get_metric_dir(metric, db)
    if not metric_dir.exists():
        return {'files': []}
    files = [f.stem for f in metric_dir.glob('*.jsonl')]
    return {'files': files, 'metric': metric}
