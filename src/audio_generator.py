from pathlib import Path

import edge_tts

from src.config import Settings


async def generate_speech(
    settings: Settings,
    text: str,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text.strip(), settings.tts_voice)
    await communicate.save(str(output_path))
    return output_path
