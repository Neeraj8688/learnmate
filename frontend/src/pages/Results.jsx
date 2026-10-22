import { api } from "../api";
import { useAsync, Loading, ErrorBox, Empty, Md as Markdown, Sources } from "../components";

export default function Results({ result }) {
  const hist = useAsync(() => api("/attempts"), [result]);
  return (
    <div>
      <h2>Results</h2>
      {result ? (
        <div>
          <div className="card big"><b>{result.score} / {result.total}</b><span>{result.percent}%</span></div>
          {result.results.map((r) => (
            <div key={r.question_id} className={"q " + (r.correct ? "right" : "wrong")}>
              <p><b>{r.question_id + 1}. <Markdown inline text={r.question} /></b> <span className="muted">[{r.topic}]</span></p>
              <p>Your answer: {r.selected_index === null ? "(none)" : r.options[r.selected_index]}</p>
              {!r.correct && <p>Correct answer: <b>{r.options[r.correct_index]}</b></p>}
              <div className="muted"><Markdown text={r.explanation} /></div>
              <Sources sources={r.sources} msgId={"r" + r.question_id} />
            </div>))}
        </div>) : <Empty>Take a quiz to see results here.</Empty>}
      <h3>History</h3>
      {hist.loading ? <Loading /> : hist.error ? <ErrorBox error={hist.error} /> :
        hist.data.length === 0 ? <Empty>No attempts yet.</Empty> :
        <table><thead><tr><th>#</th><th>Quiz</th><th>Score</th><th>%</th><th>When (UTC)</th></tr></thead>
          <tbody>{hist.data.map((a) => <tr key={a.attempt_id}><td>{a.attempt_id}</td><td>{a.quiz_id}</td><td>{a.score}/{a.total}</td><td>{a.percent}</td><td>{a.created_at}</td></tr>)}</tbody></table>}
    </div>
  );
}
