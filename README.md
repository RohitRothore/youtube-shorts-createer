# YouTube Short Creator

Generate vertical YouTube Shorts (9:16) from a text prompt — **100% free**, no API keys, full web UI.

## Free stack

| Step | Tool | Cost |
|------|------|------|
| Script | [Ollama](https://ollama.com) (local LLM) + built-in fallback templates | Free |
| Voiceover | [edge-tts](https://github.com/rany2/edge-tts) (Microsoft Edge voices) | Free |
| Images | [Pollinations.ai](https://pollinations.ai) + local Pillow slides as fallback | Free |
| Video assembly | FFmpeg | Free |
| Web UI | FastAPI + HTML/JS | Free |

No OpenAI, no paid subscriptions, no API keys required.

## Prerequisites

- **Python 3.11+**
- **ffmpeg** — `sudo apt install ffmpeg`
- **Optional:** [Ollama](https://ollama.com) for smarter scripts — `ollama pull llama3.2`

## Setup

```bash
cd youtube-short-creater
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional — defaults work out of the box
```

## Run the web app

```bash
python run.py
```

Open **http://localhost:8000** in your browser.

### What you can do

1. Enter a prompt (topic or idea for your short)
2. Click **Generate Video** — watch live progress
3. Preview the finished 9:16 MP4 in the browser
4. **Download** the video
5. Browse **Recent Generations** and re-preview past videos

## How it works

```
Prompt → Script (Ollama or templates) → Scenes
  → Images (Pollinations or local slides)
  → Voice (edge-tts per scene)
  → FFmpeg clips with Ken Burns effect
  → Final MP4
```

Each short includes:
- A hook in the first few seconds
- 5 scenes with narration, visuals, and on-screen captions
- Title and hashtags in metadata

## Configuration (optional)

Copy `.env.example` to `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | Local Ollama server |
| `OLLAMA_MODEL` | `llama3.2` | Model for script writing |
| `TTS_VOICE` | `en-US-ChristopherNeural` | edge-tts voice |
| `VIDEO_WIDTH` | `1080` | Output width |
| `VIDEO_HEIGHT` | `1920` | Output height |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Web server |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web UI |
| `POST` | `/api/generate` | Start generation `{ "prompt": "...", "use_online_images": true }` |
| `GET` | `/api/jobs/{id}` | Poll job status & progress |
| `GET` | `/api/stream/{id}` | Stream video for preview |
| `GET` | `/api/download/{id}` | Download MP4 |
| `GET` | `/api/health` | System status (ffmpeg, Ollama) |

## Project structure

```
youtube-short-creater/
├── app.py                  # FastAPI routes
├── run.py                  # Start server
├── src/
│   ├── pipeline.py         # End-to-end orchestration + job store
│   ├── script_generator.py # Ollama + template fallback
│   ├── audio_generator.py  # edge-tts
│   ├── visual_generator.py # Pollinations + Pillow slides
│   └── video_assembler.py  # FFmpeg
├── web/
│   ├── templates/          # HTML pages
│   └── static/             # CSS & JS
└── output/                 # Generated videos (gitignored)
```

## Tips

- **Uncheck "Use free online AI images"** for faster testing (local slides only, no network).
- **Install Ollama** for much better scripts: `curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3.2`
- Generation takes 2–8 minutes depending on network (images) and CPU.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ffmpeg is not installed` | `sudo apt install ffmpeg` |
| Script quality is basic | Install Ollama and pull a model |
| Images fail / slow | Uncheck online images or retry; local slides always work |
| Port in use | Set `PORT=8080` in `.env` |
