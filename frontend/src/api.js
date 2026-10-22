// ---- API base URL -------------------------------------------------------------------------
// Production builds read VITE_API_BASE_URL (public backend URL only; never put a secret in a VITE_ var,
// because everything VITE_* is baked into the public JavaScript bundle). VITE_API_URL is a legacy alias.
const RAW = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || "";
export const API_BASE = (RAW || (import.meta.env.DEV ? "http://localhost:8000" : "")).replace(/\/+$/, "");

const isLocalHost = (h) => ["localhost", "127.0.0.1", "[::1]"].includes(h);
function configProblem() {
  if (!API_BASE) return "This deployment is missing VITE_API_BASE_URL (the public backend URL). Set it and rebuild.";
  try {
    const u = new URL(API_BASE, window.location.origin);
    if (isLocalHost(u.hostname) && !isLocalHost(window.location.hostname))
      return "This build points at localhost. Set VITE_API_BASE_URL to your public backend URL and rebuild.";
  } catch { /* relative base such as /api is fine */ }
  return null;
}
export const CONFIG_PROBLEM = configProblem();

// ---- auth token (login session) -----------------------------------------------------------
const KEY = "learnmate_token";
// localStorage can throw (private mode, blocked storage), so every access is guarded.
export const getToken = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
export const setToken = (t) => { try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); } catch { /* ignore */ } };

// ---- personal Gemini key: tab session only ------------------------------------------------
// Kept in sessionStorage (cleared when the tab closes), never in localStorage, never sent anywhere
// except as a request header to this app's own backend, and never saved server-side.
const SKEY = "learnmate_session_gemini_key";
export const getSessionKey = () => { try { return sessionStorage.getItem(SKEY) || null; } catch { return null; } };
export const setSessionKey = (v) => { try { v ? sessionStorage.setItem(SKEY, v) : sessionStorage.removeItem(SKEY); } catch { /* ignore */ } };
const AI_PATHS = ["/chat", "/quizzes", "/agent", "/revision-plan", "/llm/check"];
// Only these codes mean "the shared demo allowance is gone, ask for a personal key".
export const NEED_KEY_CODES = new Set(["shared_quota_exhausted", "demo_limit_reached"]);

export class ApiError extends Error {
  constructor(message, { status = 0, code = "error", retryAfter = null } = {}) {
    super(message);
    this.status = status; this.code = code; this.retryAfter = retryAfter;
  }
}

export async function api(path, opts = {}) {
  if (CONFIG_PROBLEM) throw new ApiError(CONFIG_PROBLEM, { code: "misconfigured" });
  const headers = { ...(opts.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = "Bearer " + token;
  const isAi = AI_PATHS.some((p) => path.startsWith(p));
  const sk = getSessionKey();
  if (sk && isAi) headers["X-LLM-Key"] = sk;
  let res;
  try {
    res = await fetch(API_BASE + path, { ...opts, headers });
  } catch {
    throw new ApiError("API unavailable. Check your connection or try again in a moment.", { code: "network" });
  }
  if (isAi) window.dispatchEvent(new Event("learnmate-refresh"));
  if (res.status === 401 && !path.startsWith("/auth/")) {
    setToken(null); setSessionKey(null);
    window.dispatchEvent(new Event("learnmate-logout"));
    throw new ApiError("Your session expired. Please sign in again.", { status: 401, code: "not_authenticated" });
  }
  if (!res.ok) {
    let detail = "", code = "error";
    try { const j = await res.json(); detail = j.detail; code = j.code || code; } catch { /* non-JSON error */ }
    const retry = Number(res.headers.get("Retry-After")) || null;
    let msg = typeof detail === "string" && detail ? detail : detail ? "Invalid request." : "Request failed (HTTP " + res.status + ")";
    if (res.status === 429 && retry && !msg.includes("Try again")) msg += " (retry in " + retry + "s)";
    const err = new ApiError(msg, { status: res.status, code, retryAfter: retry });
    if (code === "invalid_api_key" && sk) { setSessionKey(null); window.dispatchEvent(new Event("learnmate-refresh")); }
    if (NEED_KEY_CODES.has(code)) window.dispatchEvent(new CustomEvent("learnmate-need-key", { detail: { code, message: msg } }));
    throw err;
  }
  return res.json();
}

const json = (method) => (path, body) =>
  api(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const post = json("POST");
export const put = json("PUT");
