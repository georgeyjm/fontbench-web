from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from app.config import STATIC_DIR
from app.db import init_db, SessionLocal
from app.routers import data_router, jobs_router, metrics_router, typefaces_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    '''
    Lifespan context manager for FastAPI app.
    Handles startup and shutdown events.
    '''
    # Startup: Initialize database
    try:
        init_db()
        db = SessionLocal()
    except Exception as e:
        raise
    finally:
        db.close()
    yield

    # Shutdown: Cleanup if needed
    pass


app = FastAPI(
    title='FontBench Web',
    description='Glyphs font file analysis and visualization',
    version='0.1.0',
    lifespan=lifespan,
)

# Include routers
app.include_router(data_router)
app.include_router(jobs_router)
app.include_router(metrics_router)
app.include_router(typefaces_router)

# Serve static files (frontend)
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')


@app.get('/')
async def main_page():
    index_path = STATIC_DIR / 'index.html'
    if index_path.exists():
        return FileResponse(index_path)
    return {'message': 'FontBench Web API', 'docs': '/docs'}


@app.get('/upload')
async def upload_page():
    upload_path = STATIC_DIR / 'upload.html'
    if upload_path.exists():
        return FileResponse(upload_path)
    return {'message': 'Upload page not found'}


def run_server():
    '''Entry point for running the server.'''
    uvicorn.run('app.main:app', host='127.0.0.1', port=8000, reload=True)


if __name__ == '__main__':
    run_server()
