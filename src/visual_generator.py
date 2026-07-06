import hashlib
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import httpx
from PIL import Image, ImageDraw, ImageFont

from src.config import Settings


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _palette(seed: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    digest = hashlib.sha256(seed.encode()).digest()
    base = tuple(digest[i] % 156 + 40 for i in range(3))
    accent = tuple(min(255, c + 80) for c in base)
    dark = tuple(max(0, c - 30) for c in base)
    return base, accent, dark


def _draw_gradient(img: Image.Image, c1: tuple[int, int, int], c2: tuple[int, int, int]) -> None:
    draw = ImageDraw.Draw(img)
    w, h = img.size
    for y in range(h):
        t = y / max(h - 1, 1)
        color = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=color)


def _draw_decorations(draw: ImageDraw.ImageDraw, w: int, h: int, accent: tuple[int, int, int]) -> None:
    for i in range(6):
        radius = 120 + i * 90
        alpha_color = (*accent, 30 + i * 8)
        bbox = [
            w // 2 - radius,
            h // 3 - radius // 2,
            w // 2 + radius,
            h // 3 + radius // 2,
        ]
        draw.ellipse(bbox, outline=accent, width=2)


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []

    for word in words:
        trial = " ".join(current + [word])
        bbox = font.getbbox(trial)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines or [text]


def create_slide_image(
    settings: Settings,
    visual_prompt: str,
    on_screen_text: str,
    output_path: Path,
    *,
    scene_index: int = 0,
) -> Path:
    w, h = settings.video_width, settings.video_height
    base, accent, dark = _palette(visual_prompt)

    img = Image.new("RGB", (w, h))
    _draw_gradient(img, dark, base)
    draw = ImageDraw.Draw(img)
    _draw_decorations(draw, w, h, accent)

    title_font = _font(max(52, w // 14), bold=True)
    sub_font = _font(max(32, w // 26))

    headline = on_screen_text.strip() or visual_prompt.split(",")[0][:40]
    lines = _wrap_text(headline, title_font, w - 120)
    y = h // 2 - len(lines) * 40
    for line in lines:
        bbox = title_font.getbbox(line)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2, y), line, font=title_font, fill=(255, 255, 255))
        y += bbox[3] - bbox[1] + 12

    badge = f"Scene {scene_index + 1}"
    badge_font = _font(28, bold=True)
    pad = 20
    bb = badge_font.getbbox(badge)
    bw, bh = bb[2] - bb[0] + pad * 2, bb[3] - bb[1] + pad * 2
    draw.rounded_rectangle(
        (w // 2 - bw // 2, h - bh - 80, w // 2 + bw // 2, h - 80),
        radius=16,
        fill=(*accent,),
    )
    draw.text((w // 2, h - 80 - bh // 2), badge, font=badge_font, fill=(255, 255, 255), anchor="mm")

    snippet = visual_prompt[:90] + ("..." if len(visual_prompt) > 90 else "")
    sub_lines = _wrap_text(snippet, sub_font, w - 160)
    sy = h // 2 + 40
    for line in sub_lines[:3]:
        bbox = sub_font.getbbox(line)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2, sy), line, font=sub_font, fill=(220, 220, 230))
        sy += bbox[3] - bbox[1] + 8

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")
    return output_path


async def fetch_pollinations_image(
    settings: Settings,
    prompt: str,
    output_path: Path,
) -> bool:
    encoded = quote(
        f"{prompt}. Vertical 9:16 cinematic photo, high quality, no text, no watermark."
    )
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={settings.video_width}&height={settings.video_height}&nologo=true&seed={hash(prompt) % 99999}"
    )

    try:
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code != 200 or len(response.content) < 1000:
                return False

            image = Image.open(BytesIO(response.content)).convert("RGB")
            image = image.resize(
                (settings.video_width, settings.video_height),
                Image.Resampling.LANCZOS,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(output_path, format="PNG")
            return True
    except Exception:
        return False


def add_text_overlay(
    image_path: Path,
    text: str,
    output_path: Path,
    *,
    width: int,
    height: int,
) -> Path:
    if not text.strip():
        output_path.write_bytes(image_path.read_bytes())
        return output_path

    img = Image.open(image_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Premium large bold font
    font_size = max(56, width // 16)
    font = _font(font_size, bold=True)

    # Convert text to uppercase for impact
    text_upper = text.strip().upper()

    margin = width // 10
    lines = _wrap_text(text_upper, font, width - margin * 2)
    
    # Calculate line heights and total height
    line_heights = []
    for line in lines:
        bbox = font.getbbox(line)
        line_heights.append(bbox[3] - bbox[1])
    
    total_h = sum(line_heights) + (len(lines) - 1) * 12
    
    # Position in the sweet spot (60% down the screen)
    y = int(height * 0.60) - total_h // 2

    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        lw = bbox[2] - bbox[0]
        # Yellow accent for the last line, white for others
        # Thick black outline for readability (stroke_width=6)
        fill_color = (255, 235, 59, 255) if i == len(lines) - 1 else (255, 255, 255, 255)
        draw.text(
            ((width - lw) // 2, y),
            line,
            font=font,
            fill=fill_color,
            stroke_width=6,
            stroke_fill=(0, 0, 0, 255),
        )
        y += line_heights[i] + 12

    combined = Image.alpha_composite(img, overlay).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.save(output_path, format="PNG")
    return output_path


async def generate_image(
    settings: Settings,
    visual_prompt: str,
    on_screen_text: str,
    output_path: Path,
    *,
    scene_index: int = 0,
    use_online_images: bool = True,
) -> tuple[Path, str]:
    raw_path = output_path.with_name(output_path.stem + "_raw.png")

    if use_online_images:
        ok = await fetch_pollinations_image(settings, visual_prompt, raw_path)
        if ok:
            final = add_text_overlay(
                raw_path, on_screen_text, output_path, width=settings.video_width, height=settings.video_height
            )
            return final, "pollinations"

    create_slide_image(
        settings, visual_prompt, on_screen_text, raw_path, scene_index=scene_index
    )
    final = add_text_overlay(
        raw_path, on_screen_text, output_path, width=settings.video_width, height=settings.video_height
    )
    return final, "local"
