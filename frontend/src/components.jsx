import { lazy, Suspense, useEffect, useState } from "react";

// Markdown + KaTeX are heavy, so they load on demand instead of bloating the first page.
const MarkdownLazy = lazy(() => import("./markdown.jsx"));
export function Md(props) {
  return <Suspense fallback={<span className="muted">{props.text}</span>}><MarkdownLazy {...props} /></Suspense>;
}

export function useAsync(fn, deps = []) {
  const [state, set] = useState({ loading: true, data: null, error: null });
  const reload = () => {
    set((s) => ({ ...s, loading: true, error: null }));
    fn().then((data) => set({ loading: false, data, error: null }))
        .catch((e) => set({ loading: false, data: null, error: e.message }));
  };
  useEffect(reload, deps); // eslint-disable-line
  return { ...state, reload };
}

export const Loading = ({ text = "Loading..." }) => <p className="muted">{text}</p>;
export const ErrorBox = ({ error }) => error ? <div className="error" role="alert">{error}</div> : null;
export const Empty = ({ children }) => <div className="empty">{children}</div>;

/** Readable citations: "1 · Physics.pdf · page 10" + the supporting excerpt. Internal chunk IDs are never shown. */
export function Sources({ sources, msgId = "m" }) {
  if (!sources?.length) return null;
  return (
    <div className="sources">
      <h4>Sources</h4>
      {sources.map((s, i) => {
        const n = s.ref || i + 1;
        return (
          <details key={s.chunk_id || i} id={"src-" + msgId + "-" + n}>
            <summary><span className="refnum">{n}</span> <span className="srcname">{s.document_name}</span>
              {s.page ? <span className="muted"> · page {s.page}</span> : null}</summary>
            <blockquote>{s.excerpt}</blockquote>
          </details>
        );
      })}
    </div>
  );
}
