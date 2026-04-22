# Multilingual Avatar Assistant

A real-time speech-to-speech avatar assistant built with Django + React frontend.

## What This Project Does

1. Accepts user input as typed text or microphone audio.
2. Uses STT to transcribe speech.
3. Uses LLM inference with conversation memory.
4. Generates TTS response audio.
5. Runs MuseTalk lip-sync over the configured avatar video.
6. Returns speaking avatar video + text response to the UI.
7. Auto-switches avatar persona by detected language family (English / North Indian / South Indian).

## Current Model Stack

- STT: Sarvam (`saaras:v3`) by default, OpenAI Whisper fallback path exists.
- LLM: OpenAI chat/responses API (`OPENAI_MODEL`).
- TTS: Sarvam (`bulbul:v3`) by default, OpenAI TTS fallback path exists.
- Lip-sync: MuseTalk (required path in current app flow).

## Architecture

- Backend: Django (`core/views.py`) handles STT, LLM, TTS, lip-sync orchestration.
- Frontend: React + Framer Motion (`static/core/app.js`) for avatar UI, mic, history, and chat interactions.
- Storage:
  - SQLite (default Django DB) for persistent chat sessions/messages.
  - Media folder for generated audio/video files.
- Lip-sync engine:
  - MuseTalk persistent worker mode supported for lower latency.

## Data Models (Persistent Chat History)

Defined in `core/models.py`:

- `ChatSession`
  - `session_id` (unique)
  - `language`
  - `created_at`, `updated_at`

- `ChatMessage`
  - `session` FK
  - `role` (`user`, `assistant`)
  - `content`
  - `created_at`

This enables long-term conversation dependency across requests and reloads.

## API Endpoints

- `POST /api/query/`
  - Main inference endpoint (text/audio -> response text/audio/video).
- `POST /api/musetalk/preload/`
  - Preload/pretrain MuseTalk avatar caches/workers for English, North, South avatars.
  - Optional `sync=1` for blocking mode.
- `GET /api/musetalk/preload/status/`
  - Check preload readiness (`cache_ready`, `worker_alive`) for each avatar group.
- `GET /api/history/sessions/`
  - List stored chat sessions for history drawer.
- `GET /api/history/session/<session_id>/`
  - Load full chat session into frontend.
- `POST /api/webhooks/sarvam/`
  - Webhook receiver for Sarvam STT/TTS async callbacks.

## Webhook Support

Optional webhook mode exists for Sarvam STT/TTS:

- STT webhook envs:
  - `SARVAM_STT_WEBHOOK_ENABLED`
  - `SARVAM_STT_WEBHOOK_URL`
  - `SARVAM_STT_WEBHOOK_SECRET`
  - `SARVAM_STT_WEBHOOK_WAIT_SEC`

- TTS webhook envs:
  - `SARVAM_WEBHOOK_ENABLED`
  - `SARVAM_WEBHOOK_URL`
  - `SARVAM_WEBHOOK_SECRET`
  - `SARVAM_WEBHOOK_WAIT_SEC`

If webhook is enabled, backend can wait for callback payload and continue flow.

## Setup

```powershell
cd "d:\avatar assistant"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

## Run

```powershell
python manage.py migrate
python manage.py runserver
```

Open:

- `http://127.0.0.1:8000`

## MuseTalk Preload (Recommended for Faster Switching)

Use terminal command (on demand):

```powershell
python manage.py preload_avatars
python manage.py preload_avatars --status
```

Or use API:

```powershell
curl -X POST http://127.0.0.1:8000/api/musetalk/preload/
curl -X POST http://127.0.0.1:8000/api/musetalk/preload/ -d "sync=1"
curl http://127.0.0.1:8000/api/musetalk/preload/status/
```

## Important Environment Variables

- Core:
  - `OPENAI_API_KEY`
  - `OPENAI_MODEL`
  - `STT_PROVIDER` (`sarvam` recommended)
  - `TTS_PROVIDER` (`sarvam` recommended)

- Sarvam:
  - `SARVAM_API_KEY`
  - `SARVAM_STT_MODEL`
  - `SARVAM_TTS_MODEL`

- MuseTalk:
  - `MUSE_TALK_DIR`
  - `MUSE_TALK_PYTHON`
  - `MUSE_TALK_VERSION`
  - `MUSE_TALK_PERSISTENT_WORKER`
  - `MUSE_TALK_USE_FAST_PROFILE`

- Avatar:
  - `DEFAULT_AVATAR_VIDEO` (currently points to `static/core/Realistic_Avatar_Video_Generation.mp4`)

## Latency Notes

- Biggest latency drivers:
  - TTS audio length
  - MuseTalk generation time
  - cold-start vs warm persistent worker
- Current project includes low-latency MuseTalk profile tuning and persistent worker mode.

## Frontend Features

- In-avatar floating controls (chat toggle, mic input control, end call).
- ChatGPT-style history drawer with session restore.
- New Chat reset flow with fresh session id.
- Premium motion UI using Framer Motion.
- Idle avatar video switches automatically based on current language avatar.

## Avatar Switching Rules

- English (`en`) -> `Micheal` avatar using:
  - `static/core/Avatar_Suit_Creation_and_Video.mp4`
- North Indian languages (`hi`, `gu`, `pa`, `mr`, `bn`, `or`, etc.) -> `Radha` avatar using:
  - `static/core/Realistic_Avatar_Video_Generation.mp4`
- South Indian languages (`te`, `ta`, `kn`, `ml`) -> `Durga` avatar using:
  - `static/core/Telugu_Avatar_Assistant_Saree_Video.mp4`

When language family changes mid-chat, assistant prepends a short switch line (for example: "I am now switching to Durga, your assistant. Namaskaram.") and then continues answer in target language.

## Disclaimer

Do not commit secrets (`.env`, API keys). The repository includes `.gitignore` rules for env files, media outputs, model caches, and local virtual environments.
