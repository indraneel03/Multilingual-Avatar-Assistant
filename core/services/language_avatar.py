import re
from pathlib import Path

from django.conf import settings

from core.models import ChatSession


def normalize_lang(code: str) -> str:
    value = (code or "").strip().lower()
    if "-" in value:
        value = value.split("-")[0]
    return value


def language_to_bcp47(code: str) -> str:
    value = normalize_lang(code)
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


SOUTH_INDIAN_LANGS = {"te", "telugu", "ta", "tamil", "kn", "kannada", "ml", "malayalam", "south"}
NORTH_INDIAN_LANGS = {"hi", "hindi", "mr", "marathi", "gu", "gujarati", "bn", "bengali", "pa", "punjabi", "or", "odia", "north"}

SCRIPT_RANGES = [
    (0x0C00, 0x0C7F, "te"),
    (0x0B80, 0x0BFF, "ta"),
    (0x0C80, 0x0CFF, "kn"),
    (0x0D00, 0x0D7F, "ml"),
    (0x0900, 0x097F, "hi"),
    (0x0A80, 0x0AFF, "gu"),
    (0x0980, 0x09FF, "bn"),
    (0x0A00, 0x0A7F, "pa"),
    (0x0B00, 0x0B7F, "or"),
]

LANGUAGE_NAME_TO_CODE = {
    "telugu": "te",
    "hindi": "hi",
    "tamil": "ta",
    "kannada": "kn",
    "malayalam": "ml",
    "marathi": "mr",
    "gujarati": "gu",
    "bengali": "bn",
    "bangla": "bn",
    "punjabi": "pa",
    "odia": "or",
    "english": "en",
}

SWITCH_PATTERN = re.compile(
    r"\b(?:in|speak|talk|reply|respond|switch\s+to|use|change\s+to|convert\s+to|translate\s+to)\s+"
    + r"(" + "|".join(LANGUAGE_NAME_TO_CODE.keys()) + r")\b",
    re.IGNORECASE,
)

SWITCH_ONLY_PATTERN = re.compile(
    r"^\s*(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
    r"(?:speak|talk|reply|respond|switch\s+to|use|change\s+to|convert\s+to|translate\s+to)\s+"
    r"(?:in\s+)?(" + "|".join(LANGUAGE_NAME_TO_CODE.keys()) + r")\s*(?:please)?[\.\!\?]*\s*$",
    re.IGNORECASE,
)

SWITCH_READY_RESPONSES = {
    "en": "Hello! We can continue in English now.",
    "hi": "नमस्ते! अब हम हिंदी में आगे बात कर सकते हैं।",
    "te": "నమస్తే! ఇప్పుడు మనం తెలుగులో కొనసాగవచ్చు.",
    "ta": "வணக்கம்! இனி நாம் தமிழில் தொடரலாம்.",
    "kn": "ನಮಸ್ಕಾರ! ಈಗ ನಾವು ಕನ್ನಡದಲ್ಲಿ ಮುಂದುವರಿಯಬಹುದು.",
    "ml": "നമസ്കാരം! ഇനി നമുക്ക് മലയാളത്തില്‍ തുടരാം.",
    "mr": "नमस्कार! आता आपण मराठीत पुढे बोलू शकतो.",
    "gu": "નમસ્તે! હવે આપણે ગુજરાતીમાં આગળ વાત કરી શકીએ.",
    "bn": "নমস্কার! এখন আমরা বাংলায় এগোতে পারি।",
    "pa": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਅਸੀਂ ਹੁਣ ਪੰਜਾਬੀ ਵਿੱਚ ਅੱਗੇ ਗੱਲ ਕਰ ਸਕਦੇ ਹਾਂ।",
    "or": "ନମସ୍କାର! ଏବେ ଆମେ ଓଡିଆରେ ଆଗକୁ କଥା ହେବା।",
}


def detect_language_intent(text: str) -> str:
    if not text:
        return ""
    match = SWITCH_PATTERN.search(text)
    if match:
        return LANGUAGE_NAME_TO_CODE.get(match.group(1).lower(), "")
    stripped = text.strip().lower()
    if stripped in LANGUAGE_NAME_TO_CODE:
        return LANGUAGE_NAME_TO_CODE[stripped]
    return ""


def detect_language_from_text(text: str) -> str:
    if not text:
        return ""
    counts: dict[str, int] = {}
    for ch in text:
        codepoint = ord(ch)
        for start, end, lang in SCRIPT_RANGES:
            if start <= codepoint <= end:
                counts[lang] = counts.get(lang, 0) + 1
                break
    if not counts:
        ascii_count = sum(1 for ch in text if "a" <= ch.lower() <= "z")
        if ascii_count > len(text) * 0.3:
            return "en"
        return ""
    return max(counts, key=counts.get)


