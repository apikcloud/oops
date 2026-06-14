import * as d3 from "d3";
import type { MethodNode, MethodStackLayer } from "../types";
import { el, originBadge, methodKind, SECTION_CLASS } from "../dom";
import { fetchSource } from "./detailDrawer";
export { closeDrawer } from "./detailDrawer";

// ---------------------------------------------------------------------------
// Python syntax highlighter
// ---------------------------------------------------------------------------

const KWD = new Set(["False","None","True","and","as","assert","async","await",
  "break","class","continue","def","del","elif","else","except","finally","for",
  "from","global","if","import","in","is","lambda","nonlocal","not","or","pass",
  "raise","return","self","cls","try","while","with","yield"]);

const BUILTIN = new Set(["abs","all","any","bool","bytes","callable","chr",
  "classmethod","dict","dir","enumerate","filter","float","format","frozenset",
  "getattr","hasattr","hash","id","input","int","isinstance","issubclass","iter",
  "len","list","map","max","min","next","object","open","ord","print","property",
  "range","repr","reversed","round","set","setattr","sorted","staticmethod",
  "str","sum","super","tuple","type","vars","zip"]);

// Token regex: order matters (most specific first).
const PY_RE = new RegExp(
  // triple-quoted strings (may span multiple lines)
  "[fFrRbBuU]{0,2}(?:\"\"\"[\\s\\S]*?\"\"\"|'''[\\s\\S]*?''')"
  // comment to end of line
  + "|#[^\\n]*"
  // single-line strings
  + '|[fFrRbBuU]{0,2}(?:"(?:\\\\.|[^"\\\\\\n])*"|\'(?:\\\\.|[^\'\\\\\\n])*\')'
  // decorator
  + "|@[\\w.]+"
  // numbers
  + "|\\b\\d+\\.?\\d*(?:[eE][+-]?\\d+)?[jJ]?\\b|0x[\\da-fA-F]+|0b[01]+|0o[0-7]+"
  // identifiers (keywords, builtins, other)
  + "|\\b[A-Za-z_]\\w*\\b",
  "g"
);

