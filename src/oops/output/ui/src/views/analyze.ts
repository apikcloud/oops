import type { Payload, FieldNode, MethodNode, ModelNode, Structure } from "../types";
import type { Source } from "../source";
import {
  el, fmt, humanize, badge, numCell, tableWrap,
  renderMetadataBar, renderStructure,
  originBadge, methodKind,
} from "../dom";
import { manifestGrid } from "../components/manifestGrid";
import { fieldsTable }  from "../components/fieldsTable";
import { methodsTable } from "../components/methodsTable";

// ---------------------------------------------------------------------------
// Analyze-specific types (flat payload, no models_by_bare)
// ---------------------------------------------------------------------------

interface AnalyzeLoc {
  python: number; xml: number; javascript: number; docs: number;
  total?: number; pct?: number;
}

interface AnalyzeModelNode extends ModelNode {
  class_name?: string;
  description?: string;
  description_inherited_from?: string;
  ancestor_model?: string;
  inherit_origin?: string;
  is_new_model?: boolean;
  missing_description?: boolean;
}

interface AnalyzeModuleEntry {
  module: string;
  manifest?: Record<string, unknown>;
  readme?: { present?: boolean; format?: string; path?: string; content?: string };
  depends?: string[];
  models?: AnalyzeModelNode[];
  fields?: FieldNode[];
  methods?: MethodNode[];
  views?: Array<Record<string, unknown>>;
  structure?: Structure & { demo?: number };
  metrics?: Record<string, unknown>;
  loc?: AnalyzeLoc;
  not_analysed?: string[];
  warnings?: string[];
}

interface AnalyzePayload {
  modules: AnalyzeModuleEntry[];
  warnings?: string[];
  metadata: Payload["metadata"];
}

// ---------------------------------------------------------------------------

export function viewAnalyze(root: HTMLElement, payload: Payload, _source: Source): void {
  const p = payload as unknown as AnalyzePayload;
  const modules  = p.modules  ?? [];
  const warnings = p.warnings ?? [];

  const metaBar = renderMetadataBar(p.metadata);
  if (metaBar) root.appendChild(metaBar);

  root.appendChild(el("div", { class: "page-header" }, [
    el("h1", {}, "Module Analysis"),
    el("p", { class: "page-subtitle" },
      `${modules.length} module${modules.length !== 1 ? "s" : ""} analysed`),
  ]));

  if (warnings.length) {
    root.appendChild(el("div", { class: "warnings" }, [
      el("ul", {}, warnings.map((w) => el("li", {}, w))),
    ]));
  }

  for (const mod of modules) {
    root.appendChild(_renderModule(mod));
  }
}

// ---------------------------------------------------------------------------
// Per-module section
// ---------------------------------------------------------------------------

