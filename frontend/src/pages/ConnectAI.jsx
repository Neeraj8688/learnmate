import { useState } from "react";
import { api, setSessionKey } from "../api";

const KEY_URL = "https://aistudio.google.com/apikey";
const FRIENDLY = {
  invalid_api_key: "Google rejected that key. Check that you copied it fully and that the Gemini API is enabled for it.",
  personal_quota_exhausted: "That key is valid but has reached its own quota. Try a different key or wait for it to reset.",
  provider_unavailable: "Google's service is temporarily unavailable. Your key was not rejected; please try again in a moment.",
  provider_network_error: "Could not reach Google's service. Check your connection and try again.",
  provider_rate_limited: "Google is rate limiting requests right now. Wait a few seconds and press Connect again.",
  https_required: "This site must be opened over HTTPS before a key can be sent.",
};

/** Key entry + validation. The key is checked with a tiny request, kept for this browser tab only. */
export function ConnectKeyForm({ onConnected, submitLabel = "Connect" }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function connect(e) {
    e.preventDefault();
    setBusy(true); setErr(null);
    const k = key.trim();
    setSessionKey(k);
    try {
      const r = await api("/llm/check", { method: "POST" });
      if (!r.ok) throw Object.assign(new Error(r.error || "The key did not work."), { code: r.code });
      setKey("");
      onConnected && onConnected();
    } catch (ex) {
      setSessionKey(null);                       // never keep a key that failed
      setErr(FRIENDLY[ex.code] || ex.message);
    }
    setBusy(false);
  }
  return (
    <form onSubmit={connect} className="connect-form">
      <input className="pill-input" type="password" placeholder="Paste your Gemini API key" value={key}
        onChange={(e) => setKey(e.target.value)} required minLength={8} autoComplete="off" spellCheck={false} aria-label="Gemini API key" />
      <button className="primary" disabled={busy || key.trim().length < 8}>{busy ? "Checking..." : submitLabel}</button>
      {err && <div className="error" role="alert">{err}</div>}
      <p className="fine">
        Don't have one? <a href={KEY_URL} target="_blank" rel="noopener noreferrer">Create a free key in Google AI Studio</a>.
        Your key stays in this browser tab only, is sent over HTTPS with your requests, and is never saved or logged on our
        servers. Closing the tab or pressing Disconnect removes it.
      </p>
    </form>
  );
}

/** Inline panel for "no AI available" states (the quota dialog lives in KeyModal). */
export default function ConnectAI({ ai, onDone }) {
  const exhausted = ai.mode === "exhausted";
  return (
    <div className="hero connect">
      <div className="hero-icon warn-icon" aria-hidden>!</div>
      <h2>{exhausted ? "Demo quota reached" : "No live AI"}</h2>
      <p className="lead">
        {exhausted ? ai.detail + " Connect your own Gemini API key to keep going. Usage is billed to your Google account."
          : "This site has no shared AI key configured. Connect your own Gemini API key to get answers and quizzes."}
      </p>
      <ConnectKeyForm onConnected={onDone} />
      <p className="fine">You can still search your notes without AI; matching passages are shown instead of a written answer.</p>
    </div>
  );
}