function tokenClass(t: string): string {
  const c = t[0];
  if (c === "#") return "py-cmt";
  if (c === "@") return "py-dec";
  if (c === '"' || c === "'") return "py-str";
  if (c >= "0" && c <= "9") return "py-num";
  if (/^[fFrRbBuU]{1,2}["']/.test(t)) return "py-str";
  if (KWD.has(t)) return "py-kw";
  if (BUILTIN.has(t)) return "py-bi";
  return "";
}

function renderHighlightedCode(code: string, startLine: number): HTMLElement {
  // Collect (class, text) runs spanning the whole code string
  const runs: [string, string][] = [];
  PY_RE.lastIndex = 0;
  let pos = 0;
  let m: RegExpExecArray | null;
  while ((m = PY_RE.exec(code)) !== null) {
    if (m.index > pos) runs.push(["", code.slice(pos, m.index)]);
    runs.push([tokenClass(m[0]), m[0]]);
    pos = m.index + m[0].length;
  }
  if (pos < code.length) runs.push(["", code.slice(pos)]);

  // Render line by line (runs may contain newlines)
  const pre = el("pre", { class: "source-code" });
  let lineNo = startLine;

  function newLine(): HTMLElement {
    const row = el("div", { class: "source-line" });
    row.appendChild(el("span", { class: "source-lineno" }, String(lineNo)));
    const text = el("span", { class: "source-linetext" });
    row.appendChild(text);
    pre.appendChild(row);
    return text;
  }

  let textEl = newLine();
  for (const [cls, text] of runs) {
    const parts = text.split("\n");
    for (let i = 0; i < parts.length; i++) {
      if (i > 0) { lineNo++; textEl = newLine(); }
      if (!parts[i]) continue;
      if (cls) textEl.appendChild(el("span", { class: cls }, parts[i]));
      else textEl.appendChild(document.createTextNode(parts[i]));
    }
  }
  return pre;
}

// ---------------------------------------------------------------------------
// d3 inheritance graph (left panel)
// ---------------------------------------------------------------------------

const NODE_W = 240, NODE_H = 50, GAP = 28;

function originColor(origin: string | undefined): string {
  const key = origin ? `--origin-${origin}` : "--origin-unknown";
  return getComputedStyle(document.documentElement).getPropertyValue(key).trim() || "#9aa1b4";
}

function renderStackGraph(
  stack: MethodStackLayer[],
  onNodeClick: (layer: MethodStackLayer) => void,
): HTMLElement {
  const wrap = el("div", { class: "stack-graph" });
  const w = NODE_W + 40;
  const cx = w / 2;
  const h = stack.length * NODE_H + (stack.length - 1) * GAP + 16;

  const svg = d3.select(wrap)
    .append("svg")
    .attr("viewBox", `0 0 ${w} ${h}`)
    .attr("width", w)
    .attr("height", h);

  for (let i = 0; i < stack.length - 1; i++) {
    const y1 = 8 + i * (NODE_H + GAP) + NODE_H;
    const y2 = 8 + (i + 1) * (NODE_H + GAP);
    svg.append("line").attr("x1", cx).attr("y1", y1).attr("x2", cx).attr("y2", y2 - 5).attr("class", "stack-edge");
    svg.append("polygon").attr("points", `${cx - 5},${y2 - 5} ${cx + 5},${y2 - 5} ${cx},${y2}`).attr("class", "stack-arrow");
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rects: d3.Selection<SVGRectElement, unknown, any, undefined>[] = [];
  stack.forEach((layer, i) => {
    const y = 8 + i * (NODE_H + GAP);
    const color = originColor(layer.origin);
    const g = svg.append("g").attr("class", "stack-node-g")
      .attr("transform", `translate(${cx - NODE_W / 2}, ${y})`).style("cursor", "pointer");

    const rect = g.append("rect").attr("width", NODE_W).attr("height", NODE_H).attr("rx", 6)
      .attr("class", "stack-node-rect").attr("fill", color).attr("fill-opacity", 0.1)
      .attr("stroke", color).attr("stroke-width", 1.5);
    rects.push(rect);

    const label = (layer.module ?? "—").length > 24
      ? (layer.module ?? "—").slice(0, 22) + "…" : (layer.module ?? "—");
    g.append("text").attr("x", 10).attr("y", 20).attr("fill", color)
      .style("font-family", "var(--mono)").style("font-size", "0.76rem").style("font-weight", "600").text(label);

    const badges = [
      layer.is_override && "override",
      layer.has_super && "super",
      layer.reachable === false && "unreachable",
    ].filter(Boolean) as string[];
    const sub = badges.length ? badges.join(" · ")
      : layer.source_file ? (layer.source_file.length > 28 ? "…" + layer.source_file.slice(-26) : layer.source_file) : "";
    if (sub) g.append("text").attr("x", 10).attr("y", 38)
      .style("font-size", "0.64rem").style("fill", "var(--text-muted)").style("font-family", "var(--mono)").text(sub);

    g.on("click", () => {
      rects.forEach((r, j) => r.attr("stroke-width", j === i ? 3 : 1.5));
      onNodeClick(layer);
    });
  });
  if (rects.length) rects[0].attr("stroke-width", 3);
  return wrap;
}

// ---------------------------------------------------------------------------
// Full-screen method view singleton
// ---------------------------------------------------------------------------

interface MethodViewState {
  overlay: HTMLElement;
  panel: HTMLElement;
  header: HTMLElement;
  meta: HTMLElement;
  code: HTMLElement;
  close(): void;
}

let _mv: MethodViewState | null = null;

function ensureMethodView(): MethodViewState {
  if (_mv) return _mv;

  const overlay = el("div", { class: "mv-overlay" });
  const panel   = el("div", { class: "mv-panel" });
  const header  = el("div", { class: "mv-header" });
  const closeBtn = el("button", { class: "mv-close", "aria-label": "Close" }, "✕");
  const body    = el("div", { class: "mv-body" });
  const meta    = el("div", { class: "mv-meta" });
  const code    = el("div", { class: "mv-code" });

  header.appendChild(closeBtn);
  body.appendChild(meta);
  body.appendChild(code);
  panel.appendChild(header);
  panel.appendChild(body);
  document.body.appendChild(overlay);
  document.body.appendChild(panel);

  const close = () => {
    panel.classList.remove("mv-open");
    overlay.classList.remove("mv-overlay-visible");
  };
  closeBtn.addEventListener("click", close);
  overlay.addEventListener("click", close);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });

  _mv = { overlay, panel, header, meta, code, close };
  return _mv;
}

export function closeMethodView(): void {
  _mv?.close();
}

// ---------------------------------------------------------------------------
// openMethodDrawer — public entry point
// ---------------------------------------------------------------------------

export function openMethodDrawer(m: MethodNode): void {
  const { overlay, panel, header, meta, code } = ensureMethodView();
  meta.innerHTML = "";
  code.innerHTML = "";

  // Reset header: insert title before close button
  const closeBtn = header.querySelector(".mv-close")!;
  // Remove any previous title
  for (const c of Array.from(header.children)) {
    if (!c.classList.contains("mv-close")) c.remove();
  }
  const kind = methodKind(m);
  const sig  = [m.signature, ...(m.decorators ?? [])].filter(Boolean).join("\n");
  const mAny = m as Record<string, unknown>;

  const title = el("div", { class: "mv-title" }, [
    el("span", { class: "mv-method-name mono" }, m.name || "—"),
    el("span", { class: `ft-chip ${SECTION_CLASS[m.section ?? "OTHER"] ?? "other"}` }, m.section ?? "OTHER"),
    el("span", { class: `kind-pill kind-${kind}` }, kind),
  ]);
  header.insertBefore(title, closeBtn);

  // --- Meta panel ---
  const mLabel = (text: string) => el("div", { class: "drawer-label" }, text);

  if (kind === "override" && m.overrides) {
    const ov = m.overrides as Record<string, string>;
    meta.appendChild(el("div", { class: "drawer-row" }, [
      el("span", { class: "drawer-label" }, "Overrides"),
      el("span", {}, [(ov["module"] ?? ov["origin_module"] ?? "—") + " ", ov["origin"] ? originBadge(ov["origin"]) : null]),
    ]));
  } else if (kind === "inherited" && mAny["inherited_from"]) {
    const ih = mAny["inherited_from"] as Record<string, string>;
    meta.appendChild(el("div", { class: "drawer-row" }, [
      el("span", { class: "drawer-label" }, "Inherited from"),
      el("span", {}, [(ih["origin_module"] ?? "—") + " ", ih["origin"] ? originBadge(ih["origin"]) : null]),
    ]));
  }

  if (m.docstring) {
    meta.appendChild(mLabel("Docstring"));
    meta.appendChild(el("p", { class: "drawer-docstring" }, String(m.docstring)));
  }
  if (sig) {
    meta.appendChild(mLabel("Signature"));
    meta.appendChild(el("pre", { class: "drawer-sig" }, sig));
  }

  // --- Code loading helper ---
  const loadCode = async (layer: MethodStackLayer | null) => {
    code.innerHTML = "";
    if (!layer?.source_file || layer.line_start == null) {
      code.appendChild(el("p", { class: "mv-code-unavail" }, "Source not available."));
      return;
    }
    code.appendChild(el("p", { class: "mv-loading" }, "Loading…"));
    const src = await fetchSource(layer.source_file, layer.line_start, layer.line_end ?? layer.line_start);
    code.innerHTML = "";
    if (src != null) {
      code.appendChild(renderHighlightedCode(src, layer.line_start));
    } else {
      code.appendChild(el("p", { class: "mv-code-unavail" }, "Source not available."));
    }
  };

  // --- Stack / inheritance ---
  if (m.stack && m.stack.length > 0) {
    const stack = m.stack as MethodStackLayer[];

    if (stack.length > 1) {
      meta.appendChild(mLabel(`Inheritance chain (${stack.length} layers)`));
      meta.appendChild(renderStackGraph(stack, (layer) => {
        // Update source file/line label in meta
        const pathLabel = meta.querySelector(".mv-src-path");
        if (pathLabel && layer.source_file) {
          pathLabel.textContent = layer.source_file
            + (layer.line_start != null ? `:${layer.line_start}` : "")
            + (layer.line_end != null && layer.line_end !== layer.line_start ? `–${layer.line_end}` : "");
        }
        void loadCode(layer);
      }));
    }

    const top = stack[0];
    if (top.source_file) {
      meta.appendChild(mLabel("Source"));
      const sfText = top.source_file
        + (top.line_start != null ? `:${top.line_start}` : "")
        + (top.line_end != null && top.line_end !== top.line_start ? `–${top.line_end}` : "");
      meta.appendChild(el("div", { class: "drawer-path mono mv-src-path" }, sfText));
    }
    void loadCode(top);
  } else if (mAny["source_file"]) {
    meta.appendChild(mLabel("Source"));
    meta.appendChild(el("div", { class: "drawer-path mono" }, String(mAny["source_file"])));
    void loadCode({
      source_file: String(mAny["source_file"]),
      line_start: m.line_start,
      line_end: m.line_end,
    });
  }

  panel.classList.add("mv-open");
  overlay.classList.add("mv-overlay-visible");
}
