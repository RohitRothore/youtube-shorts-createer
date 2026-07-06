import json
import re
from typing import Callable

import httpx

from src.config import Settings
from src.models import Scene, ShortScript

# ---------------------------------------------------------------------------
# Pollinations.ai FREE API (GPT-4o class — no key needed)
# ---------------------------------------------------------------------------
POLLINATIONS_API = "https://text.pollinations.ai/v1/chat/completions"
POLLINATIONS_MODEL = "openai"  # GPT-4o quality, free, no key

HINDI_SYSTEM_PROMPT = """You are a professional Indian YouTube Shorts script writer.
Your job is to write Shorts in Hinglish (Romanized Hindi mixed with English) that Indian audiences love.

Rules:
- Use Hinglish: prefer Romanized Hindi (e.g., "kya aap jaante ho?", "dostoon") and mix English naturally.
- Hook must grab attention in the first 2 seconds — curiosity, shock, or emotion.
- Exactly 5 scenes, each spoken ~5-8 seconds when read aloud.
- Use conversational Hinglish like "bhai", "yar", "sach mein", "jaante ho".
- Visual prompts should be in English but include Indian context (people, locations, desi setting).
- In `visual_prompt` ALWAYS specify: realistic photo, Indian setting, 9:16 vertical, cinematic lighting, photorealistic, NO text.
- `on_screen_text` in Hinglish (Roman), max 4 words, punchy caption style.
- Keep total spoken words under 130.
- 4-5 hashtags, Hindi/English mix, without the leading '#'.

Return ONLY valid JSON (no markdown, no explanation):
{
    "title": "string (Hinglish title)",
    "hook": "string (Hinglish hook - 1 punchy sentence)",
    "scenes": [
        {
            "narration": "string (natural Hinglish speech)",
            "visual_prompt": "string (English image generation prompt, Indian context)",
            "on_screen_text": "string (Hinglish caption, max 4 words)"
        }
    ],
    "hashtags": ["string"]
}"""


def _build_hindi_fallback_script(prompt: str) -> ShortScript:
    topic = prompt.strip().rstrip("।.")
    # Detect if prompt is already Hindi, otherwise wrap it
    is_hindi = any('\u0900' <= c <= '\u097F' for c in prompt)
    topic_hindi = topic if is_hindi else topic

    hook = f"Ruko! {topic_hindi} ke baare mein ye baat tum nahi jaante!"
    title = f"{topic_hindi} - Jaankar hairaan ho jaoge!"

    templates = [
        (
            f"Sach mein {topic_hindi} ke baare mein aisi baatein hain jo zyadatar log nahi jaante.",
            f"dramatic wide angle shot related to {topic}, Indian setting, golden hour, cinematic, 9:16 vertical, photorealistic, no text",
            "Sach jaante ho?",
        ),
        (
            f"Pehli baat - {topic_hindi} itni interesting hai ki tum surprise ho jaoge.",
            f"close-up dramatic reveal shot about {topic}, vibrant Indian colors, realistic photography, portrait orientation, no text",
            "Number ek!",
        ),
        (
            f"Aur isse bhi zyada chonkane wali baat - {topic_hindi} ka asar hum sabki zindagi pe padta hai.",
            f"epic cinematic scene about {topic}, India, people reacting with amazement, golden light, 9:16, no text",
            "Socho zara!",
        ),
        (
            f"Experts bhi maante hain ki {topic_hindi} ko samajhna bahut zaroori hai.",
            f"inspiring Indian expert or teacher explaining {topic}, studio background, professional lighting, vertical frame, no text",
            "Dhyan do!",
        ),
        (
            f"To doston, ab tum {topic_hindi} ke baare mein jaan gaye. Aise hi videos ke liye follow karo!",
            f"cheerful young Indian people celebrating, vibrant colors, energetic atmosphere, 9:16 cinematic, no text",
            "Follow karo!",
        ),
    ]

    scenes = [Scene(narration=n, visual_prompt=v, on_screen_text=t) for n, v, t in templates]
    topic_slug = re.sub(r"[^a-zA-Z0-9\u0900-\u097F]", "", topic.split()[0])[:20] or "shorts"
    hashtags = [topic_slug, "shorts", "viral", "india", "hinglishshorts"]
    return ShortScript(title=title, hook=hook, scenes=scenes, hashtags=hashtags)


def _extract_json(text: str) -> dict:
    """Extract JSON from response that may contain extra text."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find JSON block
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    raise ValueError("No valid JSON found in response")


async def _try_pollinations(prompt: str, on_status: Callable[[str], None] | None = None) -> ShortScript | None:
    """Use free Pollinations.ai GPT-4o API for high-quality Hinglish scripts."""
    if on_status:
        on_status("Script likhi ja rahi hai (Free AI)...")

    payload = {
        "model": POLLINATIONS_MODEL,
        "messages": [
            {"role": "system", "content": HINDI_SYSTEM_PROMPT},
            {"role": "user", "content": f"Topic: {prompt}"},
        ],
        "temperature": 0.9,
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(POLLINATIONS_API, json=payload)
            if response.status_code != 200:
                return None
            data = response.json()
            raw = data["choices"][0]["message"]["content"]
            if not raw:
                return None
            parsed = _extract_json(raw)
            script = ShortScript.model_validate(parsed)
            if len(script.scenes) < 3:
                return None
            return script
    except Exception as e:
        print(f"Pollinations API error: {e}")
        return None


async def _try_ollama(settings: Settings, prompt: str) -> ShortScript | None:
    """Fallback: local Ollama with Hinglish prompt."""
    payload = {
        "model": settings.ollama_model,
        "prompt": f"{HINDI_SYSTEM_PROMPT}\n\nTopic: {prompt}",
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.85},
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(f"{settings.ollama_url}/api/generate", json=payload)
            if response.status_code != 200:
                return None
            data = response.json()
            raw = data.get("response", "")
            if not raw:
                return None
            parsed = _extract_json(raw)
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
    # 1. Try free Pollinations.ai (best quality, no API key)
    script = await _try_pollinations(prompt, on_status=on_status)
    if script:
        return script, "pollinations-gpt4o"

    # 2. Fallback: local Ollama
    if on_status:
        on_status("Pollinations unavailable — trying local Ollama...")
    script = await _try_ollama(settings, prompt)
    if script:
        return script, "ollama"

    # 3. Last resort: built-in Hinglish templates
    if on_status:
        on_status("Using Hinglish templates...")
    return _build_hindi_fallback_script(prompt), "template-hinglish"
