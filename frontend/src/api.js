// Base URL of the backend API.
// - In local dev, leave VITE_API_URL empty and Vite proxies /api to :8000.
// - On Vercel, set VITE_API_URL to your Render backend URL, e.g.
//   https://your-backend.onrender.com
// Strip any trailing slash so we never produce a double slash (`//api/...`).
const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");

/**
 * Stream a chat completion via SSE.
 * @param {Array<{role: string, content: string}>} messages
 * @param {(chunk: string) => void} onChunk - called with each text delta
 * @param {AbortSignal} signal
 * @param {string|null} conversationId - if set, the turn is persisted server-side
 * @returns {Promise<void>}
 */
export async function streamChat(messages, onChunk, signal, conversationId = null) {
  const resp = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages,
      stream: true,
      conversation_id: conversationId,
    }),
    signal,
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Request failed (${resp.status}): ${text}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE events are separated by a blank line.
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const event of events) {
      const line = event.trim();
      if (!line.startsWith("data:")) continue;
      const data = line.slice("data:".length).trim();
      if (data === "[DONE]") return;

      try {
        const parsed = JSON.parse(data);
        if (parsed.error) throw new Error(parsed.error);
        if (parsed.content) onChunk(parsed.content);
      } catch (err) {
        if (err instanceof SyntaxError) continue; // partial JSON, skip
        throw err;
      }
    }
  }
}

export async function checkHealth() {
  const resp = await fetch(`${API_BASE}/api/health`);
  return resp.json();
}

// ---- Conversation history (requires DB enabled on the backend) ----

export async function listConversations() {
  const resp = await fetch(`${API_BASE}/api/conversations`);
  if (!resp.ok) throw new Error("Failed to load conversations");
  return resp.json();
}

export async function createConversation(title = "New chat") {
  const resp = await fetch(`${API_BASE}/api/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!resp.ok) throw new Error("Failed to create conversation");
  return resp.json();
}

export async function getConversation(id) {
  const resp = await fetch(`${API_BASE}/api/conversations/${id}`);
  if (!resp.ok) throw new Error("Failed to load conversation");
  return resp.json();
}

export async function deleteConversation(id) {
  const resp = await fetch(`${API_BASE}/api/conversations/${id}`, {
    method: "DELETE",
  });
  if (!resp.ok) throw new Error("Failed to delete conversation");
  return resp.json();
}
