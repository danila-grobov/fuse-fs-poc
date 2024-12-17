from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import time

app = FastAPI()

FILES_DIR = Path("files")

@app.get("/list")
def list_files():
    """List all files in the directory."""
    if not FILES_DIR.exists():
        raise HTTPException(status_code=404, detail="Directory not found")
    
    files = [f.name for f in FILES_DIR.iterdir() if f.is_file()]
    return {"files": files}

@app.get("/download/{file_name}")
def download_file(file_name: str):
    """Download a specific file."""
    time.sleep(5)
    file_path = FILES_DIR / file_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)
