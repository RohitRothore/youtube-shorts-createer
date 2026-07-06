import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
WEB_DIR = PROJECT_ROOT / "web"
MUSIC_DIR = PROJECT_ROOT / "resources" / "music"


@dataclass(frozen=True)
class Settings:
    ollama_url: str
    ollama_model: str
    tts_voice: str
    video_width: int
    video_height: int
    video_fps: int
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama2"),
            tts_voice=os.getenv("TTS_VOICE", "en-US-ChristopherNeural"),
            video_width=int(os.getenv("VIDEO_WIDTH", "1080")),
            video_height=int(os.getenv("VIDEO_HEIGHT", "1920")),
            video_fps=int(os.getenv("VIDEO_FPS", "30")),
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
        )
