import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-secret-key")
DEBUG = os.getenv("DEBUG", "1") == "1"
ALLOWED_HOSTS = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "*").split(",") if host.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "avatar_assistant.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "avatar_assistant.wsgi.application"
ASGI_APPLICATION = "avatar_assistant.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_STT_MODEL = os.getenv("OPENAI_STT_MODEL", "whisper-1")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "alloy")
OPENAI_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "64"))
VOICE_REPLY_MAX_CHARS = int(os.getenv("VOICE_REPLY_MAX_CHARS", "120"))
LLM_HISTORY_TURNS = int(os.getenv("LLM_HISTORY_TURNS", "8"))

STT_PROVIDER = os.getenv("STT_PROVIDER", "sarvam")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "sarvam")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
SARVAM_API_BASE = os.getenv("SARVAM_API_BASE", "https://api.sarvam.ai")
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
SARVAM_STT_MODE = os.getenv("SARVAM_STT_MODE", "transcribe")
SARVAM_STT_WEBHOOK_ENABLED = os.getenv("SARVAM_STT_WEBHOOK_ENABLED", "0") == "1"
SARVAM_STT_WEBHOOK_URL = os.getenv("SARVAM_STT_WEBHOOK_URL", "")
SARVAM_STT_WEBHOOK_SECRET = os.getenv("SARVAM_STT_WEBHOOK_SECRET", "")
SARVAM_STT_WEBHOOK_WAIT_SEC = float(os.getenv("SARVAM_STT_WEBHOOK_WAIT_SEC", "12"))
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
SARVAM_TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "pooja")
SARVAM_TTS_SPEAKER_ENGLISH = os.getenv("SARVAM_TTS_SPEAKER_ENGLISH", SARVAM_TTS_SPEAKER)
SARVAM_TTS_SPEAKER_NORTH = os.getenv("SARVAM_TTS_SPEAKER_NORTH", SARVAM_TTS_SPEAKER)
SARVAM_TTS_SPEAKER_SOUTH = os.getenv("SARVAM_TTS_SPEAKER_SOUTH", SARVAM_TTS_SPEAKER)
SARVAM_TTS_PACE = float(os.getenv("SARVAM_TTS_PACE", "1.0"))
SARVAM_TTS_TEMPERATURE = float(os.getenv("SARVAM_TTS_TEMPERATURE", "0.6"))
SARVAM_TTS_AUDIO_CODEC = os.getenv("SARVAM_TTS_AUDIO_CODEC", "mp3")
SARVAM_WEBHOOK_ENABLED = os.getenv("SARVAM_WEBHOOK_ENABLED", "0") == "1"
SARVAM_WEBHOOK_URL = os.getenv("SARVAM_WEBHOOK_URL", "")
SARVAM_WEBHOOK_SECRET = os.getenv("SARVAM_WEBHOOK_SECRET", "")
SARVAM_WEBHOOK_WAIT_SEC = float(os.getenv("SARVAM_WEBHOOK_WAIT_SEC", "12"))

LLM_SYSTEM_PROMPT = os.getenv(
    "LLM_SYSTEM_PROMPT",
    "You are a helpful multilingual avatar assistant. Reply naturally and clearly in the same language as the user. "
    "For spoken avatar output, keep answers concise by default: 1-2 short sentences unless the user explicitly asks for detail.",
)

