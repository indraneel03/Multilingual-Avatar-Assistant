import json
import time
import uuid
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.models import ChatSession
from core.services.ai import generate_chat_reply, local_llm_fallback, trim_tts_text
from core.services.chat_sessions import (
    build_frontend_history,
    get_or_create_chat_session,
    load_history_from_storage,
    normalize_session_id,
    parse_history,
    session_preview,
    store_chat_turn,
)
from core.services.language_avatar import (
    avatar_group_for_language,
    avatar_idle_video_url_for_group,
    build_switch_text,
    detect_language_from_text,
    detect_language_intent,
    is_switch_only_request,
    normalize_lang,
    resolve_default_avatar_image,
    resolve_avatar_video_for_language,
    session_avatar_group,
    switch_ready_text_for_language,
)
from core.services.lipsync import (
    cached_switch_clip_url,
    kickoff_model_warmup,
    musetalk_preload_status_payload,
    preload_musetalk_workers_sync,
    run_lipsync,
    run_musetalk_lipsync,
    start_musetalk_preload_thread,
)
from core.services.speech import (
    extract_sarvam_request_id,
    register_sarvam_webhook_payload,
    synthesize_tts,
    transcribe_audio,
)


def index(request):
    kickoff_model_warmup()
    return render(request, "core/index.html")


@csrf_exempt
@require_POST
def sarvam_webhook(request):
    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    request_id = extract_sarvam_request_id(payload)
    if not request_id:
        return JsonResponse({"ok": False, "error": "Missing request_id"}, status=400)

    if settings.SARVAM_WEBHOOK_SECRET.strip():
        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        supplied = (metadata or {}).get("webhook_secret") if isinstance(metadata, dict) else ""
        if supplied != settings.SARVAM_WEBHOOK_SECRET.strip():
            return JsonResponse({"ok": False, "error": "Invalid webhook secret"}, status=403)

    register_sarvam_webhook_payload(payload)
    return JsonResponse({"ok": True, "request_id": request_id})


@require_GET
def history_sessions(request):
    sessions = (
        ChatSession.objects.order_by("-updated_at", "-id")
        .values("session_id", "language", "updated_at")[:100]
    )
    data = []
    for row in sessions:
        data.append(
            {
                "session_id": row["session_id"],
                "language": row["language"] or "",
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else "",
                "preview": session_preview(row["session_id"]),
            }
        )
    return JsonResponse({"sessions": data})


@require_GET
def history_session_detail(request, session_id: str):
    normalized = normalize_session_id(session_id)
    if not normalized:
        return JsonResponse({"error": "Invalid session id."}, status=400)
    session = ChatSession.objects.filter(session_id=normalized).first()
    if not session:
        return JsonResponse({"error": "Session not found."}, status=404)
    language = normalize_lang(session.language) or ""
    avatar_group = avatar_group_for_language(language)
    return JsonResponse(
        {
            "session_id": session.session_id,
            "language": language,
            "history": build_frontend_history(session),
            "avatar_group": avatar_group,
            "avatar_idle_video_url": avatar_idle_video_url_for_group(avatar_group),
        }
    )


@csrf_exempt
@require_POST
def bootstrap_avatar(request):
    kickoff_model_warmup()
    requested_language = request.POST.get("language", "auto").strip().lower()
    session_language = "" if requested_language in {"", "auto", "detect"} else normalize_lang(requested_language)
    session_obj, session_id = get_or_create_chat_session(request.POST.get("session_id", ""), session_language)
    effective_language = session_language or normalize_lang(session_obj.language) or "en"
    avatar_group = avatar_group_for_language(effective_language)
    return JsonResponse(
        {
            "session_id": session_id,
            "language": effective_language,
            "avatar_group": avatar_group,
            "avatar_idle_video_url": avatar_idle_video_url_for_group(avatar_group),
        }
    )


@csrf_exempt
@require_POST
def musetalk_preload(request):
    sync = (request.POST.get("sync") or request.GET.get("sync") or "").strip() in {"1", "true", "yes"}
    try:
        if sync:
            preload_musetalk_workers_sync()
            payload = musetalk_preload_status_payload()
            payload["ok"] = True
            payload["mode"] = "sync"
            return JsonResponse(payload)

        started = start_musetalk_preload_thread()
        payload = musetalk_preload_status_payload()
        payload["ok"] = True
        payload["mode"] = "async"
        payload["started"] = started
        return JsonResponse(payload)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)


