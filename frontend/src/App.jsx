import { useCallback, useEffect, useState } from "react";
import { API_BASE, api, CONFIG_PROBLEM, getSessionKey, getToken, setSessionKey, setToken } from "./api";
import KeyModal from "./pages/KeyModal.jsx";
import Auth from "./pages/Auth.jsx";
import Account from "./pages/Account.jsx";
import Chat from "./pages/Chat.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Upload from "./pages/Upload.jsx";
import Quiz from "./pages/Quiz.jsx";
import Results from "./pages/Results.jsx";
import Plan from "./pages/Plan.jsx";

const TABS = [["chat", "Chat"], ["notes", "Notes"], ["quiz", "Quiz"], ["results", "Results"], ["plan", "Plan"], ["dashboard", "Overview"], ["account", "Account"]];

function deriveAi(me, failed, slow) {
  if (failed) return { mode: "unreachable", label: "API unreachable", tone: "err", ready: false };
  if (!me) return { mode: "loading", label: slow ? "Waking server (free hosting sleeps)..." : "Checking AI...", tone: "warn", ready: false };
  if (getSessionKey()) return { mode: "session", label: "Your Gemini key (this session)", tone: "ok", ready: true };
  const left = Math.max(0, me.usage.server_calls_per_day_limit - me.usage.server_calls_today);
  switch (me.server_ai_status) {
    case "ok": return { mode: "free", label: "Free AI · " + left + " left today", tone: "ok", ready: true };
    case "user_quota_used": return { mode: "exhausted", label: "Free quota used", tone: "warn", ready: false,
      detail: "You've used today's " + me.usage.server_calls_per_day_limit + " free AI calls." };
    case "site_quota_used": return { mode: "exhausted", label: "Free quota used", tone: "warn", ready: false,
      detail: "The site's shared free AI quota for today is used up." };
    default: return { mode: "none", label: "No live AI", tone: "warn", ready: false };
  }
}

function initialTheme() {
  try { const t = localStorage.getItem("learnmate_theme"); if (t) return t; } catch { /* ignore */ }
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const [tab, setTab] = useState("chat");
  const [result, setResult] = useState(null);
  const [chat, setChat] = useState([]);
  const [authed, setAuthed] = useState(!!getToken());
  const [me, setMe] = useState(null);
  const [failed, setFailed] = useState(false);
  const [theme, setTheme] = useState(initialTheme);
  const [slow, setSlow] = useState(false);
  const [ephemeral, setEphemeral] = useState(false);
  const [needKey, setNeedKey] = useState(null);   // {code, message}: quota dialog, only for demo-allowance exhaustion

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("learnmate_theme", theme); } catch { /* ignore */ }
  }, [theme]);

  const logout = useCallback(() => {
    setToken(null); setSessionKey(null); setResult(null); setChat([]); setMe(null); setTab("chat"); setAuthed(false);
  }, []);
  const refresh = useCallback(() => {
    if (!getToken()) return;
    api("/me").then((m) => { setMe(m); setFailed(false); })
      .catch((e) => { if (e.message.startsWith("API unavailable")) setFailed(true); });
  }, []);

  useEffect(() => {
    window.addEventListener("learnmate-logout", logout);
    window.addEventListener("learnmate-refresh", refresh);
    const onNeed = (e) => setNeedKey(e.detail);
    window.addEventListener("learnmate-need-key", onNeed);
    return () => { window.removeEventListener("learnmate-logout", logout); window.removeEventListener("learnmate-refresh", refresh); window.removeEventListener("learnmate-need-key", onNeed); };
  }, [logout, refresh]);
  // Free hosts sleep when idle: if the first call is slow, say so instead of looking broken.
  useEffect(() => { if (authed && !me) { const t = setTimeout(() => setSlow(true), 5000); return () => clearTimeout(t); } setSlow(false); }, [authed, me]);
  useEffect(() => {
    if (CONFIG_PROBLEM) return;
    fetch(API_BASE + "/health").then((r) => r.json()).then((h) => setEphemeral(!!h.ephemeral_storage)).catch(() => {});
  }, []);
  useEffect(() => { if (authed) { refresh(); const t = setInterval(refresh, 30000); return () => clearInterval(t); } }, [authed, refresh]);

  const ai = deriveAi(me, failed, slow);
  const keyConnected = () => { setNeedKey(null); refresh(); window.dispatchEvent(new Event("learnmate-key-connected")); };
  const banner = (<>
    {CONFIG_PROBLEM && <div className="error" role="alert">{CONFIG_PROBLEM}</div>}
    {ephemeral && <div className="warn" role="note">Demo hosting: accounts and uploaded notes may be cleared whenever the server restarts or sleeps. Don't rely on this site to store anything important.</div>}
  </>);
  const themeBtn = <button className="icon-btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
    aria-label="Toggle dark mode" title="Toggle dark mode">{theme === "dark" ? "☀" : "☾"}</button>;

  if (!authed) return (
    <div className="shell">
      <header className="topbar"><div className="brand"><span className="logo">L</span><b>LearnMate</b><span className="tag">AI</span></div>{themeBtn}</header>
      <main className="card-main">{banner}<Auth onAuthed={() => setAuthed(true)} /></main>
    </div>);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand"><span className="logo">L</span><b>LearnMate</b><span className="tag">AI</span></div>
        <div className="top-actions">
          <button className={"status " + ai.tone} onClick={() => ai.ready ? setTab("account") : ai.mode === "unreachable" ? refresh() : setTab("chat")}
            title="AI status"><i className="dot" />{ai.label}</button>
          <button className="ghost" onClick={() => { setChat([]); setTab("chat"); }}>+ New chat</button>
          <button className="icon-btn" onClick={() => setTab("account")} aria-label="Account settings" title="Account">&#9881;</button>
          {themeBtn}
        </div>
      </header>
      <nav className="tabs" aria-label="Sections">
        {TABS.map(([k, label]) => <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>{label}</button>)}
        <button className="textbtn" onClick={logout}>Sign out</button>
      </nav>
      {banner}
      <main className={tab === "chat" ? "chat-main" : "card-main"}>
        {tab === "chat" && <Chat ai={ai} refresh={refresh} chat={chat} setChat={setChat} go={setTab} />}
        {tab === "notes" && <Upload />}
        {tab === "quiz" && <Quiz ai={ai} refresh={refresh} onResult={(r) => { setResult(r); setTab("results"); }} />}
        {tab === "results" && <Results result={result} />}
        {tab === "plan" && <Plan />}
        {tab === "dashboard" && <Dashboard go={setTab} />}
        {tab === "account" && <Account onLogout={logout} />}
      </main>
      {needKey && <KeyModal info={needKey} onClose={() => setNeedKey(null)} onConnected={keyConnected} />}
    </div>
  );
}
