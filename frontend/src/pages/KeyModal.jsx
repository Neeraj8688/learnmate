import { useEffect } from "react";
import { ConnectKeyForm } from "./ConnectAI";

/** Shown ONLY when the shared demo allowance is gone (shared_quota_exhausted / demo_limit_reached). */
export default function KeyModal({ info, onClose, onConnected }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const personal = info.code === "change_key";
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="keymodal-title">
        <h2 id="keymodal-title">{personal ? "Use a different Gemini key" : info.code === "demo_limit_reached" ? "Demo allowance used" : "Demo quota reached"}</h2>
        <p className="lead">{info.message}</p>
        <ConnectKeyForm onConnected={onConnected} submitLabel="Connect and continue" />
        <p className="fine">Your uploaded notes and current chat are kept. After connecting, your last question is sent again automatically.</p>
        <button className="textbtn" onClick={onClose}>Not now</button>
      </div>
    </div>
  );
}
