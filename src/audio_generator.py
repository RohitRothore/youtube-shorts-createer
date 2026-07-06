from pathlib import Path

import edge_tts

from src.config import Settings


async def generate_speech(
    settings: Settings,
    text: str,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = text.strip()
    if not content.endswith((".", "?", "!")):
        content += "."
    communicate = edge_tts.Communicate(
        content,
        settings.tts_voice,
        rate="+3%",
        volume="+2%",
        boundary="SentenceBoundary",
    )
    await communicate.save(str(output_path))
    return output_path
