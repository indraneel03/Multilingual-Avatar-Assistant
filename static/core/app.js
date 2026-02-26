import React, { memo, useCallback, useEffect, useRef, useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
import { AnimatePresence, motion } from "https://esm.sh/framer-motion@11.11.17";
import htm from "https://esm.sh/htm@3.1.1";

const html = htm.bind(React.createElement);
const DEFAULT_IDLE_AVATAR_VIDEO = "/static/core/Realistic_Avatar_Video_Generation.mp4";
const SESSION_STORAGE_KEY = "avatar_assistant_session_id";

function makeSessionId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID().replace(/-/g, "");
  return `sess_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

const TopBar = memo(function TopBar({ streaming, speaking, loading, historyOpen, onNewChat, onToggleHistory }) {
  const status = streaming ? "Listening..." : speaking ? "Speaking..." : loading ? "Thinking..." : "Ready";
  return html`
    <${motion.header}
      className="topbar"
      initial=${{ opacity: 0, y: -10 }}
      animate=${{ opacity: 1, y: 0 }}
      transition=${{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="brand">Avatar Assistant</div>
      <div className="topbar-actions">
        <button
          className=${`topbar-history ${historyOpen ? "active" : ""}`}
          onClick=${onToggleHistory}
          title="Open chat history"
        >
          History
        </button>
        <button className="topbar-new-chat" onClick=${onNewChat} disabled=${loading} title="Start a new chat">
          New Chat
        </button>
        <div className="status">
          <span className=${`dot ${streaming || speaking || loading ? "active" : ""}`}></span>
          ${status}
        </div>
      </div>
    </${motion.header}>
  `;
});

const AvatarStage = memo(function AvatarStage({
  idleVideoUrl,
  videoUrl,
  streaming,
  chatOpen,
  onToggleMic,
  onToggleChat,
  onEndCall,
  onVideoEnded,
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
      try {
        video.currentTime = 0;
      } catch (_) {}
    };
    if (video.readyState >= 1) {
      lockToFirstFrame();
    } else {
      video.addEventListener("loadedmetadata", lockToFirstFrame, { once: true });
    }
  }, [isTalking, idleVideoUrl]);

  return html`
    <section className="avatar-stage">
      <${motion.div}
        className=${`avatar-canvas ${isTalking ? "video-mode" : "idle-mode"}`}
        initial=${{ opacity: 0, y: 8 }}
        animate=${{ opacity: 1, y: 0 }}
        transition=${{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      >
        <${motion.div}
          className="avatar-control-strip"
          initial=${{ opacity: 0, y: 12, scale: 0.96 }}
          animate=${{ opacity: 1, y: 0, scale: 1 }}
          transition=${{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
        >
          <${motion.button}
            className=${`avatar-control icon ${chatOpen ? "active" : ""}`}
            onClick=${onToggleChat}
            title="Open or close chat"
            aria-label="Toggle chat panel"
            whileHover=${{ scale: 1.07, y: -1 }}
            whileTap=${{ scale: 0.94 }}
            transition=${{ type: "spring", stiffness: 360, damping: 20 }}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 5h16v11H8l-4 4V5zm2 2v8.17L7.17 14H18V7H6z"></path>
            </svg>
          </${motion.button}>
          <${motion.button}
            className=${`avatar-control icon ${streaming ? "active" : ""}`}
            onClick=${onToggleMic}
            title="Start or stop microphone input"
            aria-label=${streaming ? "Stop microphone input" : "Start microphone input"}
            whileHover=${{ scale: 1.07, y: -1 }}
            whileTap=${{ scale: 0.94 }}
            transition=${{ type: "spring", stiffness: 360, damping: 20 }}
          >
            ${streaming
              ? html`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V22h2v-3.08A7 7 0 0 0 19 12h-2z"></path><circle cx="19" cy="5" r="3"></circle></svg>`
              : html`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V22h2v-3.08A7 7 0 0 0 19 12h-2z"></path></svg>`}
          </${motion.button}>
          <${motion.button}
            className="avatar-control icon end"
            onClick=${onEndCall}
            title="End current response"
            aria-label="End response"
            whileHover=${{ scale: 1.07, y: -1 }}
            whileTap=${{ scale: 0.94 }}
            transition=${{ type: "spring", stiffness: 360, damping: 20 }}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 14c2.5-2 5.3-3 8-3s5.5 1 8 3l-1.8 4.2-3.9-1.3v-2.2h-4.6v2.2l-3.9 1.3L4 14z"></path>
            </svg>
          </${motion.button}>
        </${motion.div}>
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
                initial=${{ opacity: 0.2, scale: 0.985 }}
                animate=${{ opacity: 1, scale: 1 }}
                transition=${{ duration: 0.28 }}
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
                initial=${{ opacity: 0.2 }}
                animate=${{ opacity: 1 }}
                transition=${{ duration: 0.35 }}
              ></${motion.video}>
            `}
      </${motion.div}>
    </section>
  `;
});

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
              initial=${{ opacity: 0, y: 10 }}
              animate=${{ opacity: 1, y: 0 }}
              exit=${{ opacity: 0, y: -10 }}
              transition=${{ duration: 0.18 }}
            >
              ${isUser
                ? html`<div className="bubble user-bubble">${item.transcript}</div>`
                : isError
                ? html`<div className="bubble error-bubble">${item.error}</div>`
                : html`
                    <div className="bubble assistant-bubble">
                      ${item.llm_text}
                      ${item.warning ? html`<div className="inline-warning">${item.warning}</div>` : null}
                    </div>
                  `}
            </${motion.article}>
          `;
        })}
      </${AnimatePresence}>
    </section>
  `;
});

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
      initial=${{ opacity: 0, y: 10 }}
      animate=${{ opacity: 1, y: 0 }}
      transition=${{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
    >
      <${motion.div}
        className="composer-tools"
        whileHover=${{ y: -1 }}
        transition=${{ type: "spring", stiffness: 300, damping: 22 }}
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
        <textarea
          placeholder="Message Avatar Assistant"
          value=${text}
          onChange=${(e) => setText(e.target.value)}
          onKeyDown=${(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
        ></textarea>
        <button className=${`icon-btn mic ${streaming ? "active" : ""}`} onClick=${streaming ? onStopMic : onStartMic} title="Microphone">
          ${streaming ? "Stop" : "Mic"}
        </button>
        <button className="icon-btn send" onClick=${onSubmit} disabled=${loading} title="Send">
          ${loading ? "..." : "Send"}
        </button>
      </div>
    </${motion.footer}>
  `;
});

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
  const [idleVideoUrl] = useState(DEFAULT_IDLE_AVATAR_VIDEO);
  const [avatarVideoUrl, setAvatarVideoUrl] = useState("");
  const ttsAudioRef = useRef(null);

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
      setLanguage((payload.language || "auto").toLowerCase() || "auto");
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
        setAvatarVideoUrl(`${payload.video_url}?t=${Date.now()}`);
        setSpeaking(true);
        setChatOpen(true);
      } else {
        setAvatarVideoUrl("");
        setSpeaking(false);
      }
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
    latestMessageRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history, loading]);

  return html`
    <div className="app-shell">
      <${TopBar}
        streaming=${streaming}
        speaking=${speaking}
        loading=${loading}
        historyOpen=${historyOpen}
        onNewChat=${newChat}
        onToggleHistory=${() => setHistoryOpen((prev) => !prev)}
      />
      <${AnimatePresence} initial=${false}>
        ${historyOpen
          ? html`
              <${motion.aside}
                className="history-drawer"
                initial=${{ opacity: 0, x: -16 }}
                animate=${{ opacity: 1, x: 0 }}
                exit=${{ opacity: 0, x: -18 }}
                transition=${{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
              >
                <div className="history-title">Chat History</div>
                <div className="history-list">
                  ${sessionsLoading
                    ? html`<div className="history-empty">Loading...</div>`
                    : savedSessions.length
                    ? savedSessions.map((item) => html`
                        <button
                          key=${item.session_id}
                          className=${`history-item ${item.session_id === sessionId ? "active" : ""}`}
                          onClick=${() => loadSession(item.session_id)}
                        >
                          <span className="history-item-preview">${item.preview || "New chat"}</span>
                          <span className="history-item-meta">${item.language || "auto"}</span>
                        </button>
                      `)
                    : html`<div className="history-empty">No previous chats yet.</div>`}
                </div>
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
              setAvatarVideoUrl("");
              setSpeaking(false);
            }}
          />
          <${AnimatePresence} initial=${false}>
            ${chatOpen
              ? html`
                  <${motion.section}
                    key="chat-pane"
                    className="chat-pane"
                    initial=${{ opacity: 0, x: 20 }}
                    animate=${{ opacity: 1, x: 0 }}
                    exit=${{ opacity: 0, x: 24 }}
                    transition=${{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
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
    </div>
  `;
}

createRoot(document.getElementById("app")).render(html`<${App} />`);
