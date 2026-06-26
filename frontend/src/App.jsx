import { useEffect, useRef, useState } from "react";
import {
  checkHealth,
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  streamChat,
} from "./api.js";
import "./App.css";

const WELCOME = {
  role: "assistant",
  content: "Hi! I'm your AI assistant. Ask me anything 👋",
};

export default function App() {
  const [messages, setMessages] = useState([WELCOME]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [persistence, setPersistence] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [currentId, setCurrentId] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const abortRef = useRef(null);
  const scrollRef = useRef(null);
  const textareaRef = useRef(null);

  // Detect whether the backend has a database, and load history if so.
  useEffect(() => {
    (async () => {
      try {
        const health = await checkHealth();
        if (health.database) {
          setPersistence(true);
          refreshConversations();
        }
      } catch {
        /* backend unreachable; UI still works for live chat attempts */
      }
    })();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, loading]);

  async function refreshConversations() {
    try {
      setConversations(await listConversations());
    } catch {
      /* ignore */
    }
  }

  function autoGrow(el) {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }

  function newChat() {
    abortRef.current?.abort();
    setCurrentId(null);
    setMessages([WELCOME]);
    setError("");
    setSidebarOpen(false);
  }

  async function openConversation(id) {
    abortRef.current?.abort();
    setError("");
    setSidebarOpen(false);
    try {
      const convo = await getConversation(id);
      setCurrentId(id);
      setMessages(
        convo.messages.length
          ? convo.messages.map((m) => ({ role: m.role, content: m.content }))
          : [WELCOME]
      );
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeConversation(e, id) {
    e.stopPropagation();
    try {
      await deleteConversation(id);
      if (id === currentId) newChat();
      refreshConversations();
    } catch (err) {
      setError(err.message);
    }
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || loading) return;

    setError("");
    const userMsg = { role: "user", content: text };
    const history = messages.filter((m) => m !== WELCOME);
    const outgoing = [...history, userMsg];

    setMessages((prev) => [...prev, userMsg, { role: "assistant", content: "" }]);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setLoading(true);

    // Create a conversation on the first message of a new chat.
    let convoId = currentId;
    if (persistence && !convoId) {
      try {
        const convo = await createConversation(text.slice(0, 60));
        convoId = convo.id;
        setCurrentId(convo.id);
      } catch {
        /* fall back to a non-persisted chat */
      }
    }

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(
        outgoing,
        (chunk) => {
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = {
              role: "assistant",
              content: next[next.length - 1].content + chunk,
            };
            return next;
          });
        },
        controller.signal,
        convoId
      );
      if (persistence && convoId) refreshConversations();
    } catch (err) {
      if (err.name !== "AbortError") {
        setError(err.message || "Something went wrong.");
        setMessages((prev) => {
          const next = [...prev];
          if (next[next.length - 1].content === "") next.pop();
          return next;
        });
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className="layout">
      {persistence && (
        <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
          <button className="new-chat-btn" onClick={newChat}>
            ＋ New chat
          </button>
          <div className="convo-list">
            {conversations.length === 0 && (
              <p className="empty-note">No saved chats yet.</p>
            )}
            {conversations.map((c) => (
              <div
                key={c.id}
                className={`convo-item ${c.id === currentId ? "active" : ""}`}
                onClick={() => openConversation(c.id)}
              >
                <span className="convo-title">{c.title}</span>
                <button
                  className="del-btn"
                  title="Delete"
                  onClick={(e) => removeConversation(e, c.id)}
                >
                  🗑
                </button>
              </div>
            ))}
          </div>
          <div className="sidebar-foot">💾 History saved to Postgres</div>
        </aside>
      )}

      <div className="app">
        <header className="header">
          <div className="brand">
            {persistence && (
              <button
                className="menu-btn"
                onClick={() => setSidebarOpen((v) => !v)}
                title="Toggle history"
              >
                ☰
              </button>
            )}
            <span className="logo">🤖</span>
            <div>
              <h1>AI Chatbot</h1>
              <p>React · FastAPI · OpenRouter{persistence ? " · Postgres" : ""}</p>
            </div>
          </div>
          <button className="ghost-btn" onClick={newChat} title="New chat">
            ＋ New chat
          </button>
        </header>

        <main className="chat" ref={scrollRef}>
          {messages.map((m, i) => (
            <div key={i} className={`row ${m.role}`}>
              <div className="avatar">{m.role === "user" ? "🧑" : "🤖"}</div>
              <div className="bubble">
                {m.content ||
                  (loading && i === messages.length - 1 ? (
                    <span className="typing">
                      <span></span>
                      <span></span>
                      <span></span>
                    </span>
                  ) : null)}
              </div>
            </div>
          ))}
          {error && <div className="error">⚠️ {error}</div>}
        </main>

        <footer className="composer">
          <textarea
            ref={textareaRef}
            value={input}
            placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
            onChange={(e) => {
              setInput(e.target.value);
              autoGrow(e.target);
            }}
            onKeyDown={onKeyDown}
            rows={1}
          />
          {loading ? (
            <button className="send-btn stop" onClick={stop}>
              ■ Stop
            </button>
          ) : (
            <button
              className="send-btn"
              onClick={sendMessage}
              disabled={!input.trim()}
            >
              ➤ Send
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
