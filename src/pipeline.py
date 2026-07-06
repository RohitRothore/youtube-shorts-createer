import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import httpx

from src.audio_generator import generate_speech
from src.config import OUTPUT_DIR, Settings, MUSIC_DIR
from src.models import ShortScript
from src.script_generator import generate_script
from src.video_assembler import create_scene_clip, merge_clips, save_metadata, mix_background_music
from src.visual_generator import generate_image

MUSIC_URLS = {
    "upbeat": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    "cinematic": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",
    "lofi": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3",
}


async def _ensure_background_music(genre: str) -> Path | None:
    if genre not in MUSIC_URLS:
        return None
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    dest = MUSIC_DIR / f"{genre}.mp3"
    if dest.exists() and dest.stat().st_size > 1000:
        return dest

    url = MUSIC_URLS[genre]
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code == 200:
                dest.write_bytes(response.content)
                return dest
    except Exception as e:
        print(f"Error downloading background music {genre}: {e}")
    return None



class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    prompt: str
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    message: str = "Waiting in queue..."
    video_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "video_path": self.video_path,
            "metadata": self.metadata,
            "error": self.error,
            "created_at": self.created_at,
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(self, prompt: str) -> Job:
        job = Job(id=str(uuid.uuid4()), prompt=prompt)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_recent(self, limit: int = 20) -> list[Job]:
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]


job_store = JobStore()


def _slugify(text: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in text.lower())
    return "-".join(part for part in safe.split("-") if part)[:60] or "short"


@dataclass
class GenerationResult:
    video_path: Path
    script: ShortScript
    output_dir: Path
    sources: dict[str, str]


ProgressCallback = Callable[[int, str], None]


async def run_pipeline(
    prompt: str,
    *,
    settings: Settings | None = None,
    output_dir: Path | None = None,
    use_online_images: bool = True,
    on_progress: ProgressCallback | None = None,
    music_genre: str = "none",
    script_data: ShortScript | None = None,
) -> GenerationResult:
    import asyncio as _asyncio
    settings = settings or Settings.from_env()
    sources: dict[str, str] = {}

    def report(progress: int, message: str) -> None:
        if on_progress:
            on_progress(progress, message)

    work_dir = output_dir or (OUTPUT_DIR / f"{_slugify(prompt[:40])}-{uuid.uuid4().hex[:8]}")
    work_dir.mkdir(parents=True, exist_ok=True)
    scenes_dir = work_dir / "scenes"
    clips_dir = work_dir / "clips"

    report(5, "Shuru ho raha hai...")

    if script_data:
        script = script_data
        script_source = "custom"
        report(20, f"Custom script: {script.title}")
    else:
        script, script_source = await generate_script(
            settings,
            prompt,
            on_status=lambda msg: report(10, msg),
        )
    sources["script"] = script_source
    report(20, f"Script taiyaar: {script.title}")

    clip_paths: list[Path] = []

    # -----------------------------------------------------------------------
    # PARALLEL generation: fetch all images + all audio simultaneously
    # This is the single biggest speed win (~3x faster than sequential)
    # -----------------------------------------------------------------------
    report(25, "Images aur audio ek saath ban rahe hain...")

    # Build all image + audio coroutines for hook + scenes
    all_image_coros = []
    all_audio_coros = []

    # Hook
    all_image_coros.append(generate_image(
        settings,
        script.scenes[0].visual_prompt,
        script.title,
        scenes_dir / "hook_image.png",
        scene_index=0,
        use_online_images=use_online_images,
    ))
    all_audio_coros.append(generate_speech(settings, script.hook, scenes_dir / "hook_audio.mp3"))

    # Scenes
    for index, scene in enumerate(script.scenes):
        all_image_coros.append(generate_image(
            settings,
            scene.visual_prompt,
            scene.on_screen_text,
            scenes_dir / f"{index:02d}_image.png",
            scene_index=index,
            use_online_images=use_online_images,
        ))
        all_audio_coros.append(generate_speech(
            settings,
            scene.narration,
            scenes_dir / f"{index:02d}_audio.mp3",
        ))

    report(30, "Visuals aur awaaz tayaar ho rahe hain...")

    # Run images and audios in parallel
    image_results, audio_results = await _asyncio.gather(
        _asyncio.gather(*all_image_coros),
        _asyncio.gather(*all_audio_coros),
    )

    report(65, "Clips render ho rahe hain...")

    # Hook clip
    hook_image, hook_img_src = image_results[0]
    hook_audio = audio_results[0]
    sources["hook_image"] = hook_img_src
    hook_clip = create_scene_clip(
        hook_image,
        hook_audio,
        clips_dir / "00_hook.mp4",
        width=settings.video_width,
        height=settings.video_height,
        fps=settings.video_fps,
        min_duration=2.5,
    )
    clip_paths.append(hook_clip)

    # Scene clips (sequential — FFmpeg is CPU bound, parallelising would starve cores)
    for index, scene in enumerate(script.scenes):
        progress_pct = 65 + int((index + 1) / len(script.scenes) * 22)
        report(progress_pct, f"Scene {index + 1}/{len(script.scenes)} render...")
        image_path, img_src = image_results[index + 1]
        audio_path = audio_results[index + 1]
        sources[f"scene_{index + 1}_image"] = img_src
        clip_path = create_scene_clip(
            image_path,
            audio_path,
            clips_dir / f"{index + 1:02d}_scene.mp4",
            width=settings.video_width,
            height=settings.video_height,
            fps=settings.video_fps,
            min_duration=3.0,
        )
        clip_paths.append(clip_path)

    report(90, "Sabhi scenes jodi jaa rahi hain...")
    # Safe ASCII slug for the file path (title may contain Devanagari)
    safe_title = re.sub(r"[^a-zA-Z0-9\-]", "-", _slugify(prompt[:40]))

    # Mix background music if requested
    if music_genre != "none":
        merged_raw_path = work_dir / f"{safe_title or 'short'}_raw.mp4"
        merge_clips(clip_paths, merged_raw_path)

        report(95, f"Downloading/preparing background music ({music_genre})...")
        music_path = await _ensure_background_music(music_genre)

        if music_path:
            report(97, "Mixing background music...")
            final_path = work_dir / f"{safe_title or 'short'}.mp4"
            try:
                final_path = mix_background_music(merged_raw_path, music_path, final_path)
                merged_raw_path.unlink(missing_ok=True)
            except Exception as e:
                print(f"Failed to mix music: {e}")
                final_path = merged_raw_path  # fallback
        else:
            report(97, "Music download failed — proceeding with voiceover only.")
            final_path = work_dir / f"{safe_title or 'short'}.mp4"
            merged_raw_path.rename(final_path)
    else:
        final_path = merge_clips(clip_paths, work_dir / f"{safe_title or 'short'}.mp4")

    metadata = {
        "title": script.title,
        "hook": script.hook,
        "hashtags": script.hashtags,
        "prompt": prompt,
        "video": str(final_path),
        "sources": sources,
        "music": music_genre,
        "scenes": [
            {
                "narration": s.narration,
                "visual_prompt": s.visual_prompt,
                "on_screen_text": s.on_screen_text,
            }
            for s in script.scenes
        ],
    }
    save_metadata(work_dir, metadata)
    sources["tts"] = "edge-tts (Hinglish)"

    report(100, "🎬 Aapka YouTube Short tayaar hai!")
    return GenerationResult(
        video_path=final_path,
        script=script,
        output_dir=work_dir,
        sources=sources,
    )



