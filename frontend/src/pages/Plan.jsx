import { useState } from "react";
import { api, post } from "../api";
import { useAsync, Loading, ErrorBox, Empty } from "../components";

export default function Plan() {
  const weak = useAsync(() => api("/weak-topics"));
  const latest = useAsync(() => api("/revision-plan"));
  const [mins, setMins] = useState(60);
  const [days, setDays] = useState(7);
  const [exam, setExam] = useState("");
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function make(e) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const body = { minutes_per_day: Number(mins), days: Number(days), explain: true };
      if (exam) body.exam_date = exam;
      setPlan(await post("/revision-plan", body));
    } catch (ex) { setErr(ex.message); }
    setBusy(false);
  }
  async function toggle(t) {
    const status = t.status === "done" ? "todo" : "done";
    try {
      await api("/revision-tasks/" + t.task_id, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
      const fresh = await api("/revision-plan"); setPlan(fresh);
    } catch (ex) { setErr(ex.message); }
  }
  const shown = plan || latest.data;
  const byDay = {};
  (shown?.tasks || []).forEach((t) => { (byDay[t.day] = byDay[t.day] || []).push(t); });

  return (
    <div>
      <h2>Weak topics</h2>
      {weak.loading ? <Loading /> : weak.error ? <ErrorBox error={weak.error} /> :
        weak.data.topics.length === 0 ? <Empty>No quiz data yet. Take some quizzes first.</Empty> : (
          <div>
            <p className="muted">{weak.data.rule}</p>
            <table><thead><tr><th>Topic</th><th>Answered</th><th>Correct</th><th>Accuracy</th><th>Status</th></tr></thead>
              <tbody>{weak.data.topics.map((t) => <tr key={t.topic}><td>{t.topic}</td><td>{t.answered}</td><td>{t.correct}</td><td>{Math.round(t.accuracy * 100)}%</td><td><span className={"badge " + t.status}>{t.status.replace(/_/g, " ")}</span></td></tr>)}</tbody></table>
          </div>)}
      <h2>Revision plan</h2>
      <form onSubmit={make} className="row wrap">
        <label>Minutes/day <input type="number" min="10" max="600" value={mins} onChange={(e) => setMins(e.target.value)} style={{ width: 80 }} /></label>
        <label>Days <input type="number" min="1" max="30" value={days} onChange={(e) => setDays(e.target.value)} style={{ width: 70 }} /></label>
        <label>Exam date (optional) <input type="date" value={exam} onChange={(e) => setExam(e.target.value)} /></label>
        <button disabled={busy}>Create plan</button>
      </form>
      {busy && <Loading />}
      <ErrorBox error={err} />
      {shown && <p className="muted">{shown.note}</p>}
      {shown?.explanation && <div className="ok">{shown.explanation}</div>}
      {Object.keys(byDay).map((d) => (
        <div key={d} className="card day"><b>Day {d}</b>
          {byDay[d].map((t) => (
            <label key={t.task_id}><input type="checkbox" checked={t.status === "done"} onChange={() => toggle(t)} /> {t.topic}: {t.minutes} min</label>))}
        </div>))}
    </div>
  );
}
