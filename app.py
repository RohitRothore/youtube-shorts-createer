import asyncio
import shutil
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from src.config import OUTPUT_DIR, WEB_DIR, Settings
from src.pipeline import JobStatus, job_store, run_pipeline
from src.models import ShortScript


app = FastAPI(title="YouTube Short Creator", version="2.0.0")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=500)
    use_online_images: bool = True
    music_genre: str = "none"
    tts_voice: str = "hi-IN-MadhurNeural"
    script: ShortScript | None = None


class GenerateResponse(BaseModel):
    job_id: str


class ScriptRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=500)


async def _process_job(
    job_id: str,
    prompt: str,
    use_online_images: bool,
    music_genre: str,
    tts_voice: str,
    script_data: ShortScript | None,
) -> None:
    job = job_store.get(job_id)
    if not job:
        return

    settings = Settings.from_env()
    # Override TTS voice from user selection
    import dataclasses
    settings = dataclasses.replace(settings, tts_voice=tts_voice)
    job.status = JobStatus.RUNNING
    job.message = "Shuru ho raha hai..."

    def on_progress(progress: int, message: str) -> None:
        job.progress = progress
        job.message = message

    try:
        result = await run_pipeline(
            prompt,
            settings=settings,
            use_online_images=use_online_images,
            on_progress=on_progress,
            music_genre=music_genre,
            script_data=script_data,
        )
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.message = "Done!"
        job.video_path = str(result.video_path)
        job.metadata = {
            "title": result.script.title,
            "hook": result.script.hook,
            "hashtags": result.script.hashtags,
            "sources": result.sources,
            "output_dir": str(result.output_dir),
        }
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        job.message = f"Failed: {exc}"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"title": "YouTube Short Creator"},
    )


@app.post("/api/generate-script", response_model=ShortScript)
async def generate_script_api(body: ScriptRequest) -> ShortScript:
    prompt = body.prompt.strip()
    if len(prompt) < 3:
        raise HTTPException(status_code=400, detail="Prompt is too short.")

    settings = Settings.from_env()
    try:
        from src.script_generator import generate_script
        script, _ = await generate_script(settings, prompt)
        return script
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate script: {e}")


@app.post("/api/generate", response_model=GenerateResponse)
async def generate_short(
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
) -> GenerateResponse:
    prompt = body.prompt.strip()
    if len(prompt) < 3:
        raise HTTPException(status_code=400, detail="Prompt is too short.")

    job = job_store.create(prompt)
    background_tasks.add_task(
        _process_job,
        job.id,
        prompt,
        body.use_online_images,
        body.music_genre,
        body.tts_voice,
        body.script,
    )
    return GenerateResponse(job_id=job.id)


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.to_dict()


@app.get("/api/jobs")
async def list_jobs() -> list[dict]:
    return [job.to_dict() for job in job_store.list_recent()]


@app.get("/api/download/{job_id}")
async def download_video(job_id: str) -> FileResponse:
    job = job_store.get(job_id)
    if not job or job.status != JobStatus.COMPLETED or not job.video_path:
        raise HTTPException(status_code=404, detail="Video not ready.")

    path = Path(job.video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video file missing.")

    title = job.metadata.get("title", "youtube-short")
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in title).strip()
    filename = f"{safe_name or 'youtube-short'}.mp4"

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=filename,
    )


@app.get("/api/stream/{job_id}")
async def stream_video(job_id: str) -> FileResponse:
    job = job_store.get(job_id)
    if not job or job.status != JobStatus.COMPLETED or not job.video_path:
        raise HTTPException(status_code=404, detail="Video not ready.")

    path = Path(job.video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video file missing.")

    return FileResponse(path, media_type="video/mp4")


@app.get("/api/health")
async def health() -> dict:
    settings = Settings.from_env()
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    ollama_ok = False
    ollama_models: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.ollama_url}/api/tags")
            if response.status_code == 200:
                ollama_ok = True
                data = response.json()
                ollama_models = [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        pass

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    return {
        "status": "ok" if ffmpeg_ok else "degraded",
        "ffmpeg": ffmpeg_ok,
        "ollama": ollama_ok,
        "ollama_models": ollama_models,
        "script_fallback": "Built-in templates (always available)",
        "tts": "edge-tts (free)",
        "images": "Pollinations.ai with local slide fallback",
    }
