import os
import subprocess
import sys
import threading
import time
import uuid
import json
import base64
import hashlib
import re
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from openai import OpenAI
import requests
from core.models import ChatMessage, ChatSession

MUSE_WORKER_LOCK = threading.Lock()
MUSE_WORKER_PROC: subprocess.Popen | None = None
MUSE_WORKER_AVATAR_SIGNATURE: str | None = None
MUSE_WARMUP_STARTED = False
SADTALKER_WARMUP_STARTED = False
SARVAM_WEBHOOK_LOCK = threading.Lock()
SARVAM_WEBHOOK_EVENTS: dict[str, threading.Event] = {}
SARVAM_WEBHOOK_RESULTS: dict[str, dict] = {}
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

if settings.NON_LIPSYNC_FORCE_CPU:
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"


def index(request):
    _kickoff_model_warmup()
    return render(request, "core/index.html")


def _openai_client() -> OpenAI:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing.")
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _parse_history(raw_value: str) -> list[dict]:
    value = (raw_value or "").strip()
    if not value:
        return []
    try:
        payload = json.loads(value)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    normalized: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip().lower()
        content = (item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content})
    if settings.LLM_HISTORY_TURNS > 0:
        normalized = normalized[-settings.LLM_HISTORY_TURNS :]
    return normalized


def _normalize_session_id(value: str) -> str:
    candidate = (value or "").strip()
    if SESSION_ID_RE.match(candidate):
        return candidate
    return ""


def _get_or_create_chat_session(session_id: str, language: str) -> tuple[ChatSession, str]:
    normalized = _normalize_session_id(session_id) or uuid.uuid4().hex
    session, _ = ChatSession.objects.get_or_create(
        session_id=normalized,
        defaults={"language": language or ""},
    )
    if language and session.language != language:
        session.language = language
        session.save(update_fields=["language", "updated_at"])
    return session, normalized


def _load_history_from_storage(session: ChatSession) -> list[dict]:
    if settings.LLM_HISTORY_TURNS <= 0:
        rows = ChatMessage.objects.filter(session=session).values("role", "content")
        return [{"role": row["role"], "content": row["content"]} for row in rows if row["content"]]
    # Keep last N user+assistant turns.
    max_messages = max(2, settings.LLM_HISTORY_TURNS * 2)
    rows = (
        ChatMessage.objects.filter(session=session)
        .order_by("-created_at", "-id")
        .values("role", "content")[:max_messages]
    )
    history = [{"role": row["role"], "content": row["content"]} for row in reversed(list(rows)) if row["content"]]
    return history


def _store_chat_turn(session: ChatSession, user_text: str, assistant_text: str, language: str):
    entries = []
    if (user_text or "").strip():
        entries.append(ChatMessage(session=session, role=ChatMessage.ROLE_USER, content=user_text.strip()))
    if (assistant_text or "").strip():
        entries.append(ChatMessage(session=session, role=ChatMessage.ROLE_ASSISTANT, content=assistant_text.strip()))
    if entries:
        ChatMessage.objects.bulk_create(entries)
    if language and session.language != language:
        session.language = language
        session.save(update_fields=["language", "updated_at"])



def _language_to_bcp47(code: str) -> str:
    value = (code or "").strip().lower()
    mapping = {
        "en": "en-IN",
        "hi": "hi-IN",
        "te": "te-IN",
        "ta": "ta-IN",
        "kn": "kn-IN",
        "ml": "ml-IN",
        "mr": "mr-IN",
        "gu": "gu-IN",
        "bn": "bn-IN",
        "pa": "pa-IN",
        "or": "od-IN",
    }
    return mapping.get(value, "en-IN")


def _sarvam_headers() -> dict:
    if not settings.SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is missing.")
    return {"api-subscription-key": settings.SARVAM_API_KEY}


