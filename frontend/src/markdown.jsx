import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

// Raw HTML is NOT enabled (no rehype-raw), so model output cannot inject markup or scripts.
const CODE = /(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/g;
const MATH = /(\$\$[\s\S]*?\$\$|\$[^$\n]+\$)/g;

const mapOutside = (text, re, fn) => text.split(re).map((seg, i) => (i % 2 ? seg : fn(seg))).join("");

/** Normalise math delimiters and turn [n] citations into links, leaving code and math untouched. */
export function prepareMarkdown(text, maxRef = 0, msgId = "m") {
  let t = String(text ?? "");
  t = mapOutside(t, CODE, (seg) =>
    seg.replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => "$$" + m + "$$")
       .replace(/\\\(([\s\S]+?)\\\)/g, (_, m) => "$" + m + "$")
       // Put every $$...$$ on its own lines so remark-math treats it as DISPLAY math, not inline.
       .replace(/\$\$([\s\S]+?)\$\$/g, (_, m) => "\n\n$$\n" + m.trim() + "\n$$\n\n"));
  if (maxRef > 0) {
    t = mapOutside(t, CODE, (seg) => mapOutside(seg, MATH, (plain) =>
      plain.replace(/\[(\d+(?:\s*,\s*\d+)*)\](?!\()/g, (all, nums) => {
        const ns = nums.split(/\s*,\s*/).map(Number);
        if (!ns.every((n) => n >= 1 && n <= maxRef)) return all;
        return ns.map((n) => "[" + n + "](#src-" + msgId + "-" + n + ")").join(" ");
      })));
  }
  return t;
}

export function openSource(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.open = true;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 1400);
}

const baseComponents = {
  a({ href, children }) {
    if (href && href.startsWith("#src-")) {
      return <sup><a className="cite" href={href} onClick={(e) => { e.preventDefault(); openSource(href.slice(1)); }}>{children}</a></sup>;
    }
    return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
  },
  table({ children }) { return <div className="table-wrap"><table>{children}</table></div>; },
};

export default function Markdown({ text, maxRef = 0, msgId = "m", inline = false }) {
  const components = inline ? { ...baseComponents, p: ({ children }) => <span>{children}</span> } : baseComponents;
  return (
    <div className={"md" + (inline ? " md-inline" : "")}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: "ignore" }]]} components={components}>
        {prepareMarkdown(text, maxRef, msgId)}
      </ReactMarkdown>
    </div>
  );
}
