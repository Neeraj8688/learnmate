import { useState } from "react";
import { post, setToken } from "../api";
import { ErrorBox } from "../components";

export default function Auth({ onAuthed }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await post(mode === "login" ? "/auth/login" : "/auth/register", { email, password });
      setToken(r.access_token);
      onAuthed(r.email);
    } catch (ex) { setErr(ex.message); }
    setBusy(false);
  }
  return (
    <div className="auth">
      <h2>{mode === "login" ? "Sign in" : "Create account"}</h2>
      <p className="muted">Your notes and quiz history are private to your account.</p>
      <form onSubmit={submit} className="stack">
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
        <input type="password" placeholder="Password (min 8 characters)" value={password} minLength={8}
          onChange={(e) => setPassword(e.target.value)} required autoComplete={mode === "login" ? "current-password" : "new-password"} />
        <button disabled={busy}>{busy ? "Please wait..." : mode === "login" ? "Sign in" : "Register"}</button>
      </form>
      <ErrorBox error={err} />
      <p>
        {mode === "login" ? "No account? " : "Already registered? "}
        <button className="textbtn" onClick={() => { setMode(mode === "login" ? "register" : "login"); setErr(null); }}>
          {mode === "login" ? "Create one" : "Sign in"}
        </button>
      </p>
    </div>
  );
}
