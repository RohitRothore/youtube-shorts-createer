import json
import shutil
import subprocess
from pathlib import Path


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg is not installed. Install it with: sudo apt install ffmpeg"
        )
    return ffmpeg


def get_audio_duration_seconds(audio_path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is not installed (comes with ffmpeg).")

    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def create_scene_clip(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    *,
    width: int,
    height: int,
    fps: int,
    min_duration: float = 2.0,
) -> Path:
    ffmpeg = _require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    duration = max(get_audio_duration_seconds(audio_path), min_duration)
    frames = max(int(duration * fps), 1)

    # 2x supersampling for smooth zoompan filter execution
    w2 = 2 * width
    h2 = 2 * height

    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-t",
            str(duration),
            "-pix_fmt",
            "yuv420p",
            "-vf",
            (
                f"scale={w2}:{h2}:force_original_aspect_ratio=increase,"
                f"crop={w2}:{h2},"
                f"zoompan=z='if(lte(zoom,1.08),zoom+0.0008,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={frames}:s={w2}x{h2}:fps={fps},"
                f"scale={width}:{height}"
            ),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path


def merge_clips(clip_paths: list[Path], output_path: Path) -> Path:
    ffmpeg = _require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    list_file = output_path.with_suffix(".txt")
    list_file.write_text(
        "\n".join(f"file '{path.resolve()}'" for path in clip_paths),
        encoding="utf-8",
    )

    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        list_file.unlink(missing_ok=True)

    return output_path


def save_metadata(output_dir: Path, metadata: dict) -> Path:
    path = output_dir / "metadata.json"
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return path


def mix_background_music(
    video_path: Path,
    music_path: Path,
    output_path: Path,
    music_volume: float = 0.12,
) -> Path:
    ffmpeg = _require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-stream_loop",
            "-1",
            "-i",
            str(music_path),
            "-filter_complex",
            f"[0:a]volume=1.0[v_aud];[1:a]volume={music_volume}[m_aud];[v_aud][m_aud]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path
