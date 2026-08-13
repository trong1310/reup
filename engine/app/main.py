from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .pipeline import JobManager

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI Video Dubber Local Engine", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = JobManager(DATA_DIR)


class ProcessRequest(BaseModel):
    url: str
    source_language: str = "auto"
    target_language: str = "vi"
    voice_id: str | None = None
    rewrite: bool = False


@app.get("/api/health")
def health():
    return {"ok": True, "service": "ai-video-dubber-engine"}


@app.get("/api/voices")
def voices():
    return manager.tts.list_voices()


@app.post("/api/jobs")
async def create_job(req: ProcessRequest):
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="URL is required")

    job_id = str(uuid.uuid4())
    manager.create(job_id, req.model_dump())
    asyncio.create_task(manager.run(job_id))
    return {
        "id": job_id,
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "stage": "queued",
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = manager.get(job_id)
    if job:
        return job

    # Fallback to checking disk for completed runs
    job_dir = DATA_DIR / job_id
    if job_dir.exists() and (job_dir / "output.mp4").exists():
        return {
            "id": job_id,
            "job_id": job_id,
            "status": "completed",
            "progress": 100,
            "stage": "done",
            "output": str(job_dir / "output.mp4"),
            "error": None,
        }

    raise HTTPException(status_code=404, detail="Job not found")


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str):
    job = manager.get(job_id)
    if job and job.get("output") and Path(job["output"]).exists():
        path = Path(job["output"])
        return FileResponse(path, media_type="video/mp4", filename=path.name)

    disk_path = DATA_DIR / job_id / "output.mp4"
    if disk_path.exists():
        return FileResponse(disk_path, media_type="video/mp4", filename="output.mp4")

    raise HTTPException(status_code=404, detail="Output file not found")


@app.get("/api/jobs/{job_id}/subtitles")
def get_subtitles(job_id: str):
    srt_path = DATA_DIR / job_id / "subtitles.srt"
    if srt_path.exists():
        return FileResponse(srt_path, media_type="text/plain", filename="subtitles.srt")

    raise HTTPException(status_code=404, detail="Subtitles not found")
