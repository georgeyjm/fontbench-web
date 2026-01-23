import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.processing import analyze_glyphs_file

app = FastAPI(title="FontBench Web", description="Glyphs font file analysis and visualization")

# Serve static files (frontend)
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    """Serve the main frontend page."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "FontBench Web API", "docs": "/docs"}


@app.post("/api/upload")
async def upload_glyphs_file(file: UploadFile = File(...)):
    """
    Upload a .glyphs file for analysis.
    Returns processed data for visualization.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not file.filename.endswith((".glyphs", ".glyphx")):
        raise HTTPException(
            status_code=400, detail="Invalid file type. Please upload a .glyphs or .glyphx file"
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


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


def run_server():
    """Entry point for running the server."""
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    run_server()
