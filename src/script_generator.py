import asyncio
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


def _extract_topic(prompt: str) -> str:
    topic = prompt.strip().rstrip("।.")
    if not topic:
        return "shorts"

    match = re.search(
        r"(?i)(?:\b(?:interesting\s+facts\s+about|facts\s+about|fact\s+about|about|ke\s+baare\s+mein)\b)\s*(.*)$",
        topic,
    )
    if match:
        extracted = match.group(1).strip()
        if extracted:
            topic = extracted

    cleaned = re.sub(r"[^a-zA-Z0-9\u0900-\u097F ]+", "", topic)
    cleaned = re.sub(r"\b(interesting|facts|fact|about|ke|baare|mein)\b", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned or "shorts"


def _build_hindi_fallback_script(prompt: str) -> ShortScript:
    safe_topic = _extract_topic(prompt)
    hook = f"Ruko! {safe_topic} ke baare mein 5 aise facts jo aap soch bhi nahi sakte."
    title = f"{safe_topic} ke 5 chonkane wale facts"

    scene_templates = [
        (
            f"Pehla fact: {safe_topic} se judi ek choti si baat jo sabko hairaan kar degi.",
            f"realistic photo of a modern Indian city street scene about {safe_topic}, cinematic 9:16, warm lighting, photorealistic, no text",
            "Pehla fact",
        ),
        (
            f"Doosra fact: yeh baat sabko nahi pata hoti, lekin iska asar har jagah hota hai.",
            f"cinematic portrait of a young Indian person reflecting on {safe_topic}, vertical 9:16, realistic photography, no text",
            "Doosra fact",
        ),
        (
            f"Teesra fact: sach yeh hai ki {safe_topic} bahut zyada important hai, aur log ise ignore karte hain.",
            f"realistic photo of Indian people reacting in surprise to {safe_topic}, dramatic lighting, 9:16 vertical, no text",
            "Sach bataun?",
        ),
        (
            f"Chautha fact: experts kehte hain ki {safe_topic} ko samajhna har ek ke liye useful hai.",
            f"cinematic scene of an Indian expert explaining {safe_topic} in a modern studio, vertical 9:16, photorealistic, no text",
            "Dhyan do",
        ),
        (
            f"Ant mein: ab aap {safe_topic} ke baare mein kuch naya jaante ho. Share karna mat bhoolna.",
            f"vibrant celebration image of young Indian creators sharing a short video, 9:16, cinematic, no text",
            "Share karo",
        ),
    ]

    scenes = [Scene(narration=n, visual_prompt=v, on_screen_text=t) for n, v, t in scene_templates]
    topic_slug = re.sub(r"[^a-zA-Z0-9\u0900-\u097F]", "", safe_topic.split()[0])[:20] or "shorts"
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
        # Reasoning-style backends (e.g. gpt-oss-20b) can spend most of the
        # completion budget on a hidden `reasoning` field and never emit
        # `content` if this is too low. Give it plenty of headroom.
        "max_tokens": 3000,
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        for attempt in range(1, 4):
            try:
                response = await client.post(POLLINATIONS_API, json=payload)
                print("🚀 ~ _try_pollinations ~ response:", response)

                if response.status_code == 200:
                    data = response.json()
                    print("🚀 ~ _try_pollinations ~ data:", data)

                    try:
                        choice = data["choices"][0]
                        message = choice.get("message", {})
                        finish_reason = choice.get("finish_reason")
                    except (KeyError, IndexError, TypeError) as exc:
                        print(f"Pollinations malformed response shape: {exc}")
                        if on_status:
                            on_status("Unexpected response shape, retrying...")
                        if attempt < 3:
                            await asyncio.sleep(attempt * 2)
                            continue
                        return None

                    raw = message.get("content")

                    # Some backends dump everything into `reasoning` and
                    # truncate before ever writing `content`. Don't try to
                    # parse `reasoning` as JSON — it's free-form chain of
                    # thought, not structured output. Just retry.
                    if not raw:
                        reason_note = " (hit token limit while reasoning)" if finish_reason == "length" else ""
                        print(f"Pollinations returned empty content{reason_note}")
                        if on_status:
                            on_status(f"Empty response from model{reason_note}, retrying...")
                        if attempt < 3:
                            await asyncio.sleep(attempt * 2)
                            continue
                        return None

                    try:
                        parsed = _extract_json(raw)
                        script = ShortScript.model_validate(parsed)
                    except (ValueError, json.JSONDecodeError) as exc:
                        print(f"Pollinations JSON/validation error: {exc}")
                        if on_status:
                            on_status("Malformed script from model, retrying...")
                        if attempt < 3:
                            await asyncio.sleep(attempt * 2)
                            continue
                        return None

                    if len(script.scenes) < 3:
                        if on_status:
                            on_status("Incomplete script from model, retrying...")
                        if attempt < 3:
                            await asyncio.sleep(attempt * 2)
                            continue
                        return None

                    return script

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after and retry_after.isdigit() else attempt * 3
                    if on_status:
                        on_status(f"Queue full at Pollinations, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue

                if on_status:
                    on_status(f"Pollinations returned {response.status_code}, fallback kar rahe hain...")
                return None

            except (httpx.ReadTimeout, httpx.ConnectError, httpx.RequestError) as exc:
                if attempt < 3:
                    if on_status:
                        on_status(f"Pollinations request failed, retrying... ({attempt}/3)")
                    await asyncio.sleep(attempt * 2)
                    continue
                print(f"Pollinations API error: {exc}")
                return None
            except Exception as exc:
                print(f"Pollinations API error: {exc}")
                return None
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