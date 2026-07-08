import React, { useState, useRef, useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { patchApplied, loggedFlagSet } from "../store/interactionSlice";

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000";

const WELCOME = {
  role: "assistant",
  text: 'Log interaction details here (e.g. "Met Dr. Sharma, discussed OncoBoost Phase III efficacy, positive sentiment, shared the brochure") or ask for help.',
};

export default function ChatPanel() {
  const [messages, setMessages] = useState([WELCOME]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);

  const dispatch = useDispatch();
  const interaction = useSelector((s) => s.interaction);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    const text = draft.trim();
    if (!text || loading) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setDraft("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          current_state: interaction,
          is_logged: interaction.isLogged,
        }),
      });
      const data = await res.json();
      if (data.field_updates && Object.keys(data.field_updates).length > 0) {
        dispatch(patchApplied(data.field_updates));
      }
      if (data.is_logged) dispatch(loggedFlagSet(true));
      setMessages((m) => [...m, { role: "assistant", text: data.reply, tool: data.tool_used }]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: "Couldn't reach the AI service — check that the backend is running." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <aside className="card chat-card">
      <div className="chat-header">
        <span className="chat-icon">🤖</span>
        <div>
          <div className="chat-title">AI Assistant</div>
          <div className="chat-subtitle">Log interaction via chat</div>
        </div>
      </div>

      <div className="chat-messages" ref={scrollRef}>
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.text}
          </div>
        ))}
        {loading && <div className="bubble assistant typing">Thinking…</div>}
      </div>

      <div className="chat-input-row">
        <input
          className="input"
          placeholder="Describe interaction..."
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button className="log-btn" onClick={send} disabled={loading}>
          ⚠ Log
        </button>
      </div>
    </aside>
  );
}
