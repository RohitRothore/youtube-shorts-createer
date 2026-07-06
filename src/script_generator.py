import json
import re
from typing import Callable

import httpx

from src.config import Settings
from src.models import Scene, ShortScript

SYSTEM_PROMPT = """You write scripts for YouTube Shorts (vertical, 30-55 seconds total).

Rules:
- Strong hook in first 2 seconds
- Exactly 5 scenes, each 5-10 seconds when spoken
- Natural spoken English, punchy and engaging
- Visual prompts: cinematic, vertical-friendly, vivid, NO text in images
- on_screen_text: max 5 words per scene, bold caption style
- Total spoken words under 140
- 3-5 hashtags without # symbol

Return ONLY valid JSON:
{
  "title": "string",
  "hook": "string",
  "scenes": [
    {"narration": "string", "visual_prompt": "string", "on_screen_text": "string"}
  ],
  "hashtags": ["string"]
}"""


def _slug_words(text: str, max_words: int = 6) -> str:
    words = re.findall(r"\w+", text)
    return " ".join(words[:max_words]).title() if words else "This Topic"


def _build_fallback_script(prompt: str) -> ShortScript:
    topic = prompt.strip().rstrip(".")
    title = _slug_words(topic, 8)
    hook = f"Stop scrolling — you need to hear this about {topic.lower()}."

    templates = [
        (
            f"Most people have no idea how fascinating {topic.lower()} really is.",
            f"cinematic dramatic opening shot about {topic}, vertical composition, vivid colors",
            "The Truth",
        ),
        (
            f"Here's the first thing that will surprise you about {topic.lower()}.",
            f"close-up detailed visual representing {topic}, professional photography, 9:16",
            "Fact #1",
        ),
        (
            f"But it gets even more interesting when you dig deeper into {topic.lower()}.",
            f"dynamic action scene about {topic}, golden hour lighting, vertical frame",
            "Go Deeper",
        ),
        (
            f"Experts say understanding {topic.lower()} can completely change your perspective.",
            f"inspiring wide angle shot of {topic}, epic atmosphere, portrait orientation",
            "Mind Blown",
        ),
        (
            f"Follow for more — and tell us what you think about {topic.lower()}!",
            f"striking final hero image of {topic}, bold colors, vertical cinematic poster",
            "Follow Us",
        ),
    ]

    scenes = [
        Scene(narration=n, visual_prompt=v, on_screen_text=t)
        for n, v, t in templates
    ]

    tag_base = re.sub(r"[^a-zA-Z0-9]", "", topic.split()[0].lower())[:20] or "facts"
    hashtags = [tag_base, "shorts", "viral", "didyouknow", "fyp"]

    return ShortScript(title=title, hook=hook, scenes=scenes, hashtags=hashtags)


async def _try_ollama(settings: Settings, prompt: str) -> ShortScript | None:
    payload = {
        "model": settings.ollama_model,
        "prompt": f"{SYSTEM_PROMPT}\n\nTopic: {prompt}",
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.85},
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ollama_url}/api/generate",
                json=payload,
            )
            if response.status_code != 200:
                return None

            data = response.json()
            raw = data.get("response", "")
            if not raw:
                return None

            parsed = json.loads(raw)
            script = ShortScript.model_validate(parsed)
            if len(script.scenes) < 3:
                return None
            return script
    except Exception:
        return None


async def generate_script(
    settings: Settings,
    prompt: str,
    on_status: Callable[[str], None] | None = None,
) -> tuple[ShortScript, str]:
    if on_status:
        on_status("Writing script with local AI (Ollama)...")

    script = await _try_ollama(settings, prompt)
    if script:
        return script, "ollama"

    if on_status:
        on_status("Ollama unavailable — using built-in script templates...")

    return _build_fallback_script(prompt), "template"
