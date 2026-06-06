import * as d3 from "d3";
import Fuse from "fuse.js";
import type { Payload, ServePayload, ModuleEntry, BareModelEntry, Schema, InventoryNode, Loc } from "../types";
import type { Source } from "../source";
import {
  el, fmt, badge, numCell, tableWrap,
  renderMetadataBar, renderStructure,
  methodKind,
} from "../dom";
import { manifestGrid }    from "../components/manifestGrid";
import { provenanceTable } from "../components/provenanceTable";
import { fieldsTable }     from "../components/fieldsTable";
import { methodsTable }    from "../components/methodsTable";
import { closeDrawer }     from "../components/methodDrawer";

// ---------------------------------------------------------------------------
// Fuse.js search index (lazy, rebuilt per payload)
// ---------------------------------------------------------------------------

interface SearchEntry {
  kind: "module" | "model" | "field" | "method";
  id: string;
  label: string;
  module: string;
  model?: string;
  section?: string;
  text: string;
  hash: string;
}

function buildSearchIndex(modules: ModuleEntry[], modelsByBare: Record<string, BareModelEntry>): Fuse<SearchEntry> {
  const entries: SearchEntry[] = [];

  for (const mod of modules) {
    const name  = mod.module ?? "";
    const mfst  = mod.manifest ?? {};
    entries.push({
      kind: "module", id: name,
      label: String(mfst["name"] ?? name), module: name,
      text: [name, mfst["name"], mfst["summary"], mfst["author"]].filter(Boolean).join(" "),
      hash: "#/module/" + encodeURIComponent(name),
    });
    for (const f of mod.fields ?? []) {
      const bare  = ((f["model"] as string | undefined) ?? "").replace(/^[^:]+:/, "");
      const label = f.label ?? (f.label_inferred
        ? (f.name ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
        : f.name ?? "");
      entries.push({
        kind: "field", id: f.id ?? `${name}:${bare}#${f.name ?? ""}`,
        label, module: name, model: bare,
        text: [f.name, label, f.help, f.type].filter(Boolean).join(" "),
        hash: "#/model/" + encodeURIComponent(bare),
      });
    }
    for (const m of mod.methods ?? []) {
      const bare = ((m as Record<string, unknown>)["model"] as string ?? "").replace(/^[^:]+:/, "");
      entries.push({
        kind: "method", id: m.id ?? `${name}:${bare}#method:${m.name ?? ""}`,
        label: m.name ?? "", module: name, model: bare, section: m.section,
        text: [m.name, m.docstring].filter(Boolean).join(" "),
        hash: "#/model/" + encodeURIComponent(bare),
      });
    }
  }

  for (const [bare, entry] of Object.entries(modelsByBare)) {
    entries.push({
      kind: "model", id: bare, label: bare,
      module: (entry.contributions ?? []).map((c) => c.module).join(", "),
      text: [bare, entry.description].filter(Boolean).join(" "),
      hash: "#/model/" + encodeURIComponent(bare),
    });
  }

  return new Fuse(entries, {
    keys: ["label", "id", "text"],
    threshold: 0.3,
    minMatchCharLength: 2,
  });
}

// ---------------------------------------------------------------------------
// viewServe: contained router + all sub-views
// ---------------------------------------------------------------------------

export function viewServe(root: HTMLElement, payload: Payload, _source: Source): void {
  const p = payload as unknown as ServePayload;
  const modules      = p.modules       ?? [];
  const modelsByBare = p.models_by_bare ?? {};
  const schema       = p.schema;

  let fuseIndex: Fuse<SearchEntry> | null = null;
  const getIndex = () => {
    if (!fuseIndex) fuseIndex = buildSearchIndex(modules, modelsByBare);
    return fuseIndex;
  };

  const modClassification = (name: string) =>
    modules.find((m) => m.module === name)?.inventory?.classification ?? "unknown";

  // Inject persistent nav into the header (once per page load).
  const headerInner = document.querySelector<HTMLElement>(".site-header-inner");
  if (headerInner && !headerInner.querySelector(".site-nav")) {
    headerInner.appendChild(el("nav", { class: "site-nav" }, [
      el("a", { href: "#/" }, "Addons"),
      el("a", { href: "#/search" }, "Search"),
    ]));
  }

  // --- Router ---
  const ROUTES: Array<{ re: RegExp; view(m: RegExpMatchArray): HTMLElement }> = [
    { re: /^#\/module\/(.+)$/, view: (m) => _viewModule(decodeURIComponent(m[1]!)) },
    { re: /^#\/model\/(.+)$/,  view: (m) => _viewModel(decodeURIComponent(m[1]!)) },
    { re: /^#\/search$/,       view: () => _viewSearch() },
    { re: /^(#\/?)?$/,         view: () => _viewIndex() },
  ];

  function route() {
    const hash = location.hash || "#/";
    root.innerHTML = "";
    closeDrawer();
    for (const r of ROUTES) {
      const m = hash.match(r.re);
      if (m) { root.appendChild(r.view(m)); return; }
    }
    root.appendChild(el("p", { class: "placeholder" }, "Page not found: " + hash));
  }

  window.addEventListener("hashchange", route);
  route();

  // ---------------------------------------------------------------------------
  // Index view (#/)
  // ---------------------------------------------------------------------------

  function _viewIndex(): HTMLElement {
    const wrap = el("div", {});

    const cs = getComputedStyle(document.documentElement);
    const CCOLORS: Record<string, string> = {
      oca:          cs.getPropertyValue("--oca").trim(),
      custom:       cs.getPropertyValue("--custom").trim(),
      "third-party": cs.getPropertyValue("--third-party").trim(),
    };
    const LCOLORS: Record<string, string> = {
      python:     cs.getPropertyValue("--loc-python").trim(),
      xml:        cs.getPropertyValue("--loc-xml").trim(),
      javascript: cs.getPropertyValue("--loc-javascript").trim(),
      docs:       cs.getPropertyValue("--loc-docs").trim(),
    };

    let totalLoc = 0;
    const byClass: Record<string, number> = {};
    const locTotals: Record<string, number> = { python: 0, xml: 0, javascript: 0, docs: 0 };
    for (const mod of modules) {
      const inv = (mod.inventory ?? {}) as InventoryNode;
      const cls = inv.classification ?? "unknown";
      byClass[cls] = (byClass[cls] ?? 0) + 1;
      const loc = (inv.loc ?? {}) as Partial<Loc>;
      const lt  = (loc.python ?? 0) + (loc.xml ?? 0) + (loc.javascript ?? 0) + (loc.docs ?? 0);
      mod._locTotal = lt;
      totalLoc += loc.total ?? lt;
      for (const k of Object.keys(LCOLORS)) locTotals[k] += (loc as Record<string, number>)[k] ?? 0;
    }

    const metaBar = renderMetadataBar(p.metadata);
    if (metaBar) wrap.appendChild(metaBar);

    wrap.appendChild(el("div", { class: "page-header" }, [
      el("h1", {}, "Project Addons"),
      el("p", { class: "page-subtitle" }, [
        `${modules.length} addons · ${fmt(totalLoc)} total LoC · `,
        el("a", { href: "#/search" }, "Search →"),
      ]),
    ]));

    // Charts
    const donutContainer = el("div", { class: "chart-container" });
    const donutLegend    = el("div", { class: "legend" });
    const locContainer   = el("div", { class: "chart-container" });
    const locLegend      = el("div", { class: "legend" });
    wrap.appendChild(el("div", { class: "charts-row" }, [
      el("div", { class: "chart-card" }, [el("h3", {}, "By classification"), donutContainer, donutLegend]),
      el("div", { class: "chart-card" }, [el("h3", {}, "Lines of code by type"), locContainer, locLegend]),
    ]));

    setTimeout(() => {
      const cData = Object.entries(byClass).map(([key, value]) => ({ key, value })).sort((a, b) => b.value - a.value);
      if (cData.length) {
        const w = 220, h = 220, r = Math.min(w, h) / 2;
        const svg = d3.select(donutContainer).append("svg")
          .attr("viewBox", `${-w / 2} ${-h / 2} ${w} ${h}`).attr("width", w).attr("height", h);
        const pie = d3.pie<typeof cData[0]>().value((d) => d.value).sort(null);
        const arc = d3.arc<d3.PieArcDatum<typeof cData[0]>>().innerRadius(r * 0.55).outerRadius(r - 5);
        svg.selectAll("path").data(pie(cData)).join("path")
          .attr("d", arc).attr("fill", (d) => CCOLORS[d.data.key] ?? "#999")
          .attr("stroke", "white").attr("stroke-width", 2);
        svg.append("text").attr("text-anchor", "middle").attr("dy", "-0.2em")
          .style("font-size", "1.4rem").style("font-weight", "600").style("font-family", "var(--mono)").text(modules.length);
        svg.append("text").attr("text-anchor", "middle").attr("dy", "1.2em")
          .style("font-size", ".7rem").style("fill", "var(--text-muted)")
          .style("text-transform", "uppercase").style("letter-spacing", ".05em").text("addons");
        cData.forEach((d) => {
          const li = d3.select(donutLegend).append("div").attr("class", "legend-item");
          li.append("span").attr("class", "legend-swatch").style("background", CCOLORS[d.key] ?? "#999");
          li.append("span").text(`${d.key} (${d.value})`);
        });
      }

      const lData = Object.entries(locTotals).filter(([, v]) => v > 0).map(([key, value]) => ({ key, value }));
      if (lData.length) {
        const w = 300, h = 220, m = { top: 10, right: 10, bottom: 28, left: 52 };
        const iW = w - m.left - m.right, iH = h - m.top - m.bottom;
        const svg = d3.select(locContainer).append("svg")
          .attr("viewBox", `0 0 ${w} ${h}`).attr("width", w).attr("height", h);
        const g = svg.append("g").attr("transform", `translate(${m.left},${m.top})`);
        const x = d3.scaleBand().domain(lData.map((d) => d.key)).range([0, iW]).padding(0.3);
        const y = d3.scaleLinear().domain([0, d3.max(lData, (d) => d.value) ?? 0]).nice().range([iH, 0]);
        g.selectAll("rect").data(lData).join("rect")
          .attr("x", (d) => x(d.key) ?? 0).attr("y", (d) => y(d.value))
          .attr("width", x.bandwidth()).attr("height", (d) => iH - y(d.value))
          .attr("fill", (d) => LCOLORS[d.key] ?? "#999").attr("rx", 2);
        g.selectAll<SVGTextElement, typeof lData[0]>("text.bar-label").data(lData).join("text")
          .attr("class", "bar-label")
          .attr("x", (d) => (x(d.key) ?? 0) + x.bandwidth() / 2).attr("y", (d) => y(d.value) - 4)
          .attr("text-anchor", "middle").style("font-size", ".7rem").style("font-family", "var(--mono)")
          .style("fill", "var(--text-muted)").text((d) => fmt(d.value));
        g.append("g").attr("transform", `translate(0,${iH})`)
          .call(d3.axisBottom(x).tickSize(0).tickPadding(8))
          .call((ax) => ax.select(".domain").remove())
          .selectAll("text").style("font-size", ".75rem").style("fill", "var(--text-muted)");
        g.append("g")
          .call(d3.axisLeft(y).ticks(5).tickFormat(d3.format("~s")))
          .call((ax) => ax.select(".domain").remove())
          .selectAll("text").style("font-size", ".7rem").style("fill", "var(--text-muted)");
        lData.forEach((d) => {
          const li = d3.select(locLegend).append("div").attr("class", "legend-item");
          li.append("span").attr("class", "legend-swatch").style("background", LCOLORS[d.key] ?? "");
          li.append("span").text(`${d.key} (${fmt(d.value)})`);
        });
      }
    }, 0);

    // Filter + sortable table
    const state = { sortKey: "_locTotal", sortDir: "desc" as "asc" | "desc", classification: "all", search: "" };

    wrap.appendChild(el("h2", {}, "All addons"));
    const filtersEl = el("div", { class: "filters" });
    const searchInput = el("input", {
      type: "search", class: "search-input", placeholder: "Search addons…", autocomplete: "off",
    }) as HTMLInputElement;
    filtersEl.append(searchInput);

    const pillDefs = [
      { label: "All", cls: "all" },
      { label: "OCA", cls: "oca" },
      { label: "Custom", cls: "custom" },
      { label: "Third-party", cls: "third-party" },
    ];
    const pillBtns = pillDefs.map(({ label, cls }) => {
      const count = cls === "all" ? modules.length : (byClass[cls] ?? 0);
      const btn = el("button", { class: "filter-btn" + (cls === "all" ? " active" : ""), "data-cls": cls },
        [label, el("span", { class: "filter-count" }, count)]);
      btn.addEventListener("click", () => {
        pillBtns.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.classification = cls;
        renderTable();
      });
      filtersEl.append(btn);
      return btn;
    });
    wrap.append(filtersEl);

    const thead = el("thead", {}, [el("tr", {}, [
      el("th", { class: "sortable", "data-sort": "module" }, "Addon"),
      el("th", { class: "sortable", "data-sort": "classification" }, "Type"),
      el("th", { class: "sortable", "data-sort": "version" }, "Version"),
      el("th", { class: "num sortable", "data-sort": "_locTotal" }, "LoC"),
      el("th", {}, "Breakdown"),
    ])]);
    for (const th of thead.querySelectorAll<HTMLElement>("th[data-sort]")) {
      th.addEventListener("click", () => {
        const key = th.dataset["sort"]!;
        state.sortDir = state.sortKey === key && state.sortDir === "desc" ? "asc" : "desc";
        state.sortKey = key;
        renderTable();
      });
    }

    const tbody = el("tbody", {});
    const emptyState = el("div", { class: "empty-state" }, "No addons match.");
    (emptyState as HTMLElement).style.display = "none";
    wrap.append(tableWrap(el("table", {}, [thead, tbody])));
    wrap.append(emptyState);

    function renderTable() {
      tbody.innerHTML = "";
      const query    = state.search.toLowerCase();
      const filtered = modules.filter((mod) => {
        const inv  = mod.inventory  ?? {};
        const mfst = mod.manifest   ?? {};
        const cls  = inv.classification ?? "unknown";
        if (state.classification !== "all" && cls !== state.classification) return false;
        if (!query) return true;
        return (
          (mod.module ?? "").toLowerCase().includes(query) ||
          String(mfst["summary"] ?? "").toLowerCase().includes(query) ||
          String(mfst["author"]  ?? "").toLowerCase().includes(query) ||
          (inv.submodule ?? "").toLowerCase().includes(query)
        );
      });

      const sorted = [...filtered].sort((a, b) => {
        const key = state.sortKey;
        let av: unknown, bv: unknown;
        if (key === "_locTotal") { av = a._locTotal ?? 0; bv = b._locTotal ?? 0; }
        else if (key === "module")         { av = a.module ?? "";           bv = b.module ?? ""; }
        else if (key === "classification") { av = a.inventory?.classification ?? ""; bv = b.inventory?.classification ?? ""; }
        else if (key === "version")        { av = a.inventory?.version ?? "";  bv = b.inventory?.version ?? ""; }
        else { av = ""; bv = ""; }
        if (typeof av === "number" && typeof bv === "number")
          return state.sortDir === "asc" ? av - bv : bv - av;
        return state.sortDir === "asc"
          ? String(av).localeCompare(String(bv))
          : String(bv).localeCompare(String(av));
      });

      (emptyState as HTMLElement).style.display = sorted.length === 0 ? "" : "none";

      for (const mod of sorted) {
        const inv     = (mod.inventory  ?? {}) as InventoryNode;
        const mfst    = mod.manifest   ?? {};
        const name    = mod.module     ?? "—";
        const cls     = inv.classification ?? "unknown";
        const loc     = (inv.loc ?? {}) as Partial<Loc>;
        const locTot  = mod._locTotal ?? 0;

        const bar = el("div", { class: "loc-bar" });
        for (const [k, color] of Object.entries(LCOLORS)) {
          const v = (loc as Record<string, number>)[k] ?? 0;
          if (!locTot || !v) continue;
          const seg = el("div", {
            class: "loc-bar-segment",
            title: `${k}: ${fmt(v)} (${((v / locTot) * 100).toFixed(1)}%)`,
          });
          (seg as HTMLElement).style.width = `${(v / locTot) * 100}%`;
          (seg as HTMLElement).style.background = color;
          bar.append(seg);
        }

        const nameCell = el("td", {}, [
          el("div", { class: "addon-name" }, el("a", { href: "#/module/" + encodeURIComponent(name) }, name)),
          mfst["summary"] ? el("div", { class: "addon-summary" }, String(mfst["summary"])) : null,
        ]);
        tbody.append(el("tr", {}, [nameCell, el("td", {}, badge(cls)), el("td", { class: "muted" }, inv.version ?? "—"), numCell(locTot || null), el("td", {}, bar)]));
      }

      for (const th of thead.querySelectorAll<HTMLElement>("th[data-sort]")) {
        th.classList.remove("sorted-asc", "sorted-desc");
        if (th.dataset["sort"] === state.sortKey) th.classList.add(state.sortDir === "asc" ? "sorted-asc" : "sorted-desc");
      }
    }

    searchInput.addEventListener("input", () => { state.search = searchInput.value; renderTable(); });
    renderTable();
    return wrap;
  }

  // ---------------------------------------------------------------------------
  // Module view (#/module/:name)
  // ---------------------------------------------------------------------------

  function _viewModule(name: string): HTMLElement {
    const mod = modules.find((m) => m.module === name);
    if (!mod) return el("p", { class: "placeholder" }, "Module not found: " + name);

    const wrap = el("div", {});
    const inv  = mod.inventory ?? {};
    const mfst = mod.manifest  ?? {};

    const titleRow = el("div", { class: "page-title-row" });
    titleRow.append(el("h1", {}, name));
    if (inv.classification) titleRow.append(badge(inv.classification));

    const meta: string[] = [];
    if (inv.version)   meta.push("v" + inv.version);
    if (inv.submodule) meta.push("submodule: " + inv.submodule);
    if (inv.branch)    meta.push("branch: " + inv.branch);

    wrap.append(el("div", { class: "page-header" }, [
      titleRow,
      meta.length ? el("p", { class: "page-subtitle" }, meta.join(" · ")) : null,
    ]));

    const card = el("div", { class: "module-card" });

    const mfstEntries = Object.entries(mfst).filter(([, v]) => v != null && v !== "");
    if (mfstEntries.length) {
      card.append(el("h4", {}, "Manifest"));
      card.append(manifestGrid(mfst as Record<string, unknown>));
    }

    if (mod.readme?.present && mod.readme.content) {
      card.append(el("h4", {}, "README"));
      card.append(el("pre", { style: "white-space:pre-wrap;max-height:300px;overflow-y:auto" }, mod.readme.content));
    }

    if (mod.depends?.length) {
      card.append(el("h4", {}, `Depends (${mod.depends.length})`));
      card.append(el("div", { class: "chip-list" }, mod.depends.map((d) => el("span", { class: "chip" }, d))));
    }

    const mEntries = Object.entries(mod.metrics ?? {}).filter(([, v]) => v != null);
    if (mEntries.length) {
      card.append(el("h4", {}, "Metrics"));
      const grid = el("div", { class: "metrics-grid" });
      mEntries.forEach(([key, value]) => {
        const zero = !value;
        grid.append(el("div", { class: "metric" + (zero ? " zero" : "") }, [
          el("div", { class: "metric-value" }, String(value)),
          el("div", { class: "metric-label" }, key.replace(/_/g, " ")),
        ]));
      });
      card.append(grid);
    }

    const structSect = renderStructure(inv.loc ? mod.structure : undefined);
    if (structSect) card.append(structSect);

    wrap.append(card);

    // Models contributed by this module
    const modelEntries = Object.entries(modelsByBare).filter(([, entry]) =>
      entry.contributions.some((c) => c.module === name)
    );
    if (modelEntries.length) {
      wrap.append(el("h2", {}, `Models (${modelEntries.length})`));
      const rows = modelEntries.map(([bare, entry]) => {
        const contrib = entry.contributions.find((c) => c.module === name) ?? {};
        const node    = (contrib as Record<string, unknown>)["model_node"] as Record<string, unknown> ?? {};
        return el("tr", {}, [
          el("td", { class: "mono" }, el("a", { href: "#/model/" + encodeURIComponent(bare) }, bare)),
          el("td", { class: "muted" }, String(node["status"] ?? "—")),
          numCell(((contrib as Record<string, unknown>)["fields"] as unknown[] | undefined)?.length ?? 0),
          numCell(((contrib as Record<string, unknown>)["methods"] as unknown[] | undefined)?.length ?? 0),
        ]);
      });
      const thead = el("thead", {}, [el("tr", {}, [
        el("th", {}, "Model"), el("th", {}, "Status"),
        el("th", { class: "num" }, "Fields"), el("th", { class: "num" }, "Methods"),
      ])]);
      wrap.append(tableWrap(el("table", {}, [thead, el("tbody", {}, rows)])));
    }

    return wrap;
  }

  // ---------------------------------------------------------------------------
  // Model view (#/model/:bare)
  // ---------------------------------------------------------------------------

  function _viewModel(bare: string): HTMLElement {
    const entry = modelsByBare[bare];
    if (!entry) return el("p", { class: "placeholder" }, "Model not found: " + bare);

    const contributions = entry.contributions ?? [];
    const wrap = el("div", {});

    wrap.append(el("div", { class: "page-header" }, [
      el("h1", {}, bare),
      entry.description
        ? el("p", { class: "page-subtitle" },
            entry.description + (entry.description_inherited_from ? ` (inherited from ${entry.description_inherited_from})` : ""))
        : null,
    ]));

    wrap.append(provenanceTable(entry, modules));

    // Metrics summary
    const allFields  = contributions.flatMap((c) => (c.fields  ?? []).map((f) => ({ ...f, _module: c.module })));
    const allMethods = contributions.flatMap((c) => (c.methods ?? []).map((m) => ({ ...m, _module: c.module })));

    const mkCard = (value: number, label: string, cls: string) =>
      el("div", { class: `fb-card ${cls}` }, [
        el("div", { class: "fb-value" }, value),
        el("div", { class: "fb-label" }, label),
      ]);

    const fTotal = allFields.length;
    const fAdded = allFields.filter((f) => f.origin_status === "new" || f.origin_status === "base").length;
    const fInher = allFields.filter((f) => f.origin_status === "extended").length;
    const mTotal = allMethods.length;
    const mAdded = allMethods.filter((m) => methodKind(m) === "added").length;
    const mInher = allMethods.filter((m) => methodKind(m) === "inherited").length;
    const mOver  = allMethods.filter((m) => methodKind(m) === "override").length;

    const metricsGrid = el("div", { class: "model-metrics" });
    if (fTotal) metricsGrid.append(el("div", { class: "mm-row" }, [
      el("span", { class: "mm-label" }, "Fields"),
      mkCard(fTotal, "Total", "total"), mkCard(fAdded, "Added", "own"), mkCard(fInher, "Inherited", "extended"),
    ]));
    if (mTotal) metricsGrid.append(el("div", { class: "mm-row" }, [
      el("span", { class: "mm-label" }, "Methods"),
      mkCard(mTotal, "Total", "total"), mkCard(mAdded, "Added", "own"),
      mkCard(mInher, "Inherited", "extended"), mkCard(mOver, "Overridden", "override"),
    ]));
    wrap.append(metricsGrid);

    // Page-level module filter
    const allModuleNames = [...new Set(contributions.map((c) => c.module))];
    const pageFilterRow  = el("div", { class: "filters", style: "margin-bottom:1rem" });
    const modSelect      = el("select", { class: "filter-select" }) as HTMLSelectElement;
    modSelect.append(el("option", { value: "" }, "All modules"));
    allModuleNames.forEach((m) => modSelect.append(el("option", { value: m }, m)));
    pageFilterRow.append(
      el("label", { style: "display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;color:var(--text-muted)" },
        ["Filter by module ", modSelect])
    );
    wrap.append(pageFilterRow);

    // Fields section
    if (allFields.length) {
      const ft = fieldsTable(allFields, schema as Schema | undefined);
      wrap.append(ft.h2);
      wrap.append(el("h4", {}, "By type"));
      wrap.append(ft.chipsContainer);
      wrap.append(ft.element);
      modSelect.addEventListener("change", () => ft.filterBy({ module: modSelect.value }));
    }

    // Methods section
    if (allMethods.length) {
      const mt = methodsTable(allMethods);
      wrap.append(mt.h2);
      wrap.append(mt.chipsContainer);
      wrap.append(mt.element);
      modSelect.addEventListener("change", () => mt.filterBy({ module: modSelect.value }));
    }

    return wrap;
  }

  // ---------------------------------------------------------------------------
  // Search view (#/search)
  // ---------------------------------------------------------------------------

  function _viewSearch(): HTMLElement {
    const wrap = el("div", {});
    wrap.append(el("div", { class: "page-header" }, [el("h1", {}, "Search")]));

    const input = el("input", {
      type: "search", class: "search-input",
      placeholder: "Type to search modules, models, fields, methods…",
      autocomplete: "off", style: "width:100%;margin-bottom:1.5rem",
    }) as HTMLInputElement;
    wrap.append(input);

    const resultsEl = el("div", {});
    wrap.append(resultsEl);

    function renderResults(query: string) {
      resultsEl.innerHTML = "";
      if (!query || query.length < 2) {
        resultsEl.append(el("p", { class: "placeholder" }, "Enter at least 2 characters."));
        return;
      }

      const hits = getIndex().search(query, { limit: 60 });
      if (!hits.length) {
        resultsEl.append(el("p", { class: "placeholder" }, `No results for "${query}".`));
        return;
      }

      const groups: Record<string, SearchEntry[]> = { module: [], model: [], field: [], method: [] };
      for (const h of hits) groups[h.item.kind]?.push(h.item);

      const kindLabels: Record<string, string> = {
        module: "Modules", model: "Models", field: "Fields", method: "Methods",
      };
      for (const [kind, items] of Object.entries(groups)) {
        if (!items.length) continue;
        resultsEl.append(el("h2", {}, kindLabels[kind] ?? kind));
        const list = el("div", {});
        for (const item of items) {
          const row = el("div", { class: "search-result-item" });
          row.append(el("a", { href: item.hash }, item.label));
          if (item.model && item.kind !== "model")
            row.append(el("span", { class: "search-result-meta" }, "in " + item.model));
          if (item.section)
            row.append(el("span", { class: `ft-chip`, style: "margin:0" }, item.section));
          row.append(el("span", { style: "margin-left:auto" }, badge(modClassification(item.module))));
          list.append(row);
        }
        resultsEl.append(list);
      }

      const total = hits.length;
      resultsEl.append(el("p", { style: "color:var(--text-muted);font-size:0.8rem;margin-top:1rem" },
        total + " result" + (total !== 1 ? "s" : "") + (total === 60 ? " (capped at 60)" : "")
      ));
    }

    input.addEventListener("input", () => renderResults(input.value));
    const qs       = location.hash.split("?")[1] ?? "";
    const initialQ = new URLSearchParams(qs).get("q") ?? "";
    if (initialQ) { input.value = initialQ; renderResults(initialQ); }
    setTimeout(() => input.focus(), 0);
    return wrap;
  }
}