LIPSYNC_ENGINE = os.getenv("LIPSYNC_ENGINE", "musetalk")
NON_LIPSYNC_FORCE_CPU = os.getenv("NON_LIPSYNC_FORCE_CPU", "0") == "1"
LIPSYNC_GPU_ID = int(os.getenv("LIPSYNC_GPU_ID", "0"))
SADTALKER_PATH = os.getenv("SADTALKER_PATH", "")
SADTALKER_PYTHON = os.getenv("SADTALKER_PYTHON", str(BASE_DIR / ".venv_sadtalker" / "Scripts" / "python.exe"))
SADTALKER_DIR = os.getenv("SADTALKER_DIR", str(BASE_DIR / ".models" / "SadTalker"))
SADTALKER_GITHUB_URL = os.getenv("SADTALKER_GITHUB_URL", "https://github.com/OpenTalker/SadTalker.git")
SADTALKER_AUTO_SETUP = os.getenv("SADTALKER_AUTO_SETUP", "1") == "1"
SADTALKER_EXTRA_ARGS = os.getenv("SADTALKER_EXTRA_ARGS", "--still --preprocess crop --size 256")
MUSE_TALK_DIR = os.getenv("MUSE_TALK_DIR", str(BASE_DIR / ".models" / "MuseTalk"))
MUSE_TALK_PYTHON = os.getenv("MUSE_TALK_PYTHON", str(BASE_DIR / ".venv_musetalk" / "Scripts" / "python.exe"))
MUSE_TALK_GPU_ID = int(os.getenv("MUSE_TALK_GPU_ID", "0"))
MUSE_TALK_VERSION = os.getenv("MUSE_TALK_VERSION", "v15")
MUSE_TALK_BATCH_SIZE = int(os.getenv("MUSE_TALK_BATCH_SIZE", "8"))
MUSE_TALK_FPS = int(os.getenv("MUSE_TALK_FPS", "25"))
MUSE_TALK_USE_FLOAT16 = os.getenv("MUSE_TALK_USE_FLOAT16", "1") == "1"
MUSE_TALK_EXTRA_MARGIN = int(os.getenv("MUSE_TALK_EXTRA_MARGIN", "10"))
MUSE_TALK_USE_SAVED_COORD = os.getenv("MUSE_TALK_USE_SAVED_COORD", "1") == "1"
MUSE_TALK_SAVE_COORD = os.getenv("MUSE_TALK_SAVE_COORD", "1") == "1"
MUSE_TALK_FFMPEG_PATH = os.getenv("MUSE_TALK_FFMPEG_PATH", "")
MUSE_TALK_PERSISTENT_WORKER = os.getenv("MUSE_TALK_PERSISTENT_WORKER", "1") == "1"
MUSE_TALK_MULTI_AVATAR_POOL = os.getenv("MUSE_TALK_MULTI_AVATAR_POOL", "1") == "1"
MUSE_TALK_WORKER_TIMEOUT_SEC = int(os.getenv("MUSE_TALK_WORKER_TIMEOUT_SEC", "120"))
MUSE_TALK_FAST_BATCH_SIZE = int(os.getenv("MUSE_TALK_FAST_BATCH_SIZE", "4"))
MUSE_TALK_FAST_FPS = int(os.getenv("MUSE_TALK_FAST_FPS", "20"))
MUSE_TALK_USE_FAST_PROFILE = os.getenv("MUSE_TALK_USE_FAST_PROFILE", "1") == "1"
MUSE_TALK_AUDIO_PADDING_LEFT = int(os.getenv("MUSE_TALK_AUDIO_PADDING_LEFT", "1"))
MUSE_TALK_AUDIO_PADDING_RIGHT = int(os.getenv("MUSE_TALK_AUDIO_PADDING_RIGHT", "1"))

DEFAULT_AVATAR_IMAGE = os.getenv("DEFAULT_AVATAR_IMAGE", "static/core/default-avatar-woman.png")
DEFAULT_AVATAR_VIDEO = os.getenv("DEFAULT_AVATAR_VIDEO", "static/core/Realistic_Avatar_Video_Generation.mp4")
AVATAR_VIDEO_ENGLISH = os.getenv("AVATAR_VIDEO_ENGLISH", DEFAULT_AVATAR_VIDEO)
AVATAR_VIDEO_NORTH = os.getenv("AVATAR_VIDEO_NORTH", DEFAULT_AVATAR_VIDEO)
AVATAR_VIDEO_SOUTH = os.getenv("AVATAR_VIDEO_SOUTH", DEFAULT_AVATAR_VIDEO)
AUTO_MODEL_WARMUP = os.getenv("AUTO_MODEL_WARMUP", "1") == "1"
