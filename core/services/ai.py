import re

from django.conf import settings
from openai import OpenAI

from core.services.language_avatar import detect_language_from_text, detect_language_intent, normalize_lang


def openai_client() -> OpenAI:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing.")
    return OpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.OPENAI_REQUEST_TIMEOUT_SEC)


def generate_chat_reply(user_text: str, language: str, history: list[dict] | None = None) -> str:
    client = openai_client()
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


LOCAL_GREETING_RESPONSES = {
    "en": "Hello! How can I help you today?",
    "hi": "नमस्ते! मैं आपकी कैसे मदद कर सकती हूँ?",
    "te": "నమస్తే! నేను మీకు ఎలా సహాయం చేయగలను?",
    "ta": "வணக்கம்! நான் உங்களுக்கு எப்படி உதவலாம்?",
    "kn": "ನಮಸ್ಕಾರ! ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?",
    "ml": "നമസ്കാരം! ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കാം?",
    "mr": "नमस्कार! मी तुमची कशी मदत करू शकते?",
    "gu": "નમસ્તે! હું તમારી કેવી રીતે મદદ કરી શકું?",
    "bn": "নমস্কার! আমি কীভাবে আপনাকে সাহায্য করতে পারি?",
    "pa": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰ ਸਕਦੀ ਹਾਂ?",
    "or": "ନମସ୍କାର! ମୁଁ ଆପଣଙ୍କୁ କିପରି ସାହାଯ୍ୟ କରିପାରିବି?",
}

LOCAL_ERROR_RESPONSES = {
    "en": "I am having trouble reaching the AI service right now. Please check the API connection and try again.",
    "hi": "अभी मैं एआई सेवा तक नहीं पहुंच पा रही हूँ। कृपया API कनेक्शन जांचकर फिर से कोशिश करें।",
    "te": "ప్రస్తుతం నేను AI సేవను చేరుకోలేకపోతున్నాను. దయచేసి API కనెక్షన్‌ను చూసి మళ్లీ ప్రయత్నించండి.",
    "ta": "இப்போது நான் AI சேவையை அணுக முடியவில்லை. API இணைப்பை சரிபார்த்து மீண்டும் முயற்சிக்கவும்.",
    "kn": "ಈಗ ನಾನು AI ಸೇವೆಯನ್ನು ಸಂಪರ್ಕಿಸಲು ಸಾಧ್ಯವಾಗುತ್ತಿಲ್ಲ. API ಸಂಪರ್ಕವನ್ನು ಪರಿಶೀಲಿಸಿ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
    "ml": "ഇപ്പോൾ എനിക്ക് AI സേവനത്തിലെത്താൻ കഴിയുന്നില്ല. API കണക്ഷൻ പരിശോധിച്ച് വീണ്ടും ശ്രമിക്കുക.",
    "mr": "सध्या मला AI सेवेशी जोडता येत नाही. कृपया API कनेक्शन तपासा आणि पुन्हा प्रयत्न करा.",
    "gu": "હમણાં હું AI સેવા સુધી પહોંચી શકતી નથી. કૃપા કરીને API કનેક્શન તપાસી ફરી પ્રયત્ન કરો.",
    "bn": "এই মুহূর্তে আমি AI পরিষেবায় পৌঁছাতে পারছি না। অনুগ্রহ করে API সংযোগ পরীক্ষা করে আবার চেষ্টা করুন।",
    "pa": "ਇਸ ਵੇਲੇ ਮੈਂ AI ਸੇਵਾ ਨਾਲ ਨਹੀਂ ਜੁੜ ਸਕਦੀ। ਕਿਰਪਾ ਕਰਕੇ API ਕਨੈਕਸ਼ਨ ਚੈਕ ਕਰਕੇ ਫਿਰ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
    "or": "ଏହି ସମୟରେ ମୁଁ AI ସେବାକୁ ପହଞ୍ଚିପାରୁନି। ଦୟାକରି API ସଂଯୋଗ ଯାଞ୍ଚ କରି ପୁଣି ଚେଷ୍ଟା କରନ୍ତୁ।",
}


def simple_greeting(text: str) -> bool:
    normalized = re.sub(r"[^a-zA-Z\u0900-\u0D7F]+", " ", (text or "").strip().lower())
    return normalized.strip() in {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good evening",
        "namaste",
        "namaskar",
        "vanakkam",
        "नमस्ते",
        "नमस्कार",
        "హాయ్",
        "నమస్తే",
        "வணக்கம்",
        "ನಮಸ್ಕಾರ",
        "നമസ്കാരം",
        "ਸਤ ਸ੍ਰੀ ਅਕਾਲ",
        "ନମସ୍କାର",
    }


def local_llm_fallback(user_text: str, language: str) -> str:
    lang = normalize_lang(language) or detect_language_intent(user_text) or detect_language_from_text(user_text) or "en"
    if simple_greeting(user_text):
        return LOCAL_GREETING_RESPONSES.get(lang, LOCAL_GREETING_RESPONSES["en"])
    return LOCAL_ERROR_RESPONSES.get(lang, LOCAL_ERROR_RESPONSES["en"])


def trim_tts_text(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= settings.VOICE_REPLY_MAX_CHARS:
        return text
    clipped = text[: settings.VOICE_REPLY_MAX_CHARS].rstrip()
    for sep in [". ", "? ", "! ", "। ", "।", ".", "!", "?"]:
        idx = clipped.rfind(sep)
        if idx > 40:
            return clipped[: idx + (0 if sep.endswith(" ") else 1)].strip()
    return clipped + "..."
