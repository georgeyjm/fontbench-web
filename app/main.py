import tempfile
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import GRAYSCALE_DIR
from app.processing import analyze_glyphs_file, load_grayscale_jsonl

app = FastAPI(title='FontBench Web', description='Glyphs font file analysis and visualization')


def get_font_weight_value(master_name: str) -> int:
    """
    Map font weight name to numeric value for sorting.
    Returns weight value from 100 (Thin) to 950 (Extra Black).
    Unknown weights default to 400 (Regular).
    """
    weight_map = {
        'thin': 100,
        'extra light': 200,
        'ultra light': 200,
        'light': 300,
        'regular': 400,
        'normal': 400,
        'medium': 500,
        'semi bold': 600,
        'demi bold': 600,
        'bold': 700,
        'extra bold': 800,
        'ultra bold': 800,
        'black': 900,
        'heavy': 900,
        'extra black': 950,
        'ultra black': 950,
    }
    # Normalize to lowercase for matching
    normalized = master_name.lower().strip()
    return weight_map.get(normalized, 400)


# Serve static files (frontend)
static_dir = Path(__file__).parent / 'static'
static_dir.mkdir(exist_ok=True)
app.mount('/static', StaticFiles(directory=static_dir), name='static')


@app.get('/')
async def root():
    '''Serve the main frontend page.'''
    index_path = static_dir / 'index.html'
    if index_path.exists():
        return FileResponse(index_path)
    return {'message': 'FontBench Web API', 'docs': '/docs'}


@app.post('/api/upload')
async def upload_glyphs_file(file: UploadFile = File(...)):
    '''
    Upload a .glyphs file for analysis.
    Returns processed data for visualization.
    '''
    if not file.filename:
        raise HTTPException(status_code=400, detail='No filename provided')

    if not file.filename.endswith(('.glyphs', '.glyphx')):
        raise HTTPException(
            status_code=400, detail='Invalid file type. Please upload a .glyphs or .glyphx file'
        )

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        # Process the file
        result = analyze_glyphs_file(tmp_path)
        return result
    finally:
        # Clean up temp file
        tmp_path.unlink(missing_ok=True)


@app.get('/api/health')
async def health_check():
    '''Health check endpoint.'''
    return {'status': 'healthy'}


@app.get('/api/grayscale')
async def list_grayscale_files():
    '''List available precomputed grayscale files.'''
    if not GRAYSCALE_DIR.exists():
        return {'files': []}
    files = [f.stem for f in GRAYSCALE_DIR.glob('*.jsonl')]
    return {'files': files}


@app.get('/api/grayscale/{font_name}')
async def get_grayscale_data(
    font_name: str,
    charset: Literal['3500', '7000', 'chinese'] = '3500',
    master: str | None = None,
):
    '''
    Get grayscale data for a font.
    Returns data formatted for scatter plot visualization.
    '''
    jsonl_path = GRAYSCALE_DIR / f'{font_name}.jsonl'
    if not jsonl_path.exists():
        raise HTTPException(status_code=404, detail=f'Grayscale data not found for {font_name}')

    df = load_grayscale_jsonl(str(jsonl_path), charset=charset)

    # Filter by master if specified
    masters = df['master'].unique().tolist()
    # Sort masters by canonical font weight (lightest to thickest)
    masters = sorted(masters, key=get_font_weight_value, reverse=False)
    if master and master in masters:
        df = df[df['master'] == master]
    elif master and master not in masters:
        raise HTTPException(status_code=400, detail=f'Master {master} not found. Available: {masters}')

    # Format for Plotly scatter plot
    # X-axis is index (ordered by grayscale), Y-axis is grayscale value
    return {
        'font_name': font_name,
        'masters': masters,
        'selected_master': master or masters[0] if masters else None,
        'total_chars': len(df),
        'chart_data': {
            'x': list(range(len(df))),
            'y': df['grayscale'].tolist(),
            'text': df['string'].tolist(),  # For hover
            'type': 'scatter',
            'mode': 'markers',
            'marker': {'size': 4},
            'hovertemplate': '%{text}<br>Grayscale: %{y:.4f}<extra></extra>',
        },
    }


def run_server():
    '''Entry point for running the server.'''
    uvicorn.run('app.main:app', host='127.0.0.1', port=8000, reload=True)


if __name__ == '__main__':
    run_server()