def is_switch_only_request(text: str) -> bool:
    if not text:
        return False
    stripped = (text or "").strip().lower()
    if stripped in LANGUAGE_NAME_TO_CODE:
        return True
    return bool(SWITCH_ONLY_PATTERN.match(stripped))


def avatar_group_for_language(language: str) -> str:
    lang = normalize_lang(language)
    if lang in SOUTH_INDIAN_LANGS:
        return "south"
    if lang in NORTH_INDIAN_LANGS:
        return "north"
    return "english"


def avatar_name_for_group(group: str) -> str:
    normalized = (group or "").strip().lower()
    if normalized == "south":
        return settings.AVATAR_NAME_SOUTH
    if normalized == "north":
        return settings.AVATAR_NAME_NORTH
    return settings.AVATAR_NAME_ENGLISH


def session_avatar_group(session: ChatSession | None) -> str:
    if session is None:
        return "english"
    session_language = normalize_lang(getattr(session, "language", "") or "")
    if session_language:
        return avatar_group_for_language(session_language)
    return "english"


def build_switch_text(target_group: str) -> str:
    normalized = (target_group or "").strip().lower() or "english"
    avatar_name = avatar_name_for_group(normalized)
    return f"Sure, switching to {avatar_name} now. Your assistant will take it from here."


def switch_ready_text_for_language(language: str) -> str:
    lang = normalize_lang(language) or "en"
    return SWITCH_READY_RESPONSES.get(lang, SWITCH_READY_RESPONSES["en"])


def tts_speaker_for_language(language: str) -> str:
    group = avatar_group_for_language(language)
    return tts_speaker_for_group(group)


def tts_speaker_for_group(group: str) -> str:
    normalized = (group or "").strip().lower()
    if normalized == "south":
        return settings.SARVAM_TTS_SPEAKER_SOUTH
    if normalized == "north":
        return settings.SARVAM_TTS_SPEAKER_NORTH
    return settings.SARVAM_TTS_SPEAKER_ENGLISH


def avatar_idle_video_url_for_group(group: str) -> str:
    mapping = {
        "english": settings.AVATAR_VIDEO_ENGLISH,
        "north": settings.AVATAR_VIDEO_NORTH,
        "south": settings.AVATAR_VIDEO_SOUTH,
    }
    rel_path = mapping.get(group, mapping["english"])
    return f"{settings.STATIC_URL}{rel_path.removeprefix('static/')}"


def resolve_default_avatar_video() -> Path:
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


def resolve_default_avatar_image() -> Path:
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


def resolve_avatar_video_for_language(language: str) -> Path:
    base_dir = Path(settings.BASE_DIR)
    group = avatar_group_for_language(language)
    if group == "south":
        configured = (base_dir / settings.AVATAR_VIDEO_SOUTH).resolve()
    elif group == "north":
        configured = (base_dir / settings.AVATAR_VIDEO_NORTH).resolve()
    else:
        configured = (base_dir / settings.AVATAR_VIDEO_ENGLISH).resolve()
    if configured.exists():
        return configured
    return resolve_default_avatar_video()


def resolve_avatar_video_for_group(group: str) -> Path:
    normalized = (group or "").strip().lower()
    if normalized == "south":
        return resolve_avatar_video_for_language("te")
    if normalized == "north":
        return resolve_avatar_video_for_language("hi")
    return resolve_avatar_video_for_language("en")


def configured_avatar_entries() -> list[tuple[str, Path]]:
    base_dir = Path(settings.BASE_DIR)
    mapping = [
        ("english", (base_dir / settings.AVATAR_VIDEO_ENGLISH).resolve()),
        ("north", (base_dir / settings.AVATAR_VIDEO_NORTH).resolve()),
        ("south", (base_dir / settings.AVATAR_VIDEO_SOUTH).resolve()),
    ]
    default_avatar = resolve_default_avatar_video()
    return [(group, candidate if candidate.exists() else default_avatar) for group, candidate in mapping]


def iter_configured_avatar_videos() -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for _, candidate in configured_avatar_entries():
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            found.append(candidate)
    if found:
        return found
    return [resolve_default_avatar_video()]


def preload_target_avatar_videos() -> list[Path]:
    configured = {group: path for group, path in configured_avatar_entries()}
    raw_groups = getattr(settings, "MUSE_TALK_PRELOAD_GROUPS", "english,south")
    requested_groups = [part.strip().lower() for part in raw_groups.split(",") if part.strip()]
    selected: list[Path] = []
    seen: set[str] = set()
    for group in requested_groups:
        candidate = configured.get(group)
        if candidate is None:
            continue
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        selected.append(candidate)
    if not selected:
        selected = iter_configured_avatar_videos()
    max_avatars = max(1, getattr(settings, "MUSE_TALK_MAX_VRAM_AVATARS", 2))
    return selected[:max_avatars]
