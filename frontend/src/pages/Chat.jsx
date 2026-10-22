import { useEffect, useRef, useState } from "react";
import { post } from "../api";
import { Md as Markdown, Sources } from "../components";
import ConnectAI from "./ConnectAI";

const STATUS_LABEL = { answered: "answered", insufficient_evidence: "not in your notes", llm_not_configured: "passages only" };
const RETRYABLE = new Set(["provider_unavailable", "provider_network_error", "provider_rate_limited", "network", "server_ai_misconfigured", "provider_error"]);

export default function Chat({ ai, refresh, chat, setChat, go }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  const pending = useRef(null);       // question waiting for the visitor to connect a key
  useEffect(() => { end.current && end.current.scrollIntoView({ behavior: "smooth", block: "end" }); }, [chat, busy]);

  async function ask(question, { resend = false } = {}) {
    setBusy(true);
    if (!resend) setChat((c) => [...c, { role: "user", text: question }]);
    try {
      const r = await post("/chat", { question });
      setChat((c) => [...c, { role: "ai", text: r.answer, status: r.status, sources: r.sources }]);
    } catch (ex) {
      if (ex.code === "shared_quota_exhausted" || ex.code === "demo_limit_reached") {
        pending.current = question;   // the app-level dialog asks for a key; we retry once it is connected
        setChat((c) => [...c, { role: "ai", notice: true, text: "The demo allowance is used up. Connect your own Gemini API key to continue; this question will be sent again automatically." }]);
      } else {
        setChat((c) => [...c, { role: "ai", error: { code: ex.code, message: ex.message }, question }]);
      }
    }
    setBusy(false);
    refresh();
  }

  useEffect(() => {
    const onConnected = () => {
      const question = pending.current;
      pending.current = null;
      if (question) {
        setChat((c) => c.filter((m) => !m.notice));   // drop the waiting notice; chat and notes are kept
        ask(question, { resend: true });
      }
    };
    window.addEventListener("learnmate-key-connected", onConnected);
    return () => window.removeEventListener("learnmate-key-connected", onConnected);
  }); // re-bound each render so it always sees the latest state

  function send(e) {
    e.preventDefault();
    const question = q.trim();
    if (question.length < 2 || busy) return;
    setQ("");
    ask(question);
  }
  const empty = chat.length === 0;
  const needsAi = !ai.ready && (ai.mode === "exhausted" || ai.mode === "none");
  return (
    <div className="chat">
      {empty && needsAi && <ConnectAI ai={ai} onDone={() => window.dispatchEvent(new Event("learnmate-key-connected"))} />}
      {empty && ai.ready && (
        <div className="hero">
          <div className="hero-icon" aria-hidden>?</div>
          <h2>Ask your notes</h2>
          <p className="lead">Answers come only from what you upload, with the source file and page.</p>
          <div className="chips">
            <button className="chip" onClick={() => go("notes")}>Upload notes</button>
            <button className="chip" onClick={() => go("quiz")}>Take a quiz</button>
            <button className="chip" onClick={() => go("plan")}>Revision plan</button>
          </div>
        </div>
      )}
      {empty && ai.mode === "unreachable" && (
        <div className="hero"><div className="hero-icon warn-icon" aria-hidden>!</div><h2>API unreachable</h2>
          <p className="lead">The server isn't responding. Check that the backend is running, then retry.</p>
          <button className="primary" onClick={refresh}>Retry</button></div>
      )}
      <div className="msgs">
        {chat.map((m, i) => (
          <div key={i} className={"msg " + m.role + (m.error ? " err" : "") + (m.notice ? " notice" : "")}>
            {m.role === "user" && <p>{m.text}</p>}
            {m.role === "ai" && m.error && (
              <>
                <span className="badge error">{m.error.code === "invalid_api_key" ? "key rejected" : "problem"}</span>
                <p>{m.error.message}</p>
                {RETRYABLE.has(m.error.code) && <button className="chip" disabled={busy} onClick={() => ask(m.question, { resend: true })}>Try again</button>}
                {(m.error.code === "invalid_api_key" || m.error.code === "personal_quota_exhausted") &&
                  <button className="chip" onClick={() => { pending.current = m.question; window.dispatchEvent(new CustomEvent("learnmate-need-key", { detail: { code: "change_key", message: "Enter a different Gemini API key. Your last question will be sent again." } })); }}>Use a different key</button>}
              </>
            )}
            {m.role === "ai" && m.notice && <p>{m.text}</p>}
            {m.role === "ai" && !m.error && !m.notice && (
              <>
                {m.status && <span className={"badge " + m.status}>{STATUS_LABEL[m.status] || m.status}</span>}
                <Markdown text={m.text} maxRef={m.sources?.length || 0} msgId={"m" + i} />
                <Sources sources={m.sources} msgId={"m" + i} />
              </>
            )}
          </div>
        ))}
        {busy && <div className="msg ai typing">Searching your notes...</div>}
        {!empty && needsAi && !pending.current && <ConnectAI ai={ai} onDone={() => window.dispatchEvent(new Event("learnmate-key-connected"))} />}
        <div ref={end} />
      </div>
      <form className="composer" onSubmit={send}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask a question about your notes..." aria-label="Question" />
        <button className="send" disabled={busy || q.trim().length < 2} aria-label="Send">&#10148;</button>
      </form>
    </div>
  );
}
