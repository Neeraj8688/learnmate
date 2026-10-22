import { useState } from "react";
import { api, post } from "../api";
import { useAsync, Loading, ErrorBox, Md as Markdown, Sources } from "../components";
import ConnectAI from "./ConnectAI";

export default function Quiz({ onResult, ai, refresh }) {
  const docs = useAsync(() => api("/documents"));
  const [topic, setTopic] = useState("");
  const [docId, setDocId] = useState("");
  const [n, setN] = useState(5);
  const [quiz, setQuiz] = useState(null);
  const [picked, setPicked] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function generate(e) {
    e.preventDefault();
    setBusy(true); setErr(null); setQuiz(null); setPicked({});
    try {
      const body = { num_questions: Number(n) };
      if (topic.trim()) body.topic = topic.trim();
      if (docId) body.document_id = docId;
      setQuiz(await post("/quizzes", body));
    } catch (ex) { setErr(ex.message); }
    setBusy(false);
  }
  async function submit() {
    setBusy(true); setErr(null);
    const answers = Object.entries(picked).map(([id, i]) => ({ question_id: Number(id), selected_index: i }));
    try { onResult(await post("/quizzes/" + quiz.quiz_id + "/submit", { answers })); } catch (ex) { setErr(ex.message); }
    setBusy(false);
  }
  return (
    <div>
      <h2>Quiz</h2>
      {!ai.ready && ai.mode !== "unreachable" && <ConnectAI ai={ai} onDone={() => window.dispatchEvent(new Event("learnmate-key-connected"))} />}
      <form onSubmit={generate} className="row wrap">
        <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Topic (optional)" />
        <select value={docId} onChange={(e) => setDocId(e.target.value)}>
          <option value="">All documents</option>
          {(docs.data || []).map((d) => <option key={d.document_id} value={d.document_id}>{d.filename}</option>)}
        </select>
        <input type="number" min="1" max="10" value={n} onChange={(e) => setN(e.target.value)} style={{ width: 70 }} />
        <button disabled={busy}>Generate quiz</button>
      </form>
      {busy && <Loading text="Working..." />}
      <ErrorBox error={err} />
      {quiz && (
        <div>
          {quiz.questions.map((q) => (
            <fieldset key={q.id} className="q">
              <legend>{q.id + 1}. <Markdown inline text={q.question} /> <span className="muted">[{q.topic}, {q.difficulty}]</span></legend>
              {q.options.map((o, i) => (
                <label key={i}><input type="radio" name={"q" + q.id} checked={picked[q.id] === i}
                  onChange={() => setPicked({ ...picked, [q.id]: i })} /> {o}</label>))}
              <Sources sources={q.sources} msgId={"q" + q.id} />
            </fieldset>))}
          <button onClick={submit} disabled={busy}>Submit ({Object.keys(picked).length}/{quiz.questions.length} answered)</button>
        </div>)}
    </div>
  );
}