function _renderModule(mod: AnalyzeModuleEntry): HTMLElement {
  const section = el("section", { class: "module" });
  const mfst    = mod.manifest ?? {};
  const version = mfst["version"] as string | undefined;

  // Header
  const h2 = el("h2", {}, [
    mod.module ?? "—",
    " ",
    version ? el("span", { class: "badge outline" }, version) : null,
  ]);
  section.appendChild(h2);

  // Manifest (skip version — already shown)
  const mfstWithoutVersion = Object.fromEntries(
    Object.entries(mfst).filter(([k]) => k !== "version")
  );
  section.appendChild(manifestGrid(mfstWithoutVersion));

  // README
  if (mod.readme?.present) {
    section.appendChild(el("h4", {}, `Readme (${mod.readme.format ?? "?"})`));
    section.appendChild(el("div", { class: "chip-list" }, [
      el("span", { class: "chip" }, mod.readme.path ?? "present"),
    ]));
  }

  // Depends
  if (mod.depends?.length) {
    section.appendChild(el("h4", {}, `Depends (${mod.depends.length})`));
    section.appendChild(el("div", { class: "chip-list" },
      mod.depends.map((d) => el("span", { class: "chip" }, d))
    ));
  }

  // Module warnings
  if (mod.warnings?.length) {
    section.appendChild(el("div", { class: "warnings" }, [
      el("ul", {}, mod.warnings.map((w) => el("li", {}, w))),
    ]));
  }

  // Metrics
  if (mod.metrics && Object.keys(mod.metrics).length) {
    section.appendChild(el("h4", {}, "Metrics"));
    section.appendChild(_metricsGrid(mod.metrics));
  }

  // LoC
  if (mod.loc?.total) {
    section.appendChild(el("h4", {}, "Lines of code"));
    section.appendChild(_locGrid(mod.loc));
  }

  // Structure
  if (mod.structure) {
    section.appendChild(renderStructure(mod.structure) ?? el("span", {}));
  }

  // Models
  const models  = mod.models ?? [];
  const fields  = mod.fields  ?? [];
  const methods = mod.methods ?? [];

  if (models.length) {
    section.appendChild(el("h2", {}, `Models (${models.length})`));

    // Group fields + methods by model id
    const fieldsByModel  = new Map<string, FieldNode[]>();
    const methodsByModel = new Map<string, MethodNode[]>();
    for (const f of fields) {
      const mid = (f["model"] as string | undefined) ?? "";
      if (!fieldsByModel.has(mid)) fieldsByModel.set(mid, []);
      fieldsByModel.get(mid)!.push(f);
    }
    for (const m of methods) {
      const mid = (m["model"] as string | undefined) ?? "";
      if (!methodsByModel.has(mid)) methodsByModel.set(mid, []);
      methodsByModel.get(mid)!.push(m);
    }

    const newModels = models.filter((m) => m.status === "new" || m.is_new_model).sort(_byModel);
    const extModels = models.filter((m) => m.status !== "new" && !m.is_new_model).sort(_byModel);

    if (newModels.length) {
      section.appendChild(el("h3", {}, `New models (${newModels.length})`));
      section.appendChild(_newModelsTable(newModels, fieldsByModel, methodsByModel));
    }
    if (extModels.length) {
      section.appendChild(el("h3", {}, `Extensions (${extModels.length})`));
      section.appendChild(_extensionsTable(extModels, fieldsByModel, methodsByModel));
    }
  }

  // Views
  if (mod.views?.length) {
    section.appendChild(_viewsSection(mod.views));
  }

  // Not analysed
  if (mod.not_analysed?.length) {
    section.appendChild(el("h4", {}, "Not analysed"));
    section.appendChild(el("div", { class: "chip-list" },
      mod.not_analysed.map((p) => el("span", { class: "chip" }, p))
    ));
  }

  return section;
}

// ---------------------------------------------------------------------------
// Models tables with inline accordion detail
// ---------------------------------------------------------------------------

const _byModel = (a: AnalyzeModelNode, b: AnalyzeModelNode) =>
  (a.model ?? "").localeCompare(b.model ?? "");

function _newModelsTable(
  models: AnalyzeModelNode[],
  fieldsByModel: Map<string, FieldNode[]>,
  methodsByModel: Map<string, MethodNode[]>,
): HTMLElement {
  const container = el("div", {});
  const table = el("table", {});
  table.appendChild(el("thead", {}, [el("tr", {}, [
    el("th", {}, "Model"),
    el("th", {}, "Description"),
    el("th", { class: "num" }, "Fields"),
    el("th", { class: "num" }, "Methods"),
  ])]));
  const tbody = el("tbody", {});

  for (const m of models) {
    const mFields  = fieldsByModel.get(m.id)  ?? [];
    const mMethods = methodsByModel.get(m.id) ?? [];
    const detailEl = _modelDetail(m, mFields, mMethods);

    const tr = el("tr", { class: "clickable" }, [
      el("td", { class: "mono" }, m.model ?? "—"),
      el("td", { class: "muted" }, m.description ?? "—"),
      numCell(mFields.length),
      numCell(mMethods.length),
    ]);
    tr.addEventListener("click", () => _toggleDetail(tr, detailEl));
    tbody.appendChild(tr);
    tbody.appendChild(el("tr", { class: "detail-row hidden" }, [
      el("td", { colspan: "4", style: "padding:0" }, detailEl),
    ]));
  }

  table.appendChild(tbody);
  container.appendChild(tableWrap(table));
  return container;
}

