import React, { memo, useCallback, useEffect, useRef, useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
import { AnimatePresence, motion } from "https://esm.sh/framer-motion@11.11.17";
import htm from "https://esm.sh/htm@3.1.1";

const html = htm.bind(React.createElement);
const DEFAULT_IDLE_AVATAR_VIDEO = "/static/core/Avatar_Suit_Creation_and_Video_musetalk_opt.mp4";
const DEFAULT_IDLE_BY_GROUP = {
  english: "/static/core/Avatar_Suit_Creation_and_Video_musetalk_opt.mp4",
  north: "/static/core/Realistic_Avatar_Video_Generation_musetalk_opt.mp4",
  south: "/static/core/Telugu_Avatar_Assistant_Saree_Video_musetalk_opt.mp4",
};
const SESSION_STORAGE_KEY = "avatar_assistant_session_id";

/* ─── Shared animation presets ─── */
const SPRING_SOFT = { type: "spring", stiffness: 260, damping: 24 };
const SPRING_SNAPPY = { type: "spring", stiffness: 420, damping: 28 };
const EASE_OUT_EXPO = [0.16, 1, 0.3, 1];
const FADE_SLIDE_UP = {
  initial: { opacity: 0, y: 14, filter: "blur(4px)" },
  animate: { opacity: 1, y: 0, filter: "blur(0px)" },
  exit: { opacity: 0, y: -10, filter: "blur(3px)" },
};
const FADE_SLIDE_RIGHT = {
  initial: { opacity: 0, x: 24, filter: "blur(4px)" },
  animate: { opacity: 1, x: 0, filter: "blur(0px)" },
  exit: { opacity: 0, x: 28, filter: "blur(3px)" },
};
const STAGGER_CHILDREN = { staggerChildren: 0.06, delayChildren: 0.04 };

/* ─── Professional SVG Icons (stroke-based, 24×24) ─── */
const IconChat = () => html`
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>
  </svg>`;

const IconMic = () => html`
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="9" y="2" width="6" height="12" rx="3"/>
    <path d="M19 10v1a7 7 0 0 1-14 0v-1"/>
    <line x1="12" y1="19" x2="12" y2="22"/>
    <line x1="8" y1="22" x2="16" y2="22"/>
  </svg>`;

const IconMicActive = () => html`
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="9" y="2" width="6" height="12" rx="3"/>
    <path d="M19 10v1a7 7 0 0 1-14 0v-1"/>
    <line x1="12" y1="19" x2="12" y2="22"/>
    <line x1="8" y1="22" x2="16" y2="22"/>
    <circle cx="12" cy="8" r="1.5" fill="currentColor" stroke="none">
      <animate attributeName="opacity" values="1;0.3;1" dur="1.2s" repeatCount="indefinite"/>
    </circle>
  </svg>`;

const IconPhoneOff = () => html`
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7 2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-5.33-5.34A19.79 19.79 0 0 1 2.8 5.22 2 2 0 0 1 4.78 3h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 11.91"/>
    <line x1="1" y1="1" x2="23" y2="23"/>
  </svg>`;

const IconSend = () => html`
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M22 2 11 13"/>
    <path d="M22 2 15 22 11 13 2 9z"/>
  </svg>`;

const IconHistory = () => html`
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style=${{ width: "14px", height: "14px" }}>
    <circle cx="12" cy="12" r="10"/>
    <polyline points="12 6 12 12 16 14"/>
  </svg>`;

const IconPlus = () => html`
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style=${{ width: "14px", height: "14px" }}>
    <line x1="12" y1="5" x2="12" y2="19"/>
    <line x1="5" y1="12" x2="19" y2="12"/>
  </svg>`;

const LoadingDots = () => html`
  <span className="loading-dots">
    <span /><span /><span />
  </span>`;

function makeSessionId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID().replace(/-/g, "");
  return `sess_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

/* ═══════════════════ TopBar ═══════════════════ */
const TopBar = memo(function TopBar({ streaming, speaking, loading, historyOpen, onNewChat, onToggleHistory }) {
  const status = streaming ? "Listening…" : speaking ? "Speaking…" : loading ? "Thinking…" : "Ready";
  return html`
    <${motion.header}
      className="topbar"
      initial=${{ opacity: 0, y: -16 }}
      animate=${{ opacity: 1, y: 0 }}
      transition=${{ duration: 0.5, ease: EASE_OUT_EXPO }}
    >
      <${motion.div}
        className="brand"
        initial=${{ opacity: 0, x: -12 }}
        animate=${{ opacity: 1, x: 0 }}
        transition=${{ duration: 0.6, ease: EASE_OUT_EXPO, delay: 0.1 }}
      >Avatar Assistant</${motion.div}>
      <${motion.div}
        className="topbar-actions"
        initial=${{ opacity: 0, x: 12 }}
        animate=${{ opacity: 1, x: 0 }}
        transition=${{ duration: 0.6, ease: EASE_OUT_EXPO, delay: 0.15 }}
      >
        <${motion.button}
          className=${`topbar-history ${historyOpen ? "active" : ""}`}
          onClick=${onToggleHistory}
          title="Open chat history"
          whileHover=${{ scale: 1.04, y: -1 }}
          whileTap=${{ scale: 0.97 }}
          transition=${SPRING_SNAPPY}
        >
          <${IconHistory} />
          History
        </${motion.button}>
        <${motion.button}
          className="topbar-new-chat"
          onClick=${onNewChat}
          disabled=${loading}
          title="Start a new chat"
          whileHover=${{ scale: 1.04, y: -1 }}
          whileTap=${{ scale: 0.97 }}
          transition=${SPRING_SNAPPY}
        >
          <${IconPlus} />
          New Chat
        </${motion.button}>
        <${motion.div}
          className="status"
          initial=${{ opacity: 0 }}
          animate=${{ opacity: 1 }}
          transition=${{ delay: 0.3, duration: 0.5 }}
        >
          <${motion.span}
            className=${`dot ${streaming || speaking || loading ? "active" : ""}`}
            animate=${streaming || speaking || loading ? { scale: [1, 1.3, 1] } : { scale: 1 }}
            transition=${streaming || speaking || loading ? { repeat: Infinity, duration: 1.6, ease: "easeInOut" } : {}}
          />
          <${AnimatePresence} mode="wait">
            <${motion.span}
              key=${status}
              initial=${{ opacity: 0, y: 6 }}
              animate=${{ opacity: 1, y: 0 }}
              exit=${{ opacity: 0, y: -6 }}
              transition=${{ duration: 0.2 }}
            >${status}</${motion.span}>
          </${AnimatePresence}>
        </${motion.div}>
      </${motion.div}>
    </${motion.header}>
  `;
});

/* ═══════════════════ AvatarStage ═══════════════════ */
const AvatarStage = memo(function AvatarStage({
  idleVideoUrl,
  videoUrl,
  streaming,
  chatOpen,
  onToggleMic,
  onToggleChat,
  onEndCall,
  onVideoEnded,
  onVideoError,
}) {
  const isTalking = !!videoUrl;
  const idleVideoRef = useRef(null);
  useEffect(() => {
    if (isTalking || !idleVideoRef.current) return;
    const video = idleVideoRef.current;
    video.muted = true;
    video.defaultMuted = true;
    video.pause();
    const lockToFirstFrame = () => {
      try { video.currentTime = 0; } catch (_) {}
    };
    if (video.readyState >= 1) lockToFirstFrame();
    else video.addEventListener("loadedmetadata", lockToFirstFrame, { once: true });
  }, [isTalking, idleVideoUrl]);

  return html`
    <section className="avatar-stage">
      <${motion.div}
        className=${`avatar-canvas ${isTalking ? "video-mode" : "idle-mode"}`}
        initial=${{ opacity: 0, scale: 0.97, filter: "blur(6px)" }}
        animate=${{ opacity: 1, scale: 1, filter: "blur(0px)" }}
        transition=${{ duration: 0.6, ease: EASE_OUT_EXPO }}
      >
        <${motion.div}
          className="avatar-control-strip"
          initial=${{ opacity: 0, y: 20, scale: 0.92 }}
          animate=${{ opacity: 1, y: 0, scale: 1 }}
          transition=${{ duration: 0.5, ease: EASE_OUT_EXPO, delay: 0.25 }}
        >
          <${motion.button}
            className=${`avatar-control icon ${chatOpen ? "active" : ""}`}
            onClick=${onToggleChat}
            title="Toggle chat panel"
            aria-label="Toggle chat panel"
            whileHover=${{ scale: 1.12, y: -2 }}
            whileTap=${{ scale: 0.9 }}
            transition=${SPRING_SNAPPY}
          >
            <${IconChat} />
          </${motion.button}>
          <${motion.button}
            className=${`avatar-control icon ${streaming ? "active" : ""}`}
            onClick=${onToggleMic}
            title=${streaming ? "Stop microphone" : "Start microphone"}
            aria-label=${streaming ? "Stop microphone input" : "Start microphone input"}
            whileHover=${{ scale: 1.12, y: -2 }}
            whileTap=${{ scale: 0.9 }}
            transition=${SPRING_SNAPPY}
          >
            ${streaming ? html`<${IconMicActive} />` : html`<${IconMic} />`}
          </${motion.button}>
          <${motion.button}
            className="avatar-control icon end"
            onClick=${onEndCall}
            title="End current response"
            aria-label="End response"
            whileHover=${{ scale: 1.12, y: -2, rotate: -8 }}
            whileTap=${{ scale: 0.9 }}
            transition=${SPRING_SNAPPY}
          >
            <${IconPhoneOff} />
          </${motion.button}>
        </${motion.div}>
        <${AnimatePresence} mode="wait">
          ${isTalking
            ? html`
                <${motion.video}
                  key=${`talk_${videoUrl}`}
                  className="avatar-video talking"
                  src=${videoUrl}
                  autoPlay
                  playsInline
                  controls=${false}
                  onEnded=${onVideoEnded}
                  onError=${onVideoError}
                  initial=${{ opacity: 0, scale: 1.02, filter: "brightness(1.2)" }}
                  animate=${{ opacity: 1, scale: 1, filter: "brightness(1) saturate(1.06) contrast(1.01)" }}
                  exit=${{ opacity: 0, scale: 0.98, filter: "brightness(0.8)" }}
                  transition=${{ duration: 0.4, ease: EASE_OUT_EXPO }}
                ></${motion.video}>
              `
            : html`
                <${motion.video}
                  key=${`idle_${idleVideoUrl}`}
                  ref=${idleVideoRef}
                  className="avatar-video idle"
                  src=${idleVideoUrl}
                  preload="metadata"
                  playsInline
                  muted=${true}
                  controls=${false}
                  initial=${{ opacity: 0 }}
                  animate=${{ opacity: 1 }}
                  exit=${{ opacity: 0 }}
                  transition=${{ duration: 0.5 }}
                ></${motion.video}>
              `}
        </${AnimatePresence}>
      </${motion.div}>
    </section>
  `;
});

/* ═══════════════════ MessageList ═══════════════════ */
const MessageList = memo(function MessageList({ history, latestMessageRef }) {
  return html`
    <section className="chat-history">
      <${AnimatePresence} initial=${false}>
        ${history.map((item, idx) => {
          const isUser = !!item.isUser;
          const isError = !!item.isError || !!item.error;
          return html`
            <${motion.article}
              key=${item.query_id || `msg_${idx}`}
              ref=${idx === history.length - 1 ? latestMessageRef : null}
              className=${`message-row ${isUser ? "user" : "assistant"} ${isError ? "error" : ""}`}
              initial=${{ opacity: 0, y: 16, scale: 0.97, filter: "blur(3px)" }}
              animate=${{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
              exit=${{ opacity: 0, y: -12, scale: 0.97, filter: "blur(3px)" }}
              transition=${{ duration: 0.3, ease: EASE_OUT_EXPO }}
            >
              ${isUser
                ? html`<${motion.div}
                    className="bubble user-bubble"
                    initial=${{ x: 12 }}
                    animate=${{ x: 0 }}
                    transition=${SPRING_SOFT}
                  >${item.transcript}</${motion.div}>`
                : isError
                ? html`<${motion.div}
                    className="bubble error-bubble"
                    initial=${{ x: -12 }}
                    animate=${{ x: 0 }}
                    transition=${SPRING_SOFT}
                  >${item.error}</${motion.div}>`
                : html`
                    <${motion.div}
                      className="bubble assistant-bubble"
                      initial=${{ x: -12 }}
                      animate=${{ x: 0 }}
                      transition=${SPRING_SOFT}
                    >
                      ${item.llm_text}
                      ${item.warning ? html`<div className="inline-warning">${item.warning}</div>` : null}
                    </${motion.div}>
                  `}
            </${motion.article}>
          `;
        })}
      </${AnimatePresence}>
    </section>
  `;
});

/* ═══════════════════ Composer ═══════════════════ */
const Composer = memo(function Composer({
  text,
  loading,
  streaming,
  language,
  setLanguage,
  setText,
  onSubmit,
  onStartMic,
  onStopMic,
}) {
  return html`
    <${motion.footer}
      className="composer"
      initial=${{ opacity: 0, y: 16, filter: "blur(4px)" }}
      animate=${{ opacity: 1, y: 0, filter: "blur(0px)" }}
      transition=${{ duration: 0.5, ease: EASE_OUT_EXPO, delay: 0.1 }}
    >
      <${motion.div}
        className="composer-tools"
        initial=${{ opacity: 0, y: 8 }}
        animate=${{ opacity: 1, y: 0 }}
        transition=${{ duration: 0.4, ease: EASE_OUT_EXPO, delay: 0.2 }}
      >
        <label htmlFor="query-language">Language</label>
        <select id="query-language" value=${language} onChange=${(e) => setLanguage(e.target.value)}>
          <option value="auto">Auto</option>
          <option value="en">English</option>
          <option value="hi">Hindi</option>
          <option value="te">Telugu</option>
          <option value="ta">Tamil</option>
          <option value="kn">Kannada</option>
          <option value="ml">Malayalam</option>
          <option value="mr">Marathi</option>
          <option value="gu">Gujarati</option>
          <option value="bn">Bengali</option>
          <option value="pa">Punjabi</option>
          <option value="or">Odia</option>
        </select>
      </${motion.div}>
      <div className="composer-row">
        <${motion.textarea}
          placeholder="Message Avatar Assistant…"
          value=${text}
          onChange=${(e) => setText(e.target.value)}
          onKeyDown=${(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
          whileFocus=${{ boxShadow: "0 0 0 3px rgba(129,140,248,0.1), 0 4px 20px rgba(129,140,248,0.06)" }}
        />
        <${motion.button}
          className=${`icon-btn mic ${streaming ? "active" : ""}`}
          onClick=${streaming ? onStopMic : onStartMic}
          title="Microphone"
          whileHover=${{ scale: 1.06, y: -1 }}
          whileTap=${{ scale: 0.93 }}
          transition=${SPRING_SNAPPY}
        >
          ${streaming ? html`<${IconMicActive} />` : html`<${IconMic} />`}
        </${motion.button}>
        <${motion.button}
          className="icon-btn send"
          onClick=${onSubmit}
          disabled=${loading}
          title="Send"
          whileHover=${{ scale: 1.06, y: -1 }}
          whileTap=${{ scale: 0.93 }}
          transition=${SPRING_SNAPPY}
        >
          ${loading ? html`<${LoadingDots} />` : html`<${IconSend} />`}
        </${motion.button}>
      </div>
    </${motion.footer}>
  `;
});

/* ═══════════════════ App ═══════════════════ */
function App() {
  const [sessionId, setSessionId] = useState(() => {
    const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) return existing;
    const created = makeSessionId();
    window.localStorage.setItem(SESSION_STORAGE_KEY, created);
    return created;
  });
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [language, setLanguage] = useState("auto");
  const [history, setHistory] = useState([]);
  const [savedSessions, setSavedSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [audioFile, setAudioFile] = useState(null);
  const [idleVideoUrl, setIdleVideoUrl] = useState(DEFAULT_IDLE_AVATAR_VIDEO);
  const [avatarVideoUrl, setAvatarVideoUrl] = useState("");
  const ttsAudioRef = useRef(null);
  const queuedVideoRef = useRef("");

  const recorderRef = useRef(null);
  const latestMessageRef = useRef(null);

  const pickSupportedMimeType = useCallback(() => {
    if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return "";
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/ogg;codecs=opus",
    ];
    return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
  }, []);

  const fetchSavedSessions = useCallback(async () => {
    try {
      setSessionsLoading(true);
      const response = await fetch("/api/history/sessions/");
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Failed to load history.");
      setSavedSessions(Array.isArray(payload.sessions) ? payload.sessions : []);
    } catch (_) {
      setSavedSessions([]);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  const loadSession = useCallback(async (targetSessionId) => {
    try {
      const response = await fetch(`/api/history/session/${encodeURIComponent(targetSessionId)}/`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Failed to load session.");
      }
      setSessionId(payload.session_id || targetSessionId);
      if (payload.session_id) {
        window.localStorage.setItem(SESSION_STORAGE_KEY, payload.session_id);
      }
      setLanguage((payload.language || "auto").toLowerCase().split("-")[0] || "auto");
      const nextIdle = payload.avatar_idle_video_url || DEFAULT_IDLE_BY_GROUP[payload.avatar_group] || DEFAULT_IDLE_AVATAR_VIDEO;
      setIdleVideoUrl(nextIdle);
      setHistory(Array.isArray(payload.history) ? payload.history : []);
      setChatOpen(true);
      setHistoryOpen(false);
    } catch (error) {
      setHistory((prev) => [
        ...prev,
        { query_id: `history_error_${Date.now()}`, error: error.message, isError: true },
      ]);
    }
  }, []);

  const buildHistoryTurns = useCallback(() => {
    const turns = [];
    for (const item of history) {
      if (item?.isUser && item?.transcript) {
        turns.push({ role: "user", content: String(item.transcript).trim() });
        continue;
      }
      if (!item?.isUser && !item?.isError && item?.llm_text) {
        turns.push({ role: "assistant", content: String(item.llm_text).trim() });
      }
    }
    return turns.filter((turn) => turn.content);
  }, [history]);

  const submitQuery = useCallback(async (overrides = {}) => {
    if (loading) return;
    const finalText = typeof overrides.text === "string" ? overrides.text.trim() : text.trim();
    const hasExplicitAudio = !!overrides.audio;
    const finalAudioFile = finalText ? (hasExplicitAudio ? overrides.audio : null) : (overrides.audio || audioFile);
    const isVoiceOnly = !finalText && !!finalAudioFile;
    if (!finalText && !finalAudioFile) return;

    const userQueryId = `query_${Date.now()}`;
    const userMessage = {
      query_id: userQueryId,
      transcript: finalText,
      isUser: true,
    };

    if (!isVoiceOnly) {
      setHistory((prev) => [...prev, userMessage]);
    }
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append("session_id", sessionId);
      formData.append("language", language);
      formData.append("lipsync_model", "musetalk");
      formData.append("history", JSON.stringify(buildHistoryTurns()));
      if (finalText) formData.append("text", finalText);
      if (finalAudioFile) formData.append("audio", finalAudioFile);

      const response = await fetch("/api/query/", {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Request failed.");
      }
      if (payload.session_id && payload.session_id !== sessionId) {
        setSessionId(payload.session_id);
        window.localStorage.setItem(SESSION_STORAGE_KEY, payload.session_id);
      }

      if (payload.video_url) {
        const ts = Date.now();
        const preludeUrl = payload.prelude_video_url ? `${payload.prelude_video_url}?t=${ts}` : "";
        const replyUrl = `${payload.video_url}?t=${ts}`;
        queuedVideoRef.current = preludeUrl ? replyUrl : "";
        setAvatarVideoUrl(preludeUrl || replyUrl);
        setSpeaking(true);
        setChatOpen(true);
      } else {
        queuedVideoRef.current = "";
        setAvatarVideoUrl("");
        setSpeaking(false);
      }
      const nextGroup = payload.avatar_group || "english";
      const nextIdle = payload.avatar_idle_video_url || DEFAULT_IDLE_BY_GROUP[nextGroup] || DEFAULT_IDLE_AVATAR_VIDEO;
      setIdleVideoUrl((prev) => {
        const prevBase = prev.split("?")[0];
        if (prevBase === nextIdle) return prev;
        return `${nextIdle}?t=${Date.now()}`;
      });
      if (ttsAudioRef.current) {
        ttsAudioRef.current.pause();
        ttsAudioRef.current = null;
      }
      if (payload.audio_url && !payload.video_url) {
        const a = new Audio(`${payload.audio_url}?t=${Date.now()}`);
        ttsAudioRef.current = a;
        a.play().catch(() => {});
      }

      setHistory((prev) => {
        if (!isVoiceOnly) {
          return [...prev, payload];
        }
        return [
          ...prev,
          {
            query_id: userQueryId,
            transcript: (payload.transcript || "Voice message").trim() || "Voice message",
            isUser: true,
          },
          payload,
        ];
      });
      setText("");
      setAudioFile(null);
      fetchSavedSessions();
    } catch (error) {
      setHistory((prev) => [
        ...prev,
        { query_id: `error_${Date.now()}`, error: error.message, isError: true },
      ]);
      setAvatarVideoUrl("");
      queuedVideoRef.current = "";
      setSpeaking(false);
      setAudioFile(null);
    } finally {
      setLoading(false);
    }
  }, [audioFile, language, text, loading, buildHistoryTurns, sessionId, fetchSavedSessions]);

  const startRecording = useCallback(async () => {
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Microphone API is not available in this browser.");
      }
      if (!window.MediaRecorder) {
        throw new Error("MediaRecorder is not supported in this browser.");
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
      });
      const mimeType = pickSupportedMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      const chunks = [];

      recorder.onerror = () => {
        setHistory((prev) => [
          ...prev,
          { query_id: `mic_error_${Date.now()}`, error: "Microphone recording failed.", isError: true },
        ]);
      };
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) chunks.push(event.data);
      };
      recorder.onstop = () => {
        if (!chunks.length) {
          setHistory((prev) => [
            ...prev,
            { query_id: `mic_error_${Date.now()}`, error: "No voice captured. Try speaking a little longer.", isError: true },
          ]);
          stream.getTracks().forEach((track) => track.stop());
          setStreaming(false);
          return;
        }
        const blob = new Blob(chunks, { type: "audio/webm" });
        const fileType = blob.type || "audio/webm";
        const ext = fileType.includes("mp4") ? "m4a" : fileType.includes("ogg") ? "ogg" : "webm";
        const file = new File([blob], `mic.${ext}`, { type: fileType });
        stream.getTracks().forEach((track) => track.stop());
        setStreaming(false);
        submitQuery({ text: "", audio: file });
      };

      recorder.start(100);
      recorderRef.current = recorder;
      setStreaming(true);
    } catch (error) {
      setHistory((prev) => [
        ...prev,
        { query_id: `mic_error_${Date.now()}`, error: error.message || "Microphone access failed.", isError: true },
      ]);
      setStreaming(false);
    }
  }, [pickSupportedMimeType, submitQuery]);

  const stopRecording = useCallback(() => {
    recorderRef.current?.stop();
  }, []);

  const endCall = useCallback(() => {
    setAvatarVideoUrl("");
    queuedVideoRef.current = "";
    setSpeaking(false);
    if (ttsAudioRef.current) {
      ttsAudioRef.current.pause();
      ttsAudioRef.current.currentTime = 0;
      ttsAudioRef.current = null;
    }
  }, []);

  const newChat = useCallback(() => {
    recorderRef.current?.stop();
    setStreaming(false);
    setSpeaking(false);
    setHistory([]);
    setText("");
    setAudioFile(null);
    setAvatarVideoUrl("");
    queuedVideoRef.current = "";
    setIdleVideoUrl(DEFAULT_IDLE_AVATAR_VIDEO);
    const created = makeSessionId();
    setSessionId(created);
    window.localStorage.setItem(SESSION_STORAGE_KEY, created);
    if (ttsAudioRef.current) {
      ttsAudioRef.current.pause();
      ttsAudioRef.current.currentTime = 0;
      ttsAudioRef.current = null;
    }
    fetchSavedSessions();
  }, [fetchSavedSessions]);

  useEffect(() => {
    fetchSavedSessions();
  }, [fetchSavedSessions]);

  useEffect(() => {
    let cancelled = false;
    async function bootstrapAvatar() {
      try {
        const formData = new FormData();
        formData.append("session_id", sessionId);
        formData.append("language", language);
        const response = await fetch("/api/bootstrap/", { method: "POST", body: formData });
        const payload = await response.json();
        if (!response.ok || cancelled) return;
        if (payload.session_id && payload.session_id !== sessionId) {
          setSessionId(payload.session_id);
          window.localStorage.setItem(SESSION_STORAGE_KEY, payload.session_id);
        }
        if (payload.avatar_idle_video_url) {
          setIdleVideoUrl(`${payload.avatar_idle_video_url}?t=${Date.now()}`);
        }
        if (payload.intro_video_url) {
          setAvatarVideoUrl(`${payload.intro_video_url}?t=${Date.now()}`);
          setSpeaking(true);
          setChatOpen(true);
          if (payload.intro_text) {
            setHistory((prev) => [
              ...prev,
              {
                query_id: `bootstrap_intro_${Date.now()}`,
                llm_text: payload.intro_text,
                isUser: false,
              },
            ]);
          }
        }
      } catch (_) {}
    }
    bootstrapAvatar();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    latestMessageRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history, loading]);

  return html`
    <${motion.div}
      className="app-shell"
      initial=${{ opacity: 0 }}
      animate=${{ opacity: 1 }}
      transition=${{ duration: 0.6, ease: EASE_OUT_EXPO }}
    >
      <${TopBar}
        streaming=${streaming}
        speaking=${speaking}
        loading=${loading}
        historyOpen=${historyOpen}
        onNewChat=${newChat}
        onToggleHistory=${() => setHistoryOpen((prev) => !prev)}
      />
      <${AnimatePresence}>
        ${historyOpen
          ? html`
              <${motion.aside}
                className="history-drawer"
                initial=${{ opacity: 0, x: -20, scale: 0.97, filter: "blur(6px)" }}
                animate=${{ opacity: 1, x: 0, scale: 1, filter: "blur(0px)" }}
                exit=${{ opacity: 0, x: -24, scale: 0.97, filter: "blur(6px)" }}
                transition=${{ duration: 0.35, ease: EASE_OUT_EXPO }}
              >
                <${motion.div}
                  className="history-title"
                  initial=${{ opacity: 0 }}
                  animate=${{ opacity: 1 }}
                  transition=${{ delay: 0.1 }}
                >Chat History</${motion.div}>
                <${motion.div}
                  className="history-list"
                  initial="hidden"
                  animate="visible"
                  variants=${{ visible: { transition: STAGGER_CHILDREN }, hidden: {} }}
                >
                  ${sessionsLoading
                    ? html`<${motion.div} className="history-empty" initial=${{ opacity: 0 }} animate=${{ opacity: 1 }}>
                        <${LoadingDots} />
                      </${motion.div}>`
                    : savedSessions.length
                    ? savedSessions.map((item) => html`
                        <${motion.button}
                          key=${item.session_id}
                          className=${`history-item ${item.session_id === sessionId ? "active" : ""}`}
                          onClick=${() => loadSession(item.session_id)}
                          variants=${{
                            visible: { opacity: 1, y: 0, filter: "blur(0px)" },
                            hidden: { opacity: 0, y: 10, filter: "blur(3px)" },
                          }}
                          whileHover=${{ scale: 1.015, x: 3 }}
                          whileTap=${{ scale: 0.98 }}
                          transition=${SPRING_SOFT}
                        >
                          <span className="history-item-preview">${item.preview || "New chat"}</span>
                          <span className="history-item-meta">${item.language || "auto"}</span>
                        </${motion.button}>
                      `)
                    : html`<div className="history-empty">No previous chats yet.</div>`}
                </${motion.div}>
              </${motion.aside}>
            `
          : null}
      </${AnimatePresence}>
      <main className="chat-main">
        <div className=${`workspace ${chatOpen ? "" : "chat-hidden"}`}>
          <${AvatarStage}
            idleVideoUrl=${idleVideoUrl}
            videoUrl=${avatarVideoUrl}
            streaming=${streaming}
            chatOpen=${chatOpen}
            onToggleMic=${streaming ? stopRecording : startRecording}
            onToggleChat=${() => setChatOpen((prev) => !prev)}
            onEndCall=${endCall}
            onVideoEnded=${() => {
              if (queuedVideoRef.current) {
                const next = queuedVideoRef.current;
                queuedVideoRef.current = "";
                setAvatarVideoUrl(next);
                setSpeaking(true);
                return;
              }
              setAvatarVideoUrl("");
              setSpeaking(false);
            }}
            onVideoError=${() => {
              if (queuedVideoRef.current) {
                const next = queuedVideoRef.current;
                queuedVideoRef.current = "";
                setAvatarVideoUrl(next);
                setSpeaking(true);
                return;
              }
              setAvatarVideoUrl("");
              setSpeaking(false);
            }}
          />
          <${AnimatePresence} mode="wait">
            ${chatOpen
              ? html`
                  <${motion.section}
                    key="chat-pane"
                    className="chat-pane"
                    initial=${{ opacity: 0, x: 28, filter: "blur(6px)" }}
                    animate=${{ opacity: 1, x: 0, filter: "blur(0px)" }}
                    exit=${{ opacity: 0, x: 32, filter: "blur(6px)" }}
                    transition=${{ duration: 0.35, ease: EASE_OUT_EXPO }}
                  >
                    <${MessageList} history=${history} latestMessageRef=${latestMessageRef} />
                    <${Composer}
                      text=${text}
                      loading=${loading}
                      streaming=${streaming}
                      language=${language}
                      setLanguage=${setLanguage}
                      setText=${setText}
                      onSubmit=${submitQuery}
                      onStartMic=${startRecording}
                      onStopMic=${stopRecording}
                    />
                  </${motion.section}>
                `
              : null}
          </${AnimatePresence}>
        </div>
      </main>
    </${motion.div}>
  `;
}

createRoot(document.getElementById("app")).render(html`<${App} />`);
