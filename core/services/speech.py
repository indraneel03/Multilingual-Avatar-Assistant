import base64
import json
import threading
from pathlib import Path

import requests
from django.conf import settings

from core.services.ai import openai_client
from core.services.language_avatar import language_to_bcp47, tts_speaker_for_language


SARVAM_WEBHOOK_LOCK = threading.Lock()
SARVAM_WEBHOOK_EVENTS: dict[str, threading.Event] = {}
SARVAM_WEBHOOK_RESULTS: dict[str, dict] = {}


def sarvam_headers() -> dict:
    if not settings.SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is missing.")
    return {"api-subscription-key": settings.SARVAM_API_KEY}


def extract_sarvam_audio_b64(payload: dict) -> str:
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
        return extract_sarvam_audio_b64(result)
    return ""


def extract_sarvam_transcript(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ["transcript", "text", "output_text", "result_text"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    result = payload.get("result")
    if isinstance(result, dict):
        return extract_sarvam_transcript(result)
    return ""


def extract_sarvam_language(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ["language_code", "language", "detected_language", "lang"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    result = payload.get("result")
    if isinstance(result, dict):
        return extract_sarvam_language(result)
    return ""


def extract_sarvam_request_id(payload: dict) -> str:
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


def wait_for_sarvam_webhook(request_id: str, timeout_sec: float) -> dict | None:
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


def register_sarvam_webhook_payload(payload: dict) -> str:
    request_id = extract_sarvam_request_id(payload)
    if not request_id:
        raise RuntimeError("Missing request_id")
    with SARVAM_WEBHOOK_LOCK:
        SARVAM_WEBHOOK_RESULTS[request_id] = payload
        event = SARVAM_WEBHOOK_EVENTS.get(request_id)
        if event is None:
            event = threading.Event()
            SARVAM_WEBHOOK_EVENTS[request_id] = event
        event.set()
    return request_id


def transcribe_audio(audio_path: Path, language_hint: str, mime_type: str = "audio/webm", request_id: str = "") -> tuple[str, str]:
    if settings.STT_PROVIDER.lower() == "sarvam":
        data = {
            "model": settings.SARVAM_STT_MODEL,
            "with_timestamps": "false",
            "mode": settings.SARVAM_STT_MODE,
        }
        if language_hint:
            data["language_code"] = language_to_bcp47(language_hint)
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
                headers=sarvam_headers(),
                data=data,
                files=files,
                timeout=settings.SARVAM_REQUEST_TIMEOUT_SEC,
            )

        if response.status_code >= 400:
            raise RuntimeError(f"Sarvam STT failed: {response.status_code} {response.text}")
        payload = response.json()
        webhook_result = None
        text = extract_sarvam_transcript(payload)
        if webhook_mode and not text:
            webhook_result = wait_for_sarvam_webhook(request_id, settings.SARVAM_STT_WEBHOOK_WAIT_SEC)
            if webhook_result:
                text = extract_sarvam_transcript(webhook_result)
        detected_language = extract_sarvam_language(payload) or language_hint or "en"
        if webhook_result:
            detected_language = extract_sarvam_language(webhook_result) or detected_language
        return text, detected_language

    client = openai_client()
    with audio_path.open("rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model=settings.OPENAI_STT_MODEL,
            file=audio_file,
            language=language_hint or None,
        )
    return (getattr(transcript, "text", "") or "").strip(), getattr(transcript, "language", "") or language_hint or "en"


def synthesize_tts(
    text: str,
    output_file: Path,
    language: str = "en",
    request_id: str = "",
    speaker_override: str | None = None,
) -> str:
    if settings.TTS_PROVIDER.lower() == "sarvam":
        payload = {
            "model": settings.SARVAM_TTS_MODEL,
            "speaker": speaker_override or tts_speaker_for_language(language),
            "target_language_code": language_to_bcp47(language),
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
            headers={**sarvam_headers(), "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=settings.SARVAM_REQUEST_TIMEOUT_SEC,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Sarvam TTS failed: {response.status_code} {response.text}")
        result = response.json()
        audio_b64 = extract_sarvam_audio_b64(result)
        if not audio_b64 and webhook_mode:
            webhook_result = wait_for_sarvam_webhook(request_id, settings.SARVAM_WEBHOOK_WAIT_SEC)
            if webhook_result:
                audio_b64 = extract_sarvam_audio_b64(webhook_result)
        if not audio_b64:
            raise RuntimeError("Sarvam TTS returned no audio data.")
        output_file.write_bytes(base64.b64decode(audio_b64))
        return "sarvam"

    client = openai_client()
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