function _extensionsTable(
  models: AnalyzeModelNode[],
  fieldsByModel: Map<string, FieldNode[]>,
  methodsByModel: Map<string, MethodNode[]>,
): HTMLElement {
  const container = el("div", {});
  const table = el("table", {});
  table.appendChild(el("thead", {}, [el("tr", {}, [
    el("th", {}, "Model"),
    el("th", {}, "Ancestor module"),
    el("th", {}, "Origin"),
    el("th", { class: "num", title: "New fields" }, "F+"),
    el("th", { class: "num", title: "Extended fields" }, "F~"),
    el("th", { class: "num" }, "Methods"),
    el("th", { class: "num", title: "Overrides" }, "M↑"),
  ])]));
  const tbody = el("tbody", {});

  for (const m of models) {
    const mFields  = fieldsByModel.get(m.id)  ?? [];
    const mMethods = methodsByModel.get(m.id) ?? [];
    const detailEl = _modelDetail(m, mFields, mMethods);

    const ownF  = mFields.filter((f) => f.origin_status === "new" || f.origin_status === "base").length;
    const extF  = mFields.filter((f) => f.origin_status === "extended").length;
    const overM = mMethods.filter((m) => methodKind(m) === "override").length;

    const tr = el("tr", { class: "clickable" }, [
      el("td", { class: "mono" }, m.model ?? "—"),
      el("td", { class: "muted mono" }, m.ancestor_module ?? "—"),
      el("td", {}, m.inherit_origin ? originBadge(m.inherit_origin) : "—"),
      numCell(ownF), numCell(extF),
      numCell(mMethods.length), numCell(overM),
    ]);
    tr.addEventListener("click", () => _toggleDetail(tr, detailEl));
    tbody.appendChild(tr);
    tbody.appendChild(el("tr", { class: "detail-row hidden" }, [
      el("td", { colspan: "7", style: "padding:0" }, detailEl),
    ]));
  }

  table.appendChild(tbody);
  container.appendChild(tableWrap(table));
  return container;
}

function _toggleDetail(tr: HTMLElement, detailEl: HTMLElement): void {
  // find the detail row sibling
  const detailRow = tr.nextElementSibling as HTMLElement | null;
  if (!detailRow) return;
  const isOpen = !detailRow.classList.contains("hidden");
  if (isOpen) {
    detailRow.classList.add("hidden");
    detailEl.innerHTML = "";
  } else {
    detailRow.classList.remove("hidden");
    if (!detailEl.children.length) _populateDetail(detailEl);
  }
}

function _populateDetail(detailEl: HTMLElement): void {
  // detail was pre-built during table construction; just reveal it
  // (already populated by _modelDetail, nothing extra to do here)
}

