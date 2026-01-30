from fastapi import APIRouter
from app.db import SessionDep
from app.models import Metric


router = APIRouter(prefix='/api/metrics', tags=['metrics'])


@router.get('')
async def list_available_metrics(db: SessionDep):
    '''List all available processing metrics.'''
    metrics = db.query(Metric).all()
    return {
        'metrics': [m.name for m in metrics],
        'details': [m.serialize() for m in metrics],
    }
