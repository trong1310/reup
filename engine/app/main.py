from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Tải các biến môi trường từ file .env (bao gồm HF_TOKEN)
load_dotenv()

# Tự động thêm đường dẫn FFmpeg vào PATH môi trường Python
ffmpeg_bin = r"C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0-full_build\bin"
if os.path.exists(ffmpeg_bin) and ffmpeg_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] = ffmpeg_bin + os.pathsep + os.environ.get("PATH", "")

from .pipeline import JobManager
from .settings_manager import get_all_settings, save_settings_to_env, test_api_key

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
    clean_sub_mode: str | None = None
    subtitle_style: str | None = "blur_yellow"
    burn_subtitles: bool | None = True


class SettingsUpdateRequest(BaseModel):
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    deepgram_api_key: str | None = None
    hf_token: str | None = None
    stt_provider: str | None = "auto"
    translate_provider: str | None = "auto"
    whisper_model: str | None = "base"
    whisper_device: str | None = "cpu"
    tts_rate: str | None = "170"


class TestApiRequest(BaseModel):
    provider: str
    api_key: str | None = None


@app.get("/api/health")
def health():
    return {"ok": True, "service": "ai-video-dubber-engine"}


@app.get("/api/settings")
def get_settings():
    return get_all_settings()


@app.post("/api/settings")
def update_settings(req: SettingsUpdateRequest):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    saved = save_settings_to_env(updates)
    return {"ok": True, "settings": saved}


@app.post("/api/settings/test")
def test_settings_api(req: TestApiRequest):
    res = test_api_key(req.provider, req.api_key)
    return res


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