function _modelDetail(
  m: AnalyzeModelNode,
  mFields: FieldNode[],
  mMethods: MethodNode[],
): HTMLElement {
  const wrap = el("div", { class: "model-detail-panel" });

  // Info cards
  const info = el("div", { class: "model-detail-info" });
  info.appendChild(el("div", { class: "di-row" }, [
    el("span", { class: "di-label" }, "Model"),
    el("span", { class: "mono" }, m.model ?? "—"),
  ]));
  if (m.class_name) info.appendChild(el("div", { class: "di-row" }, [
    el("span", { class: "di-label" }, "Class"),
    el("span", { class: "mono" }, m.class_name),
  ]));
  info.appendChild(el("div", { class: "di-row" }, [
    el("span", { class: "di-label" }, "Status"),
    el("span", { class: "status-pill" }, m.status ?? "—"),
  ]));
  if (m.ancestor_module) info.appendChild(el("div", { class: "di-row" }, [
    el("span", { class: "di-label" }, "Ancestor module"),
    el("span", { class: "mono" }, m.ancestor_module),
  ]));
  if (m.ancestor_model) info.appendChild(el("div", { class: "di-row" }, [
    el("span", { class: "di-label" }, "Ancestor model"),
    el("span", { class: "mono" }, m.ancestor_model),
  ]));
  if (m.inherit_origin) info.appendChild(el("div", { class: "di-row" }, [
    el("span", { class: "di-label" }, "Ancestor origin"),
    originBadge(m.inherit_origin),
  ]));
  if (m.description) info.appendChild(el("div", { class: "di-row" }, [
    el("span", { class: "di-label" }, "Description"),
    el("span", {}, m.description + (m.description_inherited_from ? ` (from ${m.description_inherited_from})` : "")),
  ]));
  wrap.appendChild(info);

  // Fields
  if (mFields.length) {
    const ft = fieldsTable(mFields, undefined);
    wrap.appendChild(ft.h2);
    wrap.appendChild(ft.chipsContainer);
    wrap.appendChild(ft.element);
  }

  // Methods
  if (mMethods.length) {
    const mt = methodsTable(mMethods);
    wrap.appendChild(mt.h2);
    wrap.appendChild(mt.chipsContainer);
    wrap.appendChild(mt.element);
  }

  return wrap;
}

// ---------------------------------------------------------------------------
// Views section
// ---------------------------------------------------------------------------

function _viewsSection(views: Array<Record<string, unknown>>): HTMLElement {
  const section = el("div", {});
  section.appendChild(el("h4", {}, `Views (${views.length})`));

  const byType: Record<string, number> = {};
  for (const v of views) {
    const t = String(v["type"] ?? "?");
    byType[t] = (byType[t] ?? 0) + 1;
  }

  const chips = el("div", {});
  Object.entries(byType).sort((a, b) => b[1] - a[1]).forEach(([t, n]) => {
    chips.appendChild(el("span", { class: "ft-chip" }, [t, el("span", { class: "count" }, n)]));
  });
  section.appendChild(chips);
  return section;
}

// ---------------------------------------------------------------------------
// Metric grids
// ---------------------------------------------------------------------------

const METRIC_LABELS: Record<string, string> = {
  models: "Models", own_fields: "Own fields", inherited_fields: "Inherited fields",
  methods: "Methods", inherited_methods: "Inherited", overridden_methods: "Overrides",
  missing_docs: "Missing docs", models_missing_description: "Models w/o desc",
  data: "Data records", primary_views: "Primary views", extension_views: "Ext. views",
  extension_views_upstream: "Upstream ext.", actions: "Actions",
  menus: "Menus", unresolved_views: "Unresolved views",
};

const LOC_LABELS: Record<string, string> = {
  python: "Python", xml: "XML", javascript: "JS", docs: "Docs", total: "Total", pct: "% of project",
};

function _metricsGrid(metrics: Record<string, unknown>): HTMLElement {
  const grid = el("div", { class: "metrics-grid" });
  Object.entries(metrics).forEach(([key, value]) => {
    const zero = !value;
    grid.appendChild(el("div", { class: "metric" + (zero ? " zero" : "") }, [
      el("div", { class: "metric-value" }, String(value ?? "—")),
      el("div", { class: "metric-label" }, METRIC_LABELS[key] ?? humanize(key)),
    ]));
  });
  return grid;
}

function _locGrid(loc: AnalyzeLoc): HTMLElement {
  const grid = el("div", { class: "metrics-grid" });
  const entries: [string, number | undefined][] = [
    ["python", loc.python], ["xml", loc.xml], ["javascript", loc.javascript],
    ["docs", loc.docs], ["total", loc.total],
  ];
  if (loc.pct) entries.push(["pct", loc.pct]);
  entries.forEach(([key, value]) => {
    if (value == null) return;
    const display = key === "pct" ? `${value}%` : fmt(value);
    const zero = !value;
    grid.appendChild(el("div", { class: "metric" + (zero ? " zero" : "") }, [
      el("div", { class: "metric-value" }, display),
      el("div", { class: "metric-label" }, LOC_LABELS[key] ?? humanize(key)),
    ]));
  });
  return grid;
}
