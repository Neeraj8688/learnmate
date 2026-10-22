import { api, setToken, getSessionKey, setSessionKey } from "../api";
import { useState } from "react";
import { useAsync, Loading, ErrorBox } from "../components";
import { ConnectKeyForm } from "./ConnectAI";

export default function Account({ onLogout }) {
  const me = useAsync(() => api("/me"));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [, bump] = useState(0);
  const connected = !!getSessionKey();

  const disconnect = () => { setSessionKey(null); window.dispatchEvent(new Event("learnmate-refresh")); bump((n) => n + 1); };
  async function deleteAccount() {
    if (!window.confirm("Permanently delete your account, notes and quizzes? This cannot be undone.")) return;
    setBusy(true); setErr(null);
    try { await api("/me", { method: "DELETE" }); setToken(null); setSessionKey(null); onLogout(); } catch (ex) { setErr(ex.message); setBusy(false); }
  }
  if (me.loading) return <Loading />;
  if (me.error) return <ErrorBox error={me.error} />;
  const d = me.data;
  return (
    <div>
      <h2>Account</h2>
      <p>Signed in as <b>{d.email}</b></p>
      <div className="cards">
        <div className="card"><b>{connected ? "Your key" : d.server_llm_available ? "Shared demo" : "None"}</b><span>AI source in use</span></div>
        {!connected && d.server_llm_available &&
          <div className="card"><b>{d.usage.server_calls_today} / {d.usage.server_calls_per_day_limit}</b><span>demo AI calls today (UTC)</span></div>}
        <div className="card"><b>{d.max_docs}</b><span>max documents</span></div>
      </div>

      <h3>Your own Gemini API key</h3>
      <p className="muted">
        The shared demo key has daily limits. Connect your own key to keep going. It is held for this browser tab only
        (never stored on the server, never logged) and removed when you close the tab or disconnect.
      </p>
      {connected
        ? <div className="ok">A personal Gemini key is connected for this session.
            <div className="row"><button className="danger" onClick={disconnect}>Disconnect key</button></div></div>
        : <ConnectKeyForm onConnected={() => { window.dispatchEvent(new Event("learnmate-refresh")); bump((n) => n + 1); }} />}

      <h3>Danger zone</h3>
      <ErrorBox error={err} />
      <button className="danger" onClick={deleteAccount} disabled={busy}>Delete my account and data</button>
    </div>
  );
}