def _extract_sarvam_audio_b64(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    audios = payload.get("audios")
    if isinstance(audios, list) and audios and isinstance(audios[0], str):
        return audios[0]
    for key in ["audio", "audio_base64", "output_audio", "data"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    result = payload.get("result")
    if isinstance(result, dict):
        return _extract_sarvam_audio_b64(result)
    return ""


def _extract_sarvam_transcript(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ["transcript", "text", "output_text", "result_text"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    result = payload.get("result")
    if isinstance(result, dict):
        return _extract_sarvam_transcript(result)
    return ""


def _extract_sarvam_language(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ["language_code", "language", "detected_language", "lang"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    result = payload.get("result")
    if isinstance(result, dict):
        return _extract_sarvam_language(result)
    return ""


def _extract_sarvam_request_id(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ["request_id", "requestId", "id", "job_id", "jobId"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    meta = payload.get("metadata")
    if isinstance(meta, dict):
        for key in ["request_id", "requestId", "id", "job_id", "jobId"]:
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _wait_for_sarvam_webhook(request_id: str, timeout_sec: float) -> dict | None:
    if not request_id:
        return None
    with SARVAM_WEBHOOK_LOCK:
        event = SARVAM_WEBHOOK_EVENTS.get(request_id)
        if event is None:
            event = threading.Event()
            SARVAM_WEBHOOK_EVENTS[request_id] = event
    ok = event.wait(timeout=max(0.1, timeout_sec))
    with SARVAM_WEBHOOK_LOCK:
        SARVAM_WEBHOOK_EVENTS.pop(request_id, None)
        result = SARVAM_WEBHOOK_RESULTS.pop(request_id, None)
    if not ok:
        return None
    return result
def transcribe_audio(audio_path: Path, language_hint: str, mime_type: str = "audio/webm", request_id: str = ""):
    if settings.STT_PROVIDER.lower() == "sarvam":
        data = {
            "model": settings.SARVAM_STT_MODEL,
            "with_timestamps": "false",
            "mode": settings.SARVAM_STT_MODE,
        }
        if language_hint:
            data["language_code"] = _language_to_bcp47(language_hint)
        webhook_mode = (
            settings.SARVAM_STT_WEBHOOK_ENABLED
            and bool(settings.SARVAM_STT_WEBHOOK_URL.strip())
            and bool(request_id)
        )
        if webhook_mode:
            data["request_id"] = request_id
            data["webhook_url"] = settings.SARVAM_STT_WEBHOOK_URL.strip()
            if settings.SARVAM_STT_WEBHOOK_SECRET.strip():
                data["metadata"] = json.dumps(
                    {
                        "request_id": request_id,
                        "webhook_secret": settings.SARVAM_STT_WEBHOOK_SECRET.strip(),
                    }
                )
        with audio_path.open("rb") as audio_file:
            files = {"file": (audio_path.name, audio_file, mime_type or "application/octet-stream")}
            response = requests.post(
                f"{settings.SARVAM_API_BASE.rstrip('/')}/speech-to-text",
                headers=_sarvam_headers(),
                data=data,
                files=files,
                timeout=120,
            )

        if response.status_code >= 400:
            raise RuntimeError(f"Sarvam STT failed: {response.status_code} {response.text}")
        payload = response.json()
        webhook_result = None
        text = _extract_sarvam_transcript(payload)
        if webhook_mode and not text:
            webhook_result = _wait_for_sarvam_webhook(request_id, settings.SARVAM_STT_WEBHOOK_WAIT_SEC)
            if webhook_result:
                text = _extract_sarvam_transcript(webhook_result)
        detected_language = _extract_sarvam_language(payload) or language_hint or "en"
        if webhook_result:
            detected_language = _extract_sarvam_language(webhook_result) or detected_language
        return text, detected_language

    client = _openai_client()
    with audio_path.open("rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model=settings.OPENAI_STT_MODEL,
            file=audio_file,
            language=language_hint or None,
        )

    text = (getattr(transcript, "text", "") or "").strip()
    detected_language = getattr(transcript, "language", "") or language_hint or "en"
    return text, detected_language
def generate_chat_reply(user_text: str, language: str, history: list[dict] | None = None):
    client = _openai_client()
    prompt = (
        f"Language: {language}\n"
        f"User query: {user_text}\n"
        "Instruction: Keep the response concise and speech-friendly (prefer <= 2 sentences)."
    )
    prior_turns = history or []

    if hasattr(client, "responses"):
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": settings.LLM_SYSTEM_PROMPT}],
            }
        ]
        for turn in prior_turns:
            messages.append(
                {
                    "role": turn["role"],
                    "content": [{"type": "text", "text": turn["content"]}],
                }
            )
        messages.append(
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        )
        response = client.responses.create(
            model=settings.OPENAI_MODEL,
            max_output_tokens=settings.OPENAI_MAX_OUTPUT_TOKENS,
            input=messages,
        )
        return response.output_text.strip()

    messages = [{"role": "system", "content": settings.LLM_SYSTEM_PROMPT}]
    for turn in prior_turns:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": prompt})

    completion = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        max_tokens=settings.OPENAI_MAX_OUTPUT_TOKENS,
        messages=messages,
    )
    return completion.choices[0].message.content.strip()


def _trim_tts_text(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= settings.VOICE_REPLY_MAX_CHARS:
        return text
    clipped = text[: settings.VOICE_REPLY_MAX_CHARS].rstrip()
    for sep in [". ", "? ", "! ", "à¥¤ ", "à¥¤", ".", "!", "?"]:
        idx = clipped.rfind(sep)
        if idx > 40:
            return clipped[: idx + (0 if sep.endswith(" ") else 1)].strip()
    return clipped + "..."


def synthesize_tts(text: str, output_file: Path, language: str = "en", request_id: str = ""):
    if settings.TTS_PROVIDER.lower() == "sarvam":
        payload = {
            "model": settings.SARVAM_TTS_MODEL,
            "speaker": settings.SARVAM_TTS_SPEAKER,
            "target_language_code": _language_to_bcp47(language),
            "inputs": [text],
            "pace": settings.SARVAM_TTS_PACE,
            "temperature": settings.SARVAM_TTS_TEMPERATURE,
            "output_audio_codec": settings.SARVAM_TTS_AUDIO_CODEC,
        }
        webhook_mode = (
            settings.SARVAM_WEBHOOK_ENABLED
            and bool(settings.SARVAM_WEBHOOK_URL.strip())
            and bool(request_id)
        )
        if webhook_mode:
            payload["request_id"] = request_id
            payload["webhook_url"] = settings.SARVAM_WEBHOOK_URL.strip()
            if settings.SARVAM_WEBHOOK_SECRET.strip():
                payload["metadata"] = {
                    "request_id": request_id,
                    "webhook_secret": settings.SARVAM_WEBHOOK_SECRET.strip(),
                }
        response = requests.post(
            f"{settings.SARVAM_API_BASE.rstrip('/')}/text-to-speech",
            headers={**_sarvam_headers(), "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=120,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Sarvam TTS failed: {response.status_code} {response.text}")
        result = response.json()
        audio_b64 = _extract_sarvam_audio_b64(result)
        if not audio_b64 and webhook_mode:
            webhook_result = _wait_for_sarvam_webhook(request_id, settings.SARVAM_WEBHOOK_WAIT_SEC)
            if webhook_result:
                audio_b64 = _extract_sarvam_audio_b64(webhook_result)
        if not audio_b64:
            raise RuntimeError("Sarvam TTS returned no audio data.")
        output_file.write_bytes(base64.b64decode(audio_b64))
        return "sarvam"

    client = _openai_client()
    try:
        with client.audio.speech.with_streaming_response.create(
            model=settings.OPENAI_TTS_MODEL,
            voice=settings.OPENAI_TTS_VOICE,
            input=text,
            format="mp3",
        ) as response:
            response.stream_to_file(str(output_file))
    except TypeError:
        with client.audio.speech.with_streaming_response.create(
            model=settings.OPENAI_TTS_MODEL,
            voice=settings.OPENAI_TTS_VOICE,
            input=text,
            response_format="mp3",
        ) as response:
            response.stream_to_file(str(output_file))
    return "openai"
def _run_command(cmd, cwd: Path | None = None, env: dict | None = None):
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if proc.returncode != 0:
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        details = "\n".join(part for part in [stdout, stderr] if part)
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(map(str, cmd))}\n{details}")


def _lipsync_env(gpu_id: int) -> dict:
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    return env


def _bootstrap_sadtalker(repo_dir: Path):
    repo_dir.parent.mkdir(parents=True, exist_ok=True)

    if not (repo_dir / ".git").exists():
        if repo_dir.exists():
            raise RuntimeError(f"SadTalker directory exists but is not a git repo: {repo_dir}")
        _run_command(["git", "clone", "--depth", "1", settings.SADTALKER_GITHUB_URL, str(repo_dir)])

    requirements = repo_dir / "requirements.txt"
    if requirements.exists():
        _run_command([sys.executable, "-m", "pip", "install", "-r", str(requirements)])

    download_scripts = [
        [sys.executable, str(repo_dir / "scripts" / "download_models.py")],
        ["cmd", "/c", str(repo_dir / "scripts" / "download_models.bat")],
    ]

    for cmd in download_scripts:
        if Path(cmd[-1]).exists():
            try:
                _run_command(cmd, cwd=repo_dir)
                break
            except Exception:
                continue


def _resolve_sadtalker_script() -> Path:
    if settings.SADTALKER_PATH:
        script = Path(settings.SADTALKER_PATH).resolve()
        if not script.exists():
            raise RuntimeError(f"SADTALKER_PATH does not exist: {script}")
        return script

    repo_dir = Path(settings.SADTALKER_DIR).resolve()
    script = (repo_dir / "inference.py").resolve()
    if script.exists():
        return script

    if not settings.SADTALKER_AUTO_SETUP:
        raise RuntimeError(
            "SadTalker is not available. Enable SADTALKER_AUTO_SETUP=1 or set SADTALKER_PATH to inference.py."
        )

    _bootstrap_sadtalker(repo_dir)
    if not script.exists():
        raise RuntimeError("SadTalker auto-setup did not produce inference.py. Check SADTALKER_DIR.")
    return script


def _resolve_sadtalker_python() -> str:
    configured = (Path(settings.SADTALKER_PYTHON).resolve() if settings.SADTALKER_PYTHON else None)
    if configured and configured.exists():
        return str(configured)
    fallback_candidates = [
        Path(settings.BASE_DIR) / ".venv_sadtalker" / "Scripts" / "python.exe",
        Path(settings.BASE_DIR) / ".venv" / "Scripts" / "python.exe",
    ]
    for candidate in fallback_candidates:
        candidate = candidate.resolve()
        if candidate.exists():
            return str(candidate)
    return sys.executable


def run_sadtalker_lipsync(avatar_image: Path, speech_audio: Path, output_video: Path):
    script = _resolve_sadtalker_script()
    python_exe = _resolve_sadtalker_python()
    repo_dir = script.parent.resolve()

    result_dir = output_video.parent / f"{output_video.stem}_sadtalker"
    result_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        python_exe,
        str(script),
        "--source_image",
        str(avatar_image),
        "--driven_audio",
        str(speech_audio),
        "--result_dir",
        str(result_dir),
    ]

    extra_args = settings.SADTALKER_EXTRA_ARGS.strip()
    if extra_args:
        cmd.extend(extra_args.split())

    _run_command(cmd, cwd=repo_dir, env=_lipsync_env(settings.LIPSYNC_GPU_ID))

    mp4_candidates = sorted(result_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp4_candidates:
        raise RuntimeError("SadTalker completed but no output mp4 was found.")

    mp4_candidates[0].replace(output_video)
    return "sadtalker"


def _resolve_musetalk_repo() -> Path:
    repo_dir = Path(settings.MUSE_TALK_DIR).resolve()
    if not repo_dir.exists():
        raise RuntimeError(f"MuseTalk directory does not exist: {repo_dir}")
    if not (repo_dir / "scripts" / "inference.py").exists():
        raise RuntimeError(f"MuseTalk inference script not found in: {repo_dir}")
    return repo_dir


def _resolve_musetalk_python() -> str:
    configured = (Path(settings.MUSE_TALK_PYTHON).resolve() if settings.MUSE_TALK_PYTHON else None)
    if configured and configured.exists():
        return str(configured)
    fallback_candidates = [
        Path(settings.BASE_DIR) / ".venv_musetalk" / "Scripts" / "python.exe",
        Path(settings.BASE_DIR) / ".venv" / "Scripts" / "python.exe",
    ]
    for candidate in fallback_candidates:
        candidate = candidate.resolve()
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _musetalk_runtime_profile() -> tuple[int, int]:
    """
    Low-latency runtime profile for faster lip-sync turnaround.
    """
    if settings.MUSE_TALK_USE_FAST_PROFILE:
        fps = max(20, settings.MUSE_TALK_FAST_FPS)
        batch_size = min(max(2, settings.MUSE_TALK_FAST_BATCH_SIZE), 6)
    else:
        fps = max(22, settings.MUSE_TALK_FPS)
        batch_size = min(max(2, settings.MUSE_TALK_BATCH_SIZE), 6)
    return fps, batch_size


def run_musetalk_lipsync(avatar_video: Path, speech_audio: Path, output_video: Path):
    if settings.MUSE_TALK_PERSISTENT_WORKER:
        try:
            return run_musetalk_lipsync_persistent(avatar_video, speech_audio, output_video)
        except Exception:
            return run_musetalk_lipsync_oneshot(avatar_video, speech_audio, output_video)
    return run_musetalk_lipsync_oneshot(avatar_video, speech_audio, output_video)


def run_musetalk_lipsync_oneshot(avatar_video: Path, speech_audio: Path, output_video: Path):
    repo_dir = _resolve_musetalk_repo()
    python_exe = _resolve_musetalk_python()
    version = (settings.MUSE_TALK_VERSION or "v15").strip().lower()
    if version not in {"v1", "v15"}:
        version = "v15"

    result_dir = output_video.parent / f"{output_video.stem}_musetalk"
    result_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = result_dir / "inference.yaml"

    cfg_path.write_text(
        (
            "task_0:\n"
            f"  video_path: \"{avatar_video.as_posix()}\"\n"
            f"  audio_path: \"{speech_audio.as_posix()}\"\n"
            "  result_name: \"output.mp4\"\n"
        ),
        encoding="utf-8",
    )

    if version == "v1":
        unet_model_path = repo_dir / "models" / "musetalk" / "pytorch_model.bin"
        unet_config_path = repo_dir / "models" / "musetalk" / "musetalk.json"
    else:
        unet_model_path = repo_dir / "models" / "musetalkV15" / "unet.pth"
        unet_config_path = repo_dir / "models" / "musetalkV15" / "musetalk.json"

    fps, batch_size = _musetalk_runtime_profile()

    cmd = [
        python_exe,
        "-X",
        "utf8",
        "-m",
        "scripts.inference",
        "--inference_config",
        str(cfg_path),
        "--result_dir",
        str(result_dir),
        "--unet_model_path",
        str(unet_model_path),
        "--unet_config",
        str(unet_config_path),
        "--whisper_dir",
        str(repo_dir / "models" / "whisper"),
        "--version",
        version,
        "--gpu_id",
        str(settings.MUSE_TALK_GPU_ID),
        "--fps",
        str(fps),
        "--batch_size",
        str(batch_size),
        "--extra_margin",
        str(settings.MUSE_TALK_EXTRA_MARGIN),
        "--audio_padding_length_left",
        str(settings.MUSE_TALK_AUDIO_PADDING_LEFT),
        "--audio_padding_length_right",
        str(settings.MUSE_TALK_AUDIO_PADDING_RIGHT),
    ]
    if settings.MUSE_TALK_USE_FLOAT16:
        cmd.append("--use_float16")
    if settings.MUSE_TALK_USE_SAVED_COORD:
        cmd.append("--use_saved_coord")
    if settings.MUSE_TALK_SAVE_COORD:
        cmd.append("--saved_coord")
    if settings.MUSE_TALK_FFMPEG_PATH.strip():
        cmd.extend(["--ffmpeg_path", settings.MUSE_TALK_FFMPEG_PATH.strip()])

    _run_command(cmd, cwd=repo_dir, env=_lipsync_env(settings.MUSE_TALK_GPU_ID))

    expected = result_dir / version / "output.mp4"
    if expected.exists():
        expected.replace(output_video)
        return "musetalk"

    mp4_candidates = sorted(result_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp4_candidates:
        raise RuntimeError("MuseTalk completed but no output mp4 was found.")
    mp4_candidates[0].replace(output_video)
    return "musetalk"


def _musetalk_job_dir() -> Path:
    job_dir = Path(settings.MEDIA_ROOT) / "musetalk_worker"
    (job_dir / "in").mkdir(parents=True, exist_ok=True)
    (job_dir / "out").mkdir(parents=True, exist_ok=True)
    (job_dir / "tmp").mkdir(parents=True, exist_ok=True)
    return job_dir


def _musetalk_avatar_signature(avatar_video: Path) -> str:
    stat = avatar_video.stat()
    payload = f"{avatar_video.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _ensure_musetalk_worker(avatar_video: Path):
    global MUSE_WORKER_PROC, MUSE_WORKER_AVATAR_SIGNATURE
    with MUSE_WORKER_LOCK:
        avatar_signature = _musetalk_avatar_signature(avatar_video)
        avatar_id = f"default_avatar_{avatar_signature}"
        if MUSE_WORKER_PROC is not None and MUSE_WORKER_PROC.poll() is None:
            if MUSE_WORKER_AVATAR_SIGNATURE == avatar_signature:
                return
            MUSE_WORKER_PROC.terminate()
            try:
                MUSE_WORKER_PROC.wait(timeout=10)
            except Exception:
                MUSE_WORKER_PROC.kill()
                MUSE_WORKER_PROC.wait(timeout=5)
            MUSE_WORKER_PROC = None
            MUSE_WORKER_AVATAR_SIGNATURE = None

        repo_dir = _resolve_musetalk_repo()
        python_exe = _resolve_musetalk_python()
        version = (settings.MUSE_TALK_VERSION or "v15").strip().lower()
        if version not in {"v1", "v15"}:
            version = "v15"
        if version == "v1":
            unet_model_path = repo_dir / "models" / "musetalk" / "pytorch_model.bin"
            unet_config_path = repo_dir / "models" / "musetalk" / "musetalk.json"
        else:
            unet_model_path = repo_dir / "models" / "musetalkV15" / "unet.pth"
            unet_config_path = repo_dir / "models" / "musetalkV15" / "musetalk.json"

        job_dir = _musetalk_job_dir()
        ready_flag = job_dir / "ready.flag"
        if ready_flag.exists():
            ready_flag.unlink()

        avatar_cache_dir = repo_dir / "results" / version / "avatars" / avatar_id
        server_preparation = not avatar_cache_dir.exists()

        fps, batch_size = _musetalk_runtime_profile()

        cmd = [
            python_exe,
            "-X",
            "utf8",
            "-m",
            "scripts.realtime_inference",
            "--server_mode",
            "--non_interactive",
            "--job_dir",
            str(job_dir),
            "--server_avatar_id",
            avatar_id,
            "--server_avatar_path",
            str(avatar_video),
            "--gpu_id",
            str(settings.MUSE_TALK_GPU_ID),
            "--version",
            version,
            "--fps",
            str(fps),
            "--batch_size",
            str(batch_size),
            "--unet_model_path",
            str(unet_model_path),
            "--unet_config",
            str(unet_config_path),
            "--whisper_dir",
            str(repo_dir / "models" / "whisper"),
            "--extra_margin",
            str(settings.MUSE_TALK_EXTRA_MARGIN),
            "--audio_padding_length_left",
            str(settings.MUSE_TALK_AUDIO_PADDING_LEFT),
            "--audio_padding_length_right",
            str(settings.MUSE_TALK_AUDIO_PADDING_RIGHT),
        ]
        if server_preparation:
            cmd.append("--server_preparation")
        if settings.MUSE_TALK_FFMPEG_PATH.strip():
            cmd.extend(["--ffmpeg_path", settings.MUSE_TALK_FFMPEG_PATH.strip()])

        MUSE_WORKER_PROC = subprocess.Popen(
            cmd,
            cwd=str(repo_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_lipsync_env(settings.MUSE_TALK_GPU_ID),
        )
        MUSE_WORKER_AVATAR_SIGNATURE = avatar_signature

        start = time.time()
        while time.time() - start < settings.MUSE_TALK_WORKER_TIMEOUT_SEC:
            if MUSE_WORKER_PROC.poll() is not None:
                raise RuntimeError("MuseTalk worker exited early.")
            if ready_flag.exists():
                return
            time.sleep(0.2)
        raise RuntimeError("MuseTalk worker did not become ready in time.")


def run_musetalk_lipsync_persistent(avatar_video: Path, speech_audio: Path, output_video: Path):
    _ensure_musetalk_worker(avatar_video)
    job_dir = _musetalk_job_dir()
    job_id = output_video.stem
    in_file = job_dir / "in" / f"{job_id}.json"
    out_file = job_dir / "out" / f"{job_id}.json"
    if out_file.exists():
        out_file.unlink()

    in_file.write_text(
        json.dumps(
            {
                "audio_path": str(speech_audio).replace("\\", "/"),
                "output_path": str(output_video).replace("\\", "/"),
            }
        ),
        encoding="utf-8",
    )

    start = time.time()
    while time.time() - start < settings.MUSE_TALK_WORKER_TIMEOUT_SEC:
        if out_file.exists():
            payload = out_file.read_text(encoding="utf-8")
            out_file.unlink(missing_ok=True)
            result = json.loads(payload)
            if result.get("ok"):
                if output_video.exists():
                    return "musetalk"
                raise RuntimeError("MuseTalk worker reported success but output video is missing.")
            raise RuntimeError(f"MuseTalk worker failed: {result.get('error') or payload}")
        time.sleep(0.1)

    raise RuntimeError("MuseTalk worker job timeout.")


def run_lipsync(model_name: str, avatar_video: Path, avatar_image: Path, speech_audio: Path, output_video: Path):
    model = (model_name or "").strip().lower()
    if model in {"none", "off", "skip"}:
        return "none"
    if model == "musetalk":
        return run_musetalk_lipsync(avatar_video, speech_audio, output_video)
    return run_sadtalker_lipsync(avatar_image, speech_audio, output_video)


def _kickoff_model_warmup():
    global MUSE_WARMUP_STARTED, SADTALKER_WARMUP_STARTED

    if settings.MUSE_TALK_PERSISTENT_WORKER and not MUSE_WARMUP_STARTED:
        with MUSE_WORKER_LOCK:
            if not MUSE_WARMUP_STARTED:
                MUSE_WARMUP_STARTED = True

                def _warmup_musetalk():
                    try:
                        _ensure_musetalk_worker(_resolve_default_avatar_video())
                    except Exception:
                        pass

                threading.Thread(target=_warmup_musetalk, daemon=True).start()

    if not SADTALKER_WARMUP_STARTED:
        SADTALKER_WARMUP_STARTED = True

        def _warmup_sadtalker():
            try:
                _resolve_sadtalker_script()
                _resolve_sadtalker_python()
            except Exception:
                pass

        threading.Thread(target=_warmup_sadtalker, daemon=True).start()


def _resolve_default_avatar_image() -> Path:
    base_dir = Path(settings.BASE_DIR)
    configured = (base_dir / settings.DEFAULT_AVATAR_IMAGE).resolve()
    fallback_candidates = [
        configured,
        (base_dir / "static" / "core" / "default-avatar-woman.png").resolve(),
        (base_dir / "static" / "core" / "default-avatar-woman.jpg").resolve(),
        (base_dir / "static" / "core" / "default-avatar.jpg").resolve(),
        (base_dir / "static" / "core" / "default-avatar.png").resolve(),
    ]
    for candidate in fallback_candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("No default avatar image found in static/core.")


def _resolve_default_avatar_video() -> Path:
    base_dir = Path(settings.BASE_DIR)
    configured = (base_dir / settings.DEFAULT_AVATAR_VIDEO).resolve()
    fallback_candidates = [
        configured,
        (base_dir / "static" / "core" / "Realistic_Avatar_Video_Generation.mp4").resolve(),
        (base_dir / "static" / "core" / "default-avatar-idle.mp4").resolve(),
    ]
    for candidate in fallback_candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("No default avatar video found in static/core.")


def _session_preview(session_id: str) -> str:
    latest_user = (
        ChatMessage.objects.filter(session__session_id=session_id, role=ChatMessage.ROLE_USER)
        .order_by("-created_at", "-id")
        .values_list("content", flat=True)
        .first()
    )
    latest_assistant = (
        ChatMessage.objects.filter(session__session_id=session_id, role=ChatMessage.ROLE_ASSISTANT)
        .order_by("-created_at", "-id")
        .values_list("content", flat=True)
        .first()
    )
    preview = (latest_user or latest_assistant or "").strip()
    if len(preview) > 72:
        return preview[:72].rstrip() + "..."
    return preview or "New chat"


def _build_frontend_history(session: ChatSession) -> list[dict]:
    rows = (
        ChatMessage.objects.filter(session=session)
        .order_by("created_at", "id")
        .values("id", "role", "content")
    )
    items = []
    for row in rows:
        if row["role"] == ChatMessage.ROLE_USER:
            items.append(
                {
                    "query_id": f"db_user_{row['id']}",
                    "transcript": row["content"],
                    "isUser": True,
                }
            )
        elif row["role"] == ChatMessage.ROLE_ASSISTANT:
            items.append(
                {
                    "query_id": f"db_assistant_{row['id']}",
                    "llm_text": row["content"],
                    "isUser": False,
                }
            )
    return items


@csrf_exempt
@require_POST
def sarvam_webhook(request):
    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    request_id = _extract_sarvam_request_id(payload)
    if not request_id:
        return JsonResponse({"ok": False, "error": "Missing request_id"}, status=400)

    if settings.SARVAM_WEBHOOK_SECRET.strip():
        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        supplied = (metadata or {}).get("webhook_secret") if isinstance(metadata, dict) else ""
        if supplied != settings.SARVAM_WEBHOOK_SECRET.strip():
            return JsonResponse({"ok": False, "error": "Invalid webhook secret"}, status=403)

    with SARVAM_WEBHOOK_LOCK:
        SARVAM_WEBHOOK_RESULTS[request_id] = payload
        event = SARVAM_WEBHOOK_EVENTS.get(request_id)
        if event is None:
            event = threading.Event()
            SARVAM_WEBHOOK_EVENTS[request_id] = event
        event.set()

    return JsonResponse({"ok": True, "request_id": request_id})


@require_GET
def history_sessions(request):
    sessions = (
        ChatSession.objects.order_by("-updated_at", "-id")
        .values("session_id", "language", "updated_at")[:100]
    )
    data = []
    for row in sessions:
        preview = _session_preview(row["session_id"])
        data.append(
            {
                "session_id": row["session_id"],
                "language": row["language"] or "",
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else "",
                "preview": preview,
            }
        )
    return JsonResponse({"sessions": data})


@require_GET
def history_session_detail(request, session_id: str):
    normalized = _normalize_session_id(session_id)
    if not normalized:
        return JsonResponse({"error": "Invalid session id."}, status=400)
    session = ChatSession.objects.filter(session_id=normalized).first()
    if not session:
        return JsonResponse({"error": "Session not found."}, status=404)
    return JsonResponse(
        {
            "session_id": session.session_id,
            "language": session.language or "",
            "history": _build_frontend_history(session),
        }
    )


@csrf_exempt
@require_POST
def avatar_query(request):
    _kickoff_model_warmup()
    media_root = Path(settings.MEDIA_ROOT)
    media_root.mkdir(parents=True, exist_ok=True)

    query_id = uuid.uuid4().hex
    requested_language = request.POST.get("language", "auto").strip().lower()
    language = "" if requested_language in {"", "auto", "detect"} else requested_language
    requested_lipsync_model = "musetalk"
    fast_voice_mode = False
    session_obj, session_id = _get_or_create_chat_session(request.POST.get("session_id", ""), language)
    history_turns = _load_history_from_storage(session_obj)
    if not history_turns:
        history_turns = _parse_history(request.POST.get("history", ""))
    text = (request.POST.get("text") or "").strip()

    audio_upload = request.FILES.get("audio")
    transcript = text
    if audio_upload is not None:
        upload_name = Path(audio_upload.name or "").suffix.lower()
        safe_suffix = upload_name if upload_name and len(upload_name) <= 8 else ".webm"
        input_audio = media_root / f"{query_id}_input{safe_suffix}"
        with input_audio.open("wb") as file_handle:
            for chunk in audio_upload.chunks():
                file_handle.write(chunk)
        transcript, language = transcribe_audio(
            input_audio,
            language,
            mime_type=(getattr(audio_upload, "content_type", "") or "audio/webm"),
            request_id=query_id,
        )

    if not transcript:
        return JsonResponse({"error": "Provide text or an audio file."}, status=400)

    try:
        request_started = time.time()
        llm_language = language or "en"
        llm_text = _trim_tts_text(generate_chat_reply(transcript, llm_language, history_turns))
        llm_done = time.time()
        _store_chat_turn(session_obj, transcript, llm_text, llm_language)

        tts_output = media_root / f"{query_id}_reply.mp3"
        tts_provider = synthesize_tts(llm_text, tts_output, language, request_id=query_id)
        tts_done = time.time()
        avatar_video_path = _resolve_default_avatar_video()
        avatar_image_path = None
        try:
            avatar_image_path = _resolve_default_avatar_image()
        except Exception:
            # Image avatar is optional in video-avatar mode.
            avatar_image_path = None

        video_output = media_root / f"{query_id}_reply.mp4"
        video_url = ""
        lipsync_engine = "none"
        warning = ""
        if not fast_voice_mode:
            try:
                if requested_lipsync_model == "musetalk":
                    lipsync_engine = run_musetalk_lipsync(avatar_video_path, tts_output, video_output)
                elif avatar_image_path is None:
                    lipsync_engine = run_musetalk_lipsync(avatar_video_path, tts_output, video_output)
                    warning = "Default avatar image missing; used MuseTalk video avatar."
                else:
                    lipsync_engine = run_lipsync(
                        requested_lipsync_model,
                        avatar_video_path,
                        avatar_image_path,
                        tts_output,
                        video_output,
                    )
                if video_output.exists():
                    video_url = f"{settings.MEDIA_URL}{video_output.name}"
            except Exception as exc:
                if requested_lipsync_model == "sadtalker":
                    try:
                        lipsync_engine = run_musetalk_lipsync(avatar_video_path, tts_output, video_output)
                        if video_output.exists():
                            video_url = f"{settings.MEDIA_URL}{video_output.name}"
                        warning = f"SadTalker failed ({exc}). Used MuseTalk fallback."
                    except Exception as fallback_exc:
                        warning = (
                            f"Lip-sync unavailable for this response. "
                            f"SadTalker error: {exc}. MuseTalk fallback error: {fallback_exc}"
                        )
                else:
                    warning = f"Lip-sync unavailable for this response: {exc}"
        lipsync_done = time.time()

        return JsonResponse(
            {
                "query_id": query_id,
                "session_id": session_id,
                "language": language,
                "transcript": transcript,
                "llm_text": llm_text,
                "tts_provider": tts_provider,
                "lipsync_engine": lipsync_engine,
                "audio_url": f"{settings.MEDIA_URL}{tts_output.name}",
                "video_url": video_url,
                "avatar_url": (f"{settings.STATIC_URL}core/{avatar_image_path.name}" if avatar_image_path else ""),
                "warning": warning,
                "timing_ms": {
                    "llm": int((llm_done - request_started) * 1000),
                    "tts": int((tts_done - llm_done) * 1000),
                    "lipsync": int((lipsync_done - tts_done) * 1000),
                    "total": int((lipsync_done - request_started) * 1000),
                },
            }
        )
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)





