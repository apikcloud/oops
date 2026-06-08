import type { Metadata, RefObject, Structure } from "./types";

export type Attrs = Record<string, unknown>;

export function el(tag: string, attrs: Attrs = {}, children: unknown = []): HTMLElement {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") node.className = String(v);
    else if (k === "html") node.innerHTML = String(v);
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v as EventListener);
    else node.setAttribute(k, String(v));
  }
  for (const child of ([] as unknown[]).concat(children)) {
    if (child == null) continue;
    node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

export const fmt = (n: unknown) => (typeof n === "number" ? n.toLocaleString() : String(n ?? ""));
export const humanize = (k: string) => k.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
export const bareModel = (s?: string) => { if (!s) return "—"; const i = s.indexOf(":"); return i === -1 ? s : s.slice(i + 1); };

// ----- Badges -----

export const badge = (cls?: string | null) => {
  const c = cls || "unknown";
  return el("span", { class: `badge badge-${c}` }, c);
};

export const originBadge = (origin?: string | null) =>
  el("span", { class: `badge ${origin || "unknown"}` }, (origin || "—").replace(/_/g, " "));

// ----- Table helpers -----

export const numCell = (n?: number | null): HTMLElement =>
  el("td", { class: ("num " + (n ? "" : "zero")).trim() }, n != null ? fmt(n) : "0");

export const tableWrap = (table: HTMLElement): HTMLElement => {
  const wrap = el("div", { class: "table-wrap" });
  wrap.appendChild(table);
  return wrap;
};

// ----- renderRef: DocModel ref → DOM node -----

export function renderRef(ref?: RefObject | null): HTMLElement {
  if (!ref) return el("span", { style: "color:var(--text-muted)" }, "—");
  if (ref.kind === "link") {
    const hash = mdPathToHash(ref.path);
    const anchor = ref.anchor ? "#" + ref.anchor : "";
    const name = (ref.path ?? "").replace(/^.*\//, "").replace(/\.md$/, "");
    return el("a", { href: hash + anchor }, name);
  }
  const wrap = el("span", {});
  wrap.appendChild(document.createTextNode(ref.name || "—"));
  if (ref.origin) {
    wrap.appendChild(document.createTextNode(" "));
    wrap.appendChild(originBadge(ref.origin));
  }
  return wrap;
}

export function mdPathToHash(path?: string): string {
  if (!path) return "#/";
  if (path.startsWith("models/"))  return "#/model/"  + path.slice(7).replace(/\.md$/, "");
  if (path.startsWith("methods/")) return "#/method/" + path.slice(8).replace(/\.md$/, "");
  if (path.startsWith("modules/")) return "#/module/" + path.slice(8).replace(/\.md$/, "");
  return "#/";
}

// ----- Metadata bar -----

export function renderMetadataBar(meta?: Metadata | null): HTMLElement | null {
  if (!meta) return null;
  const formatTs = (iso?: string | null) => {
    if (!iso) return null;
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
  };
  const item = (label: string, value?: string | null, cls?: string): HTMLElement | null => {
    if (value == null || value === "") return null;
    return el("div", { class: "meta-item" }, [
      el("span", { class: "label" }, label),
      el("span", { class: cls ? `value ${cls}` : "value" }, String(value)),
    ]);
  };
  const items = [
    item("Project", meta.project_name as string | undefined),
    item("Odoo", meta.odoo_version as string | undefined),
    item("Branch", meta.git_branch as string | undefined),
    item("Commit", meta.git_commit ? String(meta.git_commit).slice(0, 10) : null, "commit"),
    item("Generated", formatTs(meta.generated_at)),
    item("Tool", meta.tool_version as string | undefined),
  ].filter((x): x is HTMLElement => x !== null);
  if (!items.length) return null;
  return el("div", { class: "metadata-bar" }, items);
}

// ----- Structure cards -----

export function renderStructure(structure?: Structure | null): HTMLElement | null {
  if (!structure) return null;
  const grid = el("div", { class: "structure-grid" });

  if (structure.data && Object.keys(structure.data).length) {
    for (const [folder, exts] of Object.entries(structure.data)) {
      const card = el("div", { class: "structure-card" }, [el("div", { class: "sc-title" }, folder)]);
      for (const [ext, count] of Object.entries(exts as Record<string, number>)) {
        card.appendChild(el("div", { class: "sc-line" }, [
          el("span", {}, "." + ext),
          el("span", { class: "v" }, String(count)),
        ]));
      }
      grid.appendChild(card);
    }
  }

  const pyCounters: [string, string][] = [
    ["controllers_py", "Controllers (py)"],
    ["wizard_py", "Wizards (py)"],
    ["report_py", "Reports (py)"],
  ].filter(([k]) => (structure as Record<string, unknown>)[k]) as [string, string][];
  if (pyCounters.length) {
    const card = el("div", { class: "structure-card" }, [el("div", { class: "sc-title" }, "Python")]);
    for (const [k, label] of pyCounters) {
      card.appendChild(el("div", { class: "sc-line" }, [
        el("span", {}, label),
        el("span", { class: "v" }, String((structure as Record<string, unknown>)[k])),
      ]));
    }
    grid.appendChild(card);
  }

  if (structure.static_by_ext && Object.keys(structure.static_by_ext).length) {
    const card = el("div", { class: "structure-card" }, [el("div", { class: "sc-title" }, "Static assets")]);
    for (const [ext, count] of Object.entries(structure.static_by_ext)) {
      card.appendChild(el("div", { class: "sc-line" }, [
        el("span", {}, "." + ext),
        el("span", { class: "v" }, String(count)),
      ]));
    }
    grid.appendChild(card);
  }

  if (!grid.childElementCount) return null;
  const section = el("div", {});
  section.appendChild(el("h4", {}, "Structure"));
  section.appendChild(grid);
  return section;
}

// ----- Method helpers -----

export type MethodKind = "added" | "inherited" | "override";

export function methodKind(m: { is_override?: boolean; is_inherited?: boolean }): MethodKind {
  if (m.is_override)  return "override";
  if (m.is_inherited) return "inherited";
  return "added";
}

export const SECTION_ORDER = [
  "COMPUTE", "SELECTION", "DEFAULT", "ONCHANGE", "CONSTRAINT",
  "CRUD", "HELPER", "ACTION", "BUSINESS", "OTHER",
] as const;

export const SECTION_CLASS: Record<string, string> = {
  COMPUTE: "compute", SELECTION: "other", DEFAULT: "other",
  ONCHANGE: "onchange", CONSTRAINT: "constrain", CRUD: "crud",
  ACTION: "action", HELPER: "helper", BUSINESS: "business", OTHER: "other",
};
