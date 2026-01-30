import json
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Form

from app.config import UPLOADS_DIR
from app.db import SessionDep
from app.models import Job, Metric, Typeface
from app.handler import process_metrics_job


router = APIRouter(prefix='/api/jobs', tags=['jobs'])


@router.get('')
async def list_jobs(db: SessionDep):
    '''List all jobs (most recent first).'''
    jobs = db.query(Job).order_by(Job.created_at.desc()).all()
    return {'jobs': [job.serialize() for job in jobs]}


@router.post('')
async def create_upload_job(db: SessionDep, background_tasks: BackgroundTasks, file: UploadFile = File(...), metrics: str = Form(...), typeface_id: int | None = Form(None)):
    '''
    Create a new upload job for processing a font file.
    Returns job ID for status polling.
    '''
    if not file.filename:
        raise HTTPException(status_code=422, detail='No filename provided')

    # Validate file extension
    valid_extensions = ('.ttf', '.otf', '.glyphs')
    if not file.filename.lower().endswith(valid_extensions):
        raise HTTPException(
            status_code=422,
            detail=f'Invalid file type. Supported: {', '.join(valid_extensions)}',
        )

    # Parse and validate metrics
    try:
        requested_metrics = json.loads(metrics)
        if not isinstance(requested_metrics, list):
            raise ValueError('Metrics must be a list')
        if not requested_metrics:
            raise HTTPException(status_code=422, detail='At least one metric must be selected')

        # Validate metrics exist in database
        valid_metrics = {m.name for m in db.query(Metric).all()}
        invalid = set(requested_metrics) - valid_metrics
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f'Invalid metrics: {', '.join(invalid)}. Available: {', '.join(valid_metrics)}',
            )
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='Invalid metrics format')

    # Validate typeface if provided
    if typeface_id:
        typeface = db.query(Typeface).filter(Typeface.id == typeface_id).first()
        if not typeface:
            raise HTTPException(status_code=404, detail='Typeface not found')

    # Save file to uploads directory
    # TODO: Check for duplicate checksums first
    filename = file.filename
    while (UPLOADS_DIR / filename).exists():
        filename = Path(file.filename).stem + f'_{uuid.uuid4().hex[:8]}' + Path(file.filename).suffix
    content = await file.read()
    filepath = UPLOADS_DIR / filename
    with filepath.open('wb') as f:
        f.write(content)

    # Create Job record
    job = Job(
        status='pending',
        progress=0,
        requested_metrics=requested_metrics,
        completed_metrics=[],
    )
    db.add(job)
    db.commit()

    # Schedule background processing
    background_tasks.add_task(process_metrics_job, job.id, filepath, requested_metrics)

    return {'job_id': job.id, 'status': job.status}


@router.get('/{job_id}')
async def get_job_status(job_id: str, db: SessionDep):
    '''Get the status of an upload job.'''
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    return job.serialize()


@router.delete('/{job_id}')
async def delete_job(job_id: str, db: SessionDep):
    '''Delete a job.'''
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    db.delete(job)
    db.commit()
    return {'status': 'deleted'}
