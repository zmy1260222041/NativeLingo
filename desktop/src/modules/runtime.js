export const BACKEND_URL = window.__NATIVELINGO_BACKEND__ || "http://127.0.0.1:8756";
export const BACKEND_TOKEN = window.__NATIVELINGO_TOKEN__ || null;

export const authHeaders = () =>
  BACKEND_TOKEN ? { Authorization: `Bearer ${BACKEND_TOKEN}` } : {};

export const tokenQS = () =>
  BACKEND_TOKEN ? `?token=${encodeURIComponent(BACKEND_TOKEN)}` : "";

export function clientLog(message) {
  try {
    apiFetch("/clientlog", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ msg: String(message) }),
    }).catch(() => {});
  } catch (_) {
    // Logging must never interrupt a learning session.
  }
}

export function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (BACKEND_TOKEN && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${BACKEND_TOKEN}`);
  }
  return fetch(`${BACKEND_URL}${path}`, { ...options, headers });
}

export class ApiError extends Error {
  constructor(message, status, detail = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function readJson(response, fallback = "请求失败") {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(data.detail || fallback, response.status, data);
  }
  return data;
}

export async function deadlineFetch(path, options = {}, timeoutMs = 15_000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await apiFetch(path, { ...options, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) {
      const seconds = Math.ceil(timeoutMs / 1000);
      const timeout = new Error(`等待超过${seconds}秒，已停止本次请求。请重试。`);
      timeout.name = "RequestTimeoutError";
      throw timeout;
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export function installRuntimeLogging() {
  window.addEventListener("error", (event) => clientLog(`window.error: ${event.message}`));
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason?.message || event.reason;
    clientLog(`unhandledrejection: ${reason}`);
  });
}