@require_GET
def musetalk_preload_status(request):
    return JsonResponse(musetalk_preload_status_payload())


def _switch_only_payload(
    *,
    query_id: str,
    session_id: str,
    language: str,
    transcript: str,
    llm_text: str,
    avatar_group: str,
    current_avatar_group: str,
    switch_text: str,
    warnings: list[str],
    request_started: float,
    llm_done: float,
) -> JsonResponse:
    switch_video_url = ""
    lipsync_engine = "none"
    switch_started = time.time()
    if switch_text:
        try:
            switch_video_url = cached_switch_clip_url(current_avatar_group, avatar_group, switch_text)
            lipsync_engine = "musetalk"
        except Exception as exc:
            warnings.append(f"Avatar switch prelude unavailable: {exc}")
    switch_done = time.time()
    return JsonResponse(
        {
            "query_id": query_id,
            "session_id": session_id,
            "language": language,
            "transcript": transcript,
            "llm_text": llm_text,
            "tts_provider": "",
            "lipsync_engine": lipsync_engine,
            "audio_url": "",
            "switch_text": switch_text,
            "switch_from_group": current_avatar_group,
            "switch_to_group": avatar_group,
            "prelude_video_url": "",
            "video_url": switch_video_url,
            "avatar_url": "",
            "avatar_group": avatar_group,
            "avatar_idle_video_url": avatar_idle_video_url_for_group(avatar_group),
            "warning": " ".join(warnings),
            "timing_ms": {
                "llm": int((llm_done - request_started) * 1000),
                "tts": 0,
                "lipsync": int((switch_done - switch_started) * 1000),
                "total": int((switch_done - request_started) * 1000),
            },
        }
    )


