import { api } from "../api";
import { useAsync, Loading, ErrorBox } from "../components";

export default function Dashboard({ go }) {
  const h = useAsync(() => api("/me"));
  const d = useAsync(() => api("/documents"));
  const a = useAsync(() => api("/attempts"));
  const w = useAsync(() => api("/weak-topics"));
  if (h.loading || d.loading) return <Loading />;
  if (h.error || d.error) return <ErrorBox error={h.error || d.error} />;
  const attempts = a.data || [];
  const avg = attempts.length ? Math.round(attempts.reduce((s, x) => s + x.percent, 0) / attempts.length) : null;
  return (
    <div>
      <h2>Dashboard</h2>
      <div className="cards">
        <div className="card"><b>{d.data.length}</b><span>documents indexed</span></div>
        <div className="card"><b>{attempts.length}</b><span>quiz attempts</span></div>
        <div className="card"><b>{avg === null ? "-" : avg + "%"}</b><span>average score</span></div>
        <div className="card"><b>{w.data ? w.data.weak.length : "-"}</b><span>weak topics</span></div>
      </div>
      {!h.data.has_own_key && !h.data.server_llm_available && <div className="warn">No AI is available yet. Add your own API key under Account to enable answers and quizzes.</div>}
      {!h.data.has_own_key && h.data.server_llm_available && <div className="muted">Free AI calls today: {h.data.usage.server_calls_today} / {h.data.usage.server_calls_per_day_limit}. Add your own key under Account for more.</div>}
      {d.data.length === 0 && <div className="empty">No notes yet. <button onClick={() => go("notes")}>Upload notes</button></div>}
    </div>
  );
}
