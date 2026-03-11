/**
 * Polybot — frontend API service layer.
 * All fetch calls to the FastAPI backend.
 */

const BASE = "";  // Vite proxy forwards /api → localhost:8000

// ── Generic helpers ──────────────────────────────────────

async function request(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

// ── Bot endpoints ────────────────────────────────────────

export async function startBot(payload) {
  return request("/api/bot/start", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function stopBot(botId) {
  return request("/api/bot/stop", {
    method: "POST",
    body: JSON.stringify({ bot_id: botId }),
  });
}

export async function getBotStatus() {
  return request("/api/bot/status");
}

export async function getTrades() {
  return request("/api/trades");
}

// ── Trade history & analytics ────────────────────────────

export async function getAllTrades(limit = 50, offset = 0, mode = "all") {
  return request(`/api/trades/all?limit=${limit}&offset=${offset}&mode=${mode}`);
}

export async function getAnalytics(mode = "all") {
  return request(`/api/analytics?mode=${mode}`);
}

// ── Config endpoints ─────────────────────────────────────

export async function getConfig() {
  return request("/api/config");
}

export async function updateConfig(data) {
  return request("/api/config", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── WebSocket ────────────────────────────────────────────

export function createTradeSocket(onMessage) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/trades`;
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => console.log("[WS] Connected");
  ws.onclose = () => console.log("[WS] Disconnected");
  ws.onerror = (e) => console.error("[WS] Error", e);
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch {
      console.warn("[WS] Bad message", event.data);
    }
  };

  return ws;
}