@csrf_exempt
@require_POST
def avatar_query(request):
    kickoff_model_warmup()
    media_root = Path(settings.MEDIA_ROOT)
    media_root.mkdir(parents=True, exist_ok=True)

    query_id = uuid.uuid4().hex
    requested_language = request.POST.get("language", "auto").strip().lower()
    language = "" if requested_language in {"", "auto", "detect"} else normalize_lang(requested_language)
    requested_lipsync_model = (request.POST.get("lipsync_model") or settings.LIPSYNC_ENGINE or "musetalk").strip().lower()
    session_obj, session_id = get_or_create_chat_session(request.POST.get("session_id", ""), language)
    current_avatar_group = session_avatar_group(session_obj)
    history_turns = load_history_from_storage(session_obj)
    if not history_turns:
        history_turns = parse_history(request.POST.get("history", ""))

    transcript = (request.POST.get("text") or "").strip()
    audio_upload = request.FILES.get("audio")
    if audio_upload is not None:
        upload_name = Path(audio_upload.name or "").suffix.lower()
        safe_suffix = upload_name if upload_name and len(upload_name) <= 8 else ".webm"
        input_audio = media_root / f"{query_id}_input{safe_suffix}"
        with input_audio.open("wb") as handle:
            for chunk in audio_upload.chunks():
                handle.write(chunk)
        transcript, language = transcribe_audio(
            input_audio,
            language,
            mime_type=(getattr(audio_upload, "content_type", "") or "audio/webm"),
            request_id=query_id,
        )
        language = normalize_lang(language)

    if not transcript:
        return JsonResponse({"error": "Provide text or an audio file."}, status=400)

    transcript_intent_language = detect_language_intent(transcript)
    if transcript_intent_language:
        language = transcript_intent_language
        print(f"[AVATAR] Intent-detected language: {language!r} from text: {transcript!r}")
    else:
        transcript_script_language = detect_language_from_text(transcript)
        if not language and transcript_script_language:
            language = transcript_script_language
            print(f"[AVATAR] Script-detected language: {language!r} from text: {transcript!r}")
        elif language == "en" and transcript_script_language and transcript_script_language != "en":
            language = transcript_script_language
            print(f"[AVATAR] Script-overrode STT language: {language!r} from text: {transcript!r}")

    switch_only_request = is_switch_only_request(transcript)

    try:
        request_started = time.time()
        llm_language = language or "en"
        warnings: list[str] = []
        llm_fallback_used = False
        print(f"[AVATAR] query_id={query_id} | language={language!r} | llm_language={llm_language!r}")

        if switch_only_request:
            llm_text = trim_tts_text(switch_ready_text_for_language(llm_language))
        else:
            try:
                llm_text = trim_tts_text(generate_chat_reply(transcript, llm_language, history_turns))
            except Exception as exc:
                llm_fallback_used = True
                llm_text = trim_tts_text(local_llm_fallback(transcript, llm_language))
                warnings.append(f"LLM fallback used because the upstream request failed: {exc}")
        llm_done = time.time()

        response_lang = detect_language_from_text(llm_text)
        if response_lang and response_lang != "en" and language in ("en", ""):
            print(f"[AVATAR] Post-LLM re-detected language: {response_lang!r} (was {language!r})")
            language = response_lang
            llm_language = language

        avatar_group = avatar_group_for_language(language or llm_language)
        switch_required = current_avatar_group != avatar_group
        switch_text = build_switch_text(avatar_group) if switch_required else ""

        store_chat_turn(session_obj, transcript, llm_text, llm_language)

        if switch_only_request:
            return _switch_only_payload(
                query_id=query_id,
                session_id=session_id,
                language=language,
                transcript=transcript,
                llm_text=llm_text,
                avatar_group=avatar_group,
                current_avatar_group=current_avatar_group,
                switch_text=switch_text,
                warnings=warnings,
                request_started=request_started,
                llm_done=llm_done,
            )

        tts_output = media_root / f"{query_id}_reply.mp3"
        tts_provider = ""
        audio_url = ""
        if llm_fallback_used:
            warnings.append("Audio and lip-sync were skipped because the app is using a local text fallback.")
        else:
            try:
                tts_provider = synthesize_tts(llm_text, tts_output, language, request_id=query_id)
                audio_url = f"{settings.MEDIA_URL}{tts_output.name}"
            except Exception as exc:
                warnings.append(f"TTS unavailable: {exc}")
        tts_done = time.time()

        avatar_video_path = resolve_avatar_video_for_language(language or llm_language)
        print(f"[AVATAR] FINAL: language={language!r} avatar_group={avatar_group!r} video={avatar_video_path.name}")

        avatar_image_path = None
        try:
            avatar_image_path = resolve_default_avatar_image()
        except Exception:
            avatar_image_path = None

        prelude_video_url = ""
        if switch_text and audio_url:
            try:
                prelude_video_url = cached_switch_clip_url(current_avatar_group, avatar_group, switch_text)
            except Exception as exc:
                warnings.append(f"Avatar switch prelude unavailable: {exc}")

        video_output = media_root / f"{query_id}_reply.mp4"
        video_url = ""
        lipsync_engine = "none"
        if audio_url:
            try:
                if requested_lipsync_model == "musetalk":
                    lipsync_engine = run_musetalk_lipsync(avatar_video_path, tts_output, video_output)
                elif avatar_image_path is None:
                    lipsync_engine = run_musetalk_lipsync(avatar_video_path, tts_output, video_output)
                    warnings.append("Default avatar image missing; used MuseTalk video avatar.")
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
                        warnings.append(f"SadTalker failed ({exc}). Used MuseTalk fallback.")
                    except Exception as fallback_exc:
                        warnings.append(
                            f"Lip-sync unavailable for this response. "
                            f"SadTalker error: {exc}. MuseTalk fallback error: {fallback_exc}"
                        )
                else:
                    warnings.append(f"Lip-sync unavailable for this response: {exc}")
        else:
            warnings.append("Lip-sync skipped because no speech audio was generated.")
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
                "audio_url": audio_url,
                "switch_text": switch_text,
                "switch_from_group": current_avatar_group,
                "switch_to_group": avatar_group,
                "prelude_video_url": prelude_video_url,
                "video_url": video_url,
                "avatar_url": (f"{settings.STATIC_URL}core/{avatar_image_path.name}" if avatar_image_path else ""),
                "avatar_group": avatar_group,
                "avatar_idle_video_url": avatar_idle_video_url_for_group(avatar_group),
                "warning": " ".join(warnings),
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
