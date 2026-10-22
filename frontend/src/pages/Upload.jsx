import { useState } from "react";
import { api } from "../api";
import { useAsync, Loading, ErrorBox, Empty } from "../components";

export default function Notes() {
  const docs = useAsync(() => api("/documents"));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);

  async function onFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    setBusy(true); setErr(null); setMsg(null);
    const fd = new FormData(); fd.append("file", file);
    try {
      const r = await api("/documents", { method: "POST", body: fd });
      setMsg("Indexed " + r.filename + ": " + r.pages + " page(s), " + r.chunks + " chunk(s).");
      docs.reload();
    } catch (ex) { setErr(ex.message); }
    setBusy(false); e.target.value = "";
  }
  async function remove(id) {
    try { await api("/documents/" + id, { method: "DELETE" }); docs.reload(); } catch (ex) { setErr(ex.message); }
  }
  return (
    <div>
      <h2>Upload notes</h2>
      <p className="muted">PDF or TXT. Scanned/image-only PDFs are not supported (no OCR).</p>
      <label className="drop">
        <input type="file" accept=".pdf,.txt" onChange={onFile} disabled={busy} />
        <span>{busy ? "Extracting, embedding and indexing..." : "Choose a PDF or TXT file"}</span>
      </label>
      {msg && <div className="ok">{msg}</div>}
      <ErrorBox error={err} />
      <h3>Your documents</h3>
      {docs.loading ? <Loading /> : docs.error ? <ErrorBox error={docs.error} /> :
        docs.data.length === 0 ? <Empty>No documents uploaded yet.</Empty> :
        <ul className="list">{docs.data.map((d) => (
          <li key={d.document_id}><span>{d.filename} <span className="muted">({d.chunks} chunks)</span></span>
            <button className="link" onClick={() => remove(d.document_id)}>delete</button></li>))}</ul>}
    </div>
  );
}
