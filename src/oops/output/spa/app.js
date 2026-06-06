// oops SPA — project docs viewer
// window.OOPS is set by data.js before this script runs.

// ----- DOM helpers -----
const el = (tag, attrs, children) => {
  attrs = attrs || {};
  children = children != null ? children : [];
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v != null) node.setAttribute(k, String(v));
  }
  for (const child of [].concat(children)) {
    if (child == null) continue;
    node.append(child instanceof Node ? child : String(child));
  }
  return node;
};

const fmt = (n) => (typeof n === "number" ? n.toLocaleString() : n);
const humanize = (k) => k.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
const bareModel = (s) => { if (!s) return "—"; const i = s.indexOf(":"); return i === -1 ? s : s.slice(i + 1); };

// Classification badge — muted soft style (list report pattern)
const badge = (cls) => {
  const c = cls || "unknown";
  return el("span", { class: `badge badge-${c}` }, c);
};

// Origin badge — filled style (analyze report pattern)
const originBadge = (origin) =>
  el("span", { class: `badge ${origin || "unknown"}` }, (origin || "—").replace(/_/g, " "));

const numCell = (n) =>
  el("td", { class: ("num " + (n ? "" : "zero")).trim() }, n != null ? fmt(n) : "0");

// Table wrapper
const tableWrap = (table) => {
  const wrap = el("div", { class: "table-wrap" });
  wrap.appendChild(table);
  return wrap;
};

// ----- renderRef: DocModel ref → DOM node -----
function renderRef(ref) {
  if (!ref) return el("span", { style: "color:var(--text-muted)" }, "—");
  if (ref.kind === "link") {
    const hash = mdPathToHash(ref.path);
    const anchor = ref.anchor ? "#" + ref.anchor : "";
    const name = ref.path.replace(/^.*\//, "").replace(/\.md$/, "");
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

function mdPathToHash(path) {
  if (!path) return "#/";
  if (path.startsWith("models/"))  return "#/model/"  + path.slice(7).replace(/\.md$/, "");
  if (path.startsWith("methods/")) return "#/method/" + path.slice(8).replace(/\.md$/, "");
  if (path.startsWith("modules/")) return "#/module/" + path.slice(8).replace(/\.md$/, "");
  return "#/";
}

// ----- Schema descriptor helpers -----
function descriptorTitle(group, key) {
  const schema = window.OOPS.schema || {};
  return (((schema.definitions || {})[group] || {}).properties || {})[key]?.title || humanize(key);
}

function descriptorKind(group, key) {
  const schema = window.OOPS.schema || {};
  return (((schema.definitions || {})[group] || {}).properties || {})[key]?.["x-kind"] || "count";
}

function formatValue(value, kind) {
  if (value == null) return "—";
  if (kind === "boolean") return value ? "✓" : "✗";
  if (kind === "percent") return Number(value).toFixed(1) + "%";
  if (kind === "bytes") {
    if (value < 1024) return value + " B";
    if (value < 1024 * 1024) return (value / 1024).toFixed(1) + " KB";
    return (value / (1024 * 1024)).toFixed(1) + " MB";
  }
  return typeof value === "number" ? fmt(value) : String(value);
}

// ----- Method section -----
const SECTION_ORDER = ["COMPUTE", "SELECTION", "DEFAULT", "ONCHANGE", "CONSTRAINT",
  "CRUD", "HELPER", "ACTION", "BUSINESS", "OTHER"];

const SECTION_CLASS = {
  COMPUTE: "compute", SELECTION: "other", DEFAULT: "other",
  ONCHANGE: "onchange", CONSTRAINT: "constrain", CRUD: "crud",
  ACTION: "action", HELPER: "helper", BUSINESS: "business", OTHER: "other",
};

// ----- Router -----
const ROUTES = [
  { re: /^#\/module\/(.+)$/, view: (m) => viewModule(decodeURIComponent(m[1])) },
  { re: /^#\/model\/(.+)$/,  view: (m) => viewModel(decodeURIComponent(m[1])) },
  { re: /^#\/method\/(.+)$/, view: (m) => viewMethodPlaceholder(decodeURIComponent(m[1])) },
  { re: /^#\/search$/,       view: () => viewSearch() },
  { re: /^(#\/?)?$/,         view: () => viewIndex() },
];

function route() {
  const hash = location.hash || "#/";
  const app = document.getElementById("app");
  if (_drawer) { _drawer.close(); }
  for (const r of ROUTES) {
    const m = hash.match(r.re);
    if (m) { app.innerHTML = ""; app.appendChild(r.view(m)); return; }
  }
  app.innerHTML = "";
  app.appendChild(el("p", { class: "placeholder" }, "Page not found: " + hash));
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", route);

// ----- Metadata bar -----
function renderMetadataBar(meta) {
  if (!meta) return null;
  const formatTs = (iso) => {
    if (!iso) return null;
    try { return new Date(iso).toLocaleString(); } catch (e) { return iso; }
  };
  const item = (label, value, cls) => {
    if (value == null || value === "") return null;
    return el("div", { class: "meta-item" }, [
      el("span", { class: "label" }, label),
      el("span", { class: cls ? `value ${cls}` : "value" }, String(value)),
    ]);
  };
  const items = [
    item("Project", meta.project_name),
    item("Odoo", meta.odoo_version),
    item("Branch", meta.git_branch),
    item("Commit", meta.git_commit ? meta.git_commit.slice(0, 10) : null, "commit"),
    item("Generated", formatTs(meta.generated_at)),
    item("Tool", meta.tool_version),
  ].filter(Boolean);
  if (!items.length) return null;
  return el("div", { class: "metadata-bar" }, items);
}

// ----- Index view (#/) -----
function viewIndex() {
  const data = window.OOPS;
  const modules = data.modules || [];
  const wrap = el("div", {});

  const cs = getComputedStyle(document.documentElement);
  const CCOLORS = {
    oca: cs.getPropertyValue("--oca").trim(),
    custom: cs.getPropertyValue("--custom").trim(),
    "third-party": cs.getPropertyValue("--third-party").trim(),
  };
  const LCOLORS = {
    python: cs.getPropertyValue("--loc-python").trim(),
    xml: cs.getPropertyValue("--loc-xml").trim(),
    javascript: cs.getPropertyValue("--loc-javascript").trim(),
    docs: cs.getPropertyValue("--loc-docs").trim(),
  };

  // Pre-compute per-module totals
  let totalLoc = 0;
  const byClass = {};
  const locTotals = { python: 0, xml: 0, javascript: 0, docs: 0 };
  for (const mod of modules) {
    const inv = mod.inventory || {};
    const cls = inv.classification || "unknown";
    byClass[cls] = (byClass[cls] || 0) + 1;
    const loc = inv.loc || {};
    const lt = (loc.python || 0) + (loc.xml || 0) + (loc.javascript || 0) + (loc.docs || 0);
    mod._locTotal = lt;
    totalLoc += loc.total || lt;
    for (const k of Object.keys(LCOLORS)) locTotals[k] += loc[k] || 0;
  }

  // Metadata bar
  const metaBar = renderMetadataBar(data.metadata);
  if (metaBar) wrap.appendChild(metaBar);

  // Page header
  wrap.appendChild(el("div", { class: "page-header" }, [
    el("h1", {}, "Project Addons"),
    el("p", { class: "page-subtitle" }, `${modules.length} addons · ${fmt(totalLoc)} total LoC`),
  ]));

  // Charts row — containers built now, D3 renders after DOM insertion
  const donutContainer = el("div", { class: "chart-container" });
  const donutLegend = el("div", { class: "legend" });
  const locContainer = el("div", { class: "chart-container" });
  const locLegend = el("div", { class: "legend" });
  wrap.appendChild(el("div", { class: "charts-row" }, [
    el("div", { class: "chart-card" }, [
      el("h3", {}, "By classification"),
      donutContainer,
      donutLegend,
    ]),
    el("div", { class: "chart-card" }, [
      el("h3", {}, "Lines of code by type"),
      locContainer,
      locLegend,
    ]),
  ]));

  setTimeout(() => {
    // Classification donut
    const cData = Object.entries(byClass)
      .map(([key, value]) => ({ key, value }))
      .sort((a, b) => b.value - a.value);
    if (cData.length) {
      const w = 220, h = 220, r = Math.min(w, h) / 2;
      const svg = d3.select(donutContainer).append("svg")
        .attr("viewBox", `${-w / 2} ${-h / 2} ${w} ${h}`)
        .attr("width", w).attr("height", h);
      const pie = d3.pie().value((d) => d.value).sort(null);
      const arc = d3.arc().innerRadius(r * 0.55).outerRadius(r - 5);
      svg.selectAll("path").data(pie(cData)).join("path")
        .attr("d", arc)
        .attr("fill", (d) => CCOLORS[d.data.key] || "#999")
        .attr("stroke", "white").attr("stroke-width", 2);
      svg.append("text").attr("text-anchor", "middle").attr("dy", "-0.2em")
        .style("font-size", "1.4rem").style("font-weight", "600")
        .style("font-family", "var(--mono)").text(modules.length);
      svg.append("text").attr("text-anchor", "middle").attr("dy", "1.2em")
        .style("font-size", ".7rem").style("fill", "var(--text-muted)")
        .style("text-transform", "uppercase").style("letter-spacing", ".05em").text("addons");
      cData.forEach((d) => {
        const li = d3.select(donutLegend).append("div").attr("class", "legend-item");
        li.append("span").attr("class", "legend-swatch").style("background", CCOLORS[d.key] || "#999");
        li.append("span").text(`${d.key} (${d.value})`);
      });
    }

    // LoC bar chart
    const lData = Object.entries(locTotals).filter(([, v]) => v > 0).map(([key, value]) => ({ key, value }));
    if (lData.length) {
      const w = 300, h = 220;
      const m = { top: 10, right: 10, bottom: 28, left: 52 };
      const iW = w - m.left - m.right, iH = h - m.top - m.bottom;
      const svg = d3.select(locContainer).append("svg")
        .attr("viewBox", `0 0 ${w} ${h}`).attr("width", w).attr("height", h);
      const g = svg.append("g").attr("transform", `translate(${m.left},${m.top})`);
      const x = d3.scaleBand().domain(lData.map((d) => d.key)).range([0, iW]).padding(0.3);
      const y = d3.scaleLinear().domain([0, d3.max(lData, (d) => d.value)]).nice().range([iH, 0]);
      g.selectAll("rect").data(lData).join("rect")
        .attr("x", (d) => x(d.key)).attr("y", (d) => y(d.value))
        .attr("width", x.bandwidth()).attr("height", (d) => iH - y(d.value))
        .attr("fill", (d) => LCOLORS[d.key] || "#999").attr("rx", 2);
      g.selectAll("text.bar-label").data(lData).join("text")
        .attr("class", "bar-label")
        .attr("x", (d) => x(d.key) + x.bandwidth() / 2).attr("y", (d) => y(d.value) - 4)
        .attr("text-anchor", "middle")
        .style("font-size", ".7rem").style("font-family", "var(--mono)")
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
        li.append("span").attr("class", "legend-swatch").style("background", LCOLORS[d.key]);
        li.append("span").text(`${d.key} (${fmt(d.value)})`);
      });
    }
  }, 0);

  // Filter + search
  const state = { sortKey: "_locTotal", sortDir: "desc", classification: "all", search: "" };

  wrap.appendChild(el("h2", {}, "All addons"));

  const filtersEl = el("div", { class: "filters" });
  const searchInput = el("input", {
    type: "search",
    class: "search-input",
    placeholder: "Search addons…",
    autocomplete: "off",
  });
  filtersEl.appendChild(searchInput);

  const pillDefs = [
    { label: "All", cls: "all" },
    { label: "OCA", cls: "oca" },
    { label: "Custom", cls: "custom" },
    { label: "Third-party", cls: "third-party" },
  ];
  const pillBtns = pillDefs.map(({ label, cls }) => {
    const count = cls === "all" ? modules.length : (byClass[cls] || 0);
    const btn = el("button", { class: "filter-btn" + (cls === "all" ? " active" : ""), "data-cls": cls }, [
      label, el("span", { class: "filter-count" }, count),
    ]);
    btn.addEventListener("click", () => {
      pillBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.classification = cls;
      renderTable();
    });
    filtersEl.appendChild(btn);
    return btn;
  });
  wrap.appendChild(filtersEl);

  // Sortable table
  const thead = el("thead", {}, [
    el("tr", {}, [
      el("th", { class: "sortable", "data-sort": "module" }, "Addon"),
      el("th", { class: "sortable", "data-sort": "classification" }, "Type"),
      el("th", { class: "sortable", "data-sort": "version" }, "Version"),
      el("th", { class: "num sortable", "data-sort": "_locTotal" }, "LoC"),
      el("th", {}, "Breakdown"),
    ]),
  ]);
  for (const th of thead.querySelectorAll("th[data-sort]")) {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) {
        state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
      } else {
        state.sortKey = key;
        state.sortDir = "desc";
      }
      renderTable();
    });
  }

  const tbody = el("tbody", {});
  const emptyState = el("div", { class: "empty-state" }, "No addons match.");
  emptyState.style.display = "none";
  wrap.appendChild(tableWrap(el("table", {}, [thead, tbody])));
  wrap.appendChild(emptyState);

  function renderTable() {
    tbody.innerHTML = "";
    const query = state.search.toLowerCase();
    const filtered = modules.filter((mod) => {
      const inv = mod.inventory || {};
      const man = mod.manifest || {};
      const cls = inv.classification || "unknown";
      if (state.classification !== "all" && cls !== state.classification) return false;
      if (!query) return true;
      return (
        (mod.module || "").toLowerCase().includes(query) ||
        (man.summary || "").toLowerCase().includes(query) ||
        (man.author || "").toLowerCase().includes(query) ||
        (inv.submodule || "").toLowerCase().includes(query)
      );
    });

    const sorted = [...filtered].sort((a, b) => {
      let av, bv;
      if (state.sortKey === "_locTotal") { av = a._locTotal || 0; bv = b._locTotal || 0; }
      else if (state.sortKey === "module") { av = a.module || ""; bv = b.module || ""; }
      else if (state.sortKey === "classification") {
        av = (a.inventory || {}).classification || ""; bv = (b.inventory || {}).classification || "";
      } else if (state.sortKey === "version") {
        av = (a.inventory || {}).version || ""; bv = (b.inventory || {}).version || "";
      } else { av = ""; bv = ""; }
      if (typeof av === "number" && typeof bv === "number")
        return state.sortDir === "asc" ? av - bv : bv - av;
      return state.sortDir === "asc"
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });

    emptyState.style.display = sorted.length === 0 ? "" : "none";

    for (const mod of sorted) {
      const inv = mod.inventory || {};
      const man = mod.manifest || {};
      const name = mod.module || "—";
      const cls = inv.classification || "unknown";
      const loc = inv.loc || {};

      const bar = el("div", { class: "loc-bar" });
      for (const [k, color] of Object.entries(LCOLORS)) {
        const v = loc[k] || 0;
        if (!mod._locTotal || !v) continue;
        const seg = el("div", {
          class: "loc-bar-segment",
          title: `${k}: ${fmt(v)} (${((v / mod._locTotal) * 100).toFixed(1)}%)`,
        });
        seg.style.width = `${(v / mod._locTotal) * 100}%`;
        seg.style.background = color;
        bar.appendChild(seg);
      }

      const nameCell = el("td", {}, [
        el("div", { class: "addon-name" },
          el("a", { href: "#/module/" + encodeURIComponent(name) }, name)),
        man.summary ? el("div", { class: "addon-summary" }, man.summary) : null,
      ]);
      tbody.appendChild(el("tr", {}, [
        nameCell,
        el("td", {}, badge(cls)),
        el("td", { class: "muted" }, inv.version || "—"),
        numCell(mod._locTotal),
        el("td", {}, bar),
      ]));
    }

    for (const th of thead.querySelectorAll("th[data-sort]")) {
      th.classList.remove("sorted-asc", "sorted-desc");
      if (th.dataset.sort === state.sortKey)
        th.classList.add(state.sortDir === "asc" ? "sorted-asc" : "sorted-desc");
    }
  }

  searchInput.addEventListener("input", (e) => { state.search = e.target.value; renderTable(); });
  renderTable();
  return wrap;
}

// ----- Structure grid -----
function renderStructure(structure) {
  if (!structure) return null;
  const grid = el("div", { class: "structure-grid" });

  if (structure.data && Object.keys(structure.data).length) {
    Object.entries(structure.data).forEach(([folder, exts]) => {
      const card = el("div", { class: "structure-card" }, [el("div", { class: "sc-title" }, folder)]);
      Object.entries(exts).forEach(([ext, count]) => {
        card.appendChild(el("div", { class: "sc-line" }, [
          el("span", {}, "." + ext),
          el("span", { class: "v" }, count),
        ]));
      });
      grid.appendChild(card);
    });
  }

  const pyCounters = [
    ["controllers_py", "Controllers (py)"],
    ["wizard_py", "Wizards (py)"],
    ["report_py", "Reports (py)"],
  ].filter(([k]) => structure[k]);
  if (pyCounters.length) {
    const card = el("div", { class: "structure-card" }, [el("div", { class: "sc-title" }, "Python")]);
    pyCounters.forEach(([k, label]) => {
      card.appendChild(el("div", { class: "sc-line" }, [
        el("span", {}, label),
        el("span", { class: "v" }, structure[k]),
      ]));
    });
    grid.appendChild(card);
  }

  if (structure.static_by_ext && Object.keys(structure.static_by_ext).length) {
    const card = el("div", { class: "structure-card" }, [el("div", { class: "sc-title" }, "Static assets")]);
    Object.entries(structure.static_by_ext).forEach(([ext, count]) => {
      card.appendChild(el("div", { class: "sc-line" }, [
        el("span", {}, "." + ext),
        el("span", { class: "v" }, count),
      ]));
    });
    grid.appendChild(card);
  }

  if (!grid.childElementCount) return null;
  const section = el("div", {});
  section.appendChild(el("h4", {}, "Structure"));
  section.appendChild(grid);
  return section;
}

// ----- Module page (#/module/:name) -----
function viewModule(name) {
  const data = window.OOPS;
  const mod = (data.modules || []).find((m) => m.module === name);
  if (!mod) return el("p", { class: "placeholder" }, "Module not found: " + name);

  const wrap = el("div", {});
  const inv = mod.inventory || {};
  const man = mod.manifest || {};

  // Page header
  const titleRow = el("div", { class: "page-title-row" });
  titleRow.appendChild(el("h1", {}, name));
  if (inv.classification) titleRow.appendChild(badge(inv.classification));

  const meta = [];
  if (inv.version)   meta.push("v" + inv.version);
  if (inv.submodule) meta.push("submodule: " + inv.submodule);
  if (inv.branch)    meta.push("branch: " + inv.branch);

  wrap.appendChild(el("div", { class: "page-header" }, [
    titleRow,
    meta.length ? el("p", { class: "page-subtitle" }, meta.join(" · ")) : null,
  ]));

  const card = el("div", { class: "module-card" });

  // Manifest fields
  const manifestEntries = Object.entries(man).filter(([k, v]) => v != null && v !== "");
  if (manifestEntries.length) {
    card.appendChild(el("h4", {}, "Manifest"));
    const grid = el("div", { class: "manifest-grid" });
    manifestEntries.forEach(([key, value]) => {
      const display = typeof value === "boolean" ? (value ? "yes" : "no") : String(value);
      grid.appendChild(el("div", { class: "manifest-item" }, [
        el("span", { class: "manifest-label" }, descriptorTitle("manifest", key)),
        el("span", { class: "manifest-value" }, display),
      ]));
    });
    card.appendChild(grid);
  }

  // README
  const readme = mod.readme || {};
  if (readme.present && readme.content) {
    card.appendChild(el("h4", {}, "README"));
    card.appendChild(el("pre", { style: "white-space:pre-wrap;max-height:300px;overflow-y:auto" }, readme.content));
  }

  // Depends
  if (mod.depends && mod.depends.length) {
    card.appendChild(el("h4", {}, `Depends (${mod.depends.length})`));
    card.appendChild(el("div", { class: "chip-list" },
      mod.depends.map((d) => el("span", { class: "chip" }, d))
    ));
  }

  // Metrics
  const metricsEntries = Object.entries(mod.metrics || {}).filter(([, v]) => v != null);
  if (metricsEntries.length) {
    card.appendChild(el("h4", {}, "Metrics"));
    const grid = el("div", { class: "metrics-grid" });
    metricsEntries.forEach(([key, value]) => {
      const kind = descriptorKind("metrics", key);
      const zero = !value;
      grid.appendChild(el("div", { class: "metric" + (zero ? " zero" : "") }, [
        el("div", { class: "metric-value" }, formatValue(value, kind)),
        el("div", { class: "metric-label" }, descriptorTitle("metrics", key)),
      ]));
    });
    card.appendChild(grid);
  }

  // LoC
  const locEntries = Object.entries(mod.loc || {}).filter(([, v]) => v != null);
  if (locEntries.length) {
    card.appendChild(el("h4", {}, "Lines of code"));
    const grid = el("div", { class: "metrics-grid" });
    locEntries.forEach(([key, value]) => {
      const kind = descriptorKind("loc", key);
      const zero = !value;
      grid.appendChild(el("div", { class: "metric" + (zero ? " zero" : "") }, [
        el("div", { class: "metric-value" }, formatValue(value, kind)),
        el("div", { class: "metric-label" }, descriptorTitle("loc", key)),
      ]));
    });
    card.appendChild(grid);
  }

  // Structure
  const structureSection = renderStructure(mod.structure);
  if (structureSection) card.appendChild(structureSection);

  // Not analysed
  if (mod.not_analysed && mod.not_analysed.length) {
    card.appendChild(el("h4", {}, "Not analysed"));
    card.appendChild(el("div", { class: "chip-list" },
      mod.not_analysed.map((p) => el("span", { class: "chip" }, p))
    ));
  }

  wrap.appendChild(card);

  // Models contributed by this module
  const modelEntries = Object.entries(data.models_by_bare || {})
    .filter(([, entry]) =>
      (entry.contributions || []).some((c) => c.module === name)
    );

  if (modelEntries.length) {
    wrap.appendChild(el("h2", {}, `Models (${modelEntries.length})`));
    const thead = el("thead", {}, [
      el("tr", {}, [
        el("th", {}, "Model"),
        el("th", {}, "Status"),
        el("th", { class: "num" }, "Fields"),
        el("th", { class: "num" }, "Methods"),
      ]),
    ]);
    const rows = modelEntries.map(([bare, entry]) => {
      const contrib = (entry.contributions || []).find((c) => c.module === name) || {};
      const node = contrib.model_node || {};
      const tr = el("tr", { class: "clickable" }, [
        el("td", { class: "mono" }, el("a", { href: "#/model/" + encodeURIComponent(bare) }, bare)),
        el("td", { class: "muted" }, node.status || "—"),
        numCell((contrib.fields || []).length),
        numCell((contrib.methods || []).length),
      ]);
      return tr;
    });
    wrap.appendChild(tableWrap(el("table", {}, [thead, el("tbody", {}, rows)])));
  }

  return wrap;
}

// ----- Method kind helper (used across model page) -----
function methodKind(m) {
  if (m.is_override)  return "override";
  if (m.is_inherited) return "inherited";
  return "added";
}

// ----- Slide-in method drawer -----
let _drawer = null;

function ensureDrawer() {
  if (_drawer) return _drawer;

  const overlay  = el("div", { class: "drawer-overlay" });
  const panel    = el("div", { class: "drawer-panel" });
  const closeBtn = el("button", { class: "drawer-close", "aria-label": "Close" }, "✕");
  const body     = el("div", { class: "drawer-body" });

  panel.appendChild(closeBtn);
  panel.appendChild(body);
  document.body.appendChild(overlay);
  document.body.appendChild(panel);

  const close = () => {
    panel.classList.remove("drawer-open");
    overlay.classList.remove("drawer-overlay-visible");
  };
  closeBtn.addEventListener("click", close);
  overlay.addEventListener("click", close);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });

  _drawer = { panel, overlay, body, close };
  return _drawer;
}

function openMethodDrawer(m) {
  const { panel, overlay, body } = ensureDrawer();
  body.innerHTML = "";

  const kind = methodKind(m);
  const lineCount = (m.line_start != null && m.line_end != null)
    ? `lines ${m.line_start}–${m.line_end} (${m.line_end - m.line_start + 1} lines)` : null;
  const decorators = (m.decorators || []);
  const sig = [m.signature, ...decorators].filter(Boolean).join("\n");

  body.appendChild(el("div", { class: "drawer-method-name mono" }, m.name || "—"));
  body.appendChild(el("div", { class: "drawer-meta" }, [
    el("span", { class: `ft-chip ${SECTION_CLASS[m.section || "OTHER"] || "other"}` }, m.section || "OTHER"),
    el("span", { class: `kind-pill kind-${kind}` }, kind),
  ]));

  if (kind === "override" && m.overrides) {
    const ov = m.overrides;
    body.appendChild(el("div", { class: "drawer-row" }, [
      el("span", { class: "drawer-label" }, "Overrides"),
      el("span", {}, [(ov.origin_module || "—") + " ", ov.origin ? originBadge(ov.origin) : null]),
    ]));
  } else if (kind === "inherited" && m.inherited_from) {
    const ih = m.inherited_from;
    body.appendChild(el("div", { class: "drawer-row" }, [
      el("span", { class: "drawer-label" }, "Inherited from"),
      el("span", {}, [(ih.origin_module || "—") + " ", ih.origin ? originBadge(ih.origin) : null]),
    ]));
  }

  if (m.docstring) {
    body.appendChild(el("div", { class: "drawer-label" }, "Docstring"));
    body.appendChild(el("p", { class: "drawer-docstring" }, m.docstring));
  }

  if (sig) {
    body.appendChild(el("div", { class: "drawer-label" }, "Signature"));
    body.appendChild(el("pre", { class: "drawer-sig" }, sig));
  }

  if (m.source_file) {
    body.appendChild(el("div", { class: "drawer-label" }, "File"));
    body.appendChild(el("div", { class: "drawer-path mono" }, m.source_file));
  }
  if (lineCount) {
    body.appendChild(el("div", { class: "drawer-path" }, lineCount));
  }

  panel.classList.add("drawer-open");
  overlay.classList.add("drawer-overlay-visible");
}

// ----- Model page (#/model/:bare) -----
function viewModel(bare) {
  const data = window.OOPS;
  const entry = (data.models_by_bare || {})[bare];
  if (!entry) return el("p", { class: "placeholder" }, "Model not found: " + bare);

  const contributions = entry.contributions || [];
  const wrap = el("div", {});

  // Title
  wrap.appendChild(el("div", { class: "page-header" }, [
    el("h1", {}, bare),
    entry.description
      ? el("p", { class: "page-subtitle" },
          entry.description +
          (entry.description_inherited_from ? ` (inherited from ${entry.description_inherited_from})` : ""))
      : null,
  ]));

  // ----- Phase 1: Provenance + Extension Table -----
  const provSection = el("div", { class: "provenance-section" });
  provSection.appendChild(el("h2", {}, "Provenance"));

  const extThead = el("thead", {}, [el("tr", {}, [
    el("th", {}, "Module"),
    el("th", {}, "Status"),
    el("th", {}, "Origin"),
    el("th", {}, "Ancestor"),
    el("th", { class: "num", title: "Fields added (base/new)" }, "F+"),
    el("th", { class: "num", title: "Fields inherited (extended)" }, "F~"),
    el("th", { class: "num", title: "Methods added" }, "M+"),
    el("th", { class: "num", title: "Methods inherited" }, "M~"),
    el("th", { class: "num", title: "Methods overridden" }, "M↑"),
  ])]);
  const extRows = contributions.map((c) => {
    const node    = c.model_node || {};
    const fields  = c.fields  || [];
    const methods = c.methods || [];
    const fAdded  = fields.filter((f) => f.origin_status === "new" || f.origin_status === "base").length;
    const fInher  = fields.filter((f) => f.origin_status === "extended").length;
    const mAdded  = methods.filter((m) => methodKind(m) === "added").length;
    const mInher  = methods.filter((m) => methodKind(m) === "inherited").length;
    const mOver   = methods.filter((m) => methodKind(m) === "override").length;
    const cls     = (window.OOPS.modules || []).find((mod) => mod.module === c.module)?.inventory?.classification;
    const ownOrigin = cls === "third-party" ? "third_party" : (cls || null);
    return el("tr", {}, [
      el("td", { class: "mono" }, el("a", { href: "#/module/" + encodeURIComponent(c.module) }, c.module)),
      el("td", {}, node.status ? el("span", { class: "status-pill" }, node.status) : "—"),
      el("td", {}, ownOrigin ? originBadge(ownOrigin) : "—"),
      el("td", { class: "mono prov-ancestor" }, node.ancestor_module || "—"),
      numCell(fAdded), numCell(fInher),
      numCell(mAdded), numCell(mInher), numCell(mOver),
    ]);
  });
  provSection.appendChild(tableWrap(el("table", {}, [extThead, el("tbody", {}, extRows)])));
  wrap.appendChild(provSection);

  // ----- Unified metrics summary -----
  const fTotal    = contributions.reduce((n, c) => n + (c.fields  || []).length, 0);
  const fMetAdded = contributions.reduce((n, c) => n + (c.fields  || []).filter((f) => f.origin_status === "new" || f.origin_status === "base").length, 0);
  const fMetInher = contributions.reduce((n, c) => n + (c.fields  || []).filter((f) => f.origin_status === "extended").length, 0);
  const mTotal    = contributions.reduce((n, c) => n + (c.methods || []).length, 0);
  const mMetAdded = contributions.reduce((n, c) => n + (c.methods || []).filter((m) => methodKind(m) === "added").length, 0);
  const mMetInher = contributions.reduce((n, c) => n + (c.methods || []).filter((m) => methodKind(m) === "inherited").length, 0);
  const mMetOver  = contributions.reduce((n, c) => n + (c.methods || []).filter((m) => methodKind(m) === "override").length, 0);

  const mkCard = (value, label, cls) => el("div", { class: `fb-card ${cls}` }, [
    el("div", { class: "fb-value" }, value),
    el("div", { class: "fb-label" }, label),
  ]);

  const metricsGrid = el("div", { class: "model-metrics" });
  if (fTotal) {
    metricsGrid.appendChild(el("div", { class: "mm-row" }, [
      el("span", { class: "mm-label" }, "Fields"),
      mkCard(fTotal,    "Total",     "total"),
      mkCard(fMetAdded, "Added",     "own"),
      mkCard(fMetInher, "Inherited", "extended"),
    ]));
  }
  if (mTotal) {
    metricsGrid.appendChild(el("div", { class: "mm-row" }, [
      el("span", { class: "mm-label" }, "Methods"),
      mkCard(mTotal,    "Total",      "total"),
      mkCard(mMetAdded, "Added",      "own"),
      mkCard(mMetInher, "Inherited",  "extended"),
      mkCard(mMetOver,  "Overridden", "override"),
    ]));
  }
  wrap.appendChild(metricsGrid);

  // ----- Phase 3: Page-wide module selector -----
  const allModuleNames = [...new Set(contributions.map((c) => c.module))];
  const pageFilterRow = el("div", { class: "filters", style: "margin-bottom:1rem" });
  const modSelect = el("select", { class: "filter-select" });
  modSelect.appendChild(el("option", { value: "" }, "All modules"));
  allModuleNames.forEach((m) => modSelect.appendChild(el("option", { value: m }, m)));
  pageFilterRow.appendChild(
    el("label", { style: "display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;color:var(--text-muted)" },
      ["Filter by module ", modSelect])
  );
  wrap.appendChild(pageFilterRow);

  // ----- Fields -----
  const allFields = contributions.flatMap((c) =>
    (c.fields || []).map((f) => ({ ...f, _module: c.module }))
  );

  let fieldsTbody         = null;
  let typeSelect          = null;
  let fieldKindSelect     = null;
  let fieldsH2            = null;
  let typesChipsContainer = null;

  if (allFields.length) {
    fieldsH2 = el("h2", {}, `Fields (${allFields.length})`);
    wrap.appendChild(fieldsH2);

    // By type chips
    const byType = {};
    allFields.forEach((f) => { byType[f.type] = (byType[f.type] || 0) + 1; });
    wrap.appendChild(el("h4", {}, "By type"));
    typesChipsContainer = el("div", {});
    Object.entries(byType)
      .sort((a, b) => b[1] - a[1])
      .forEach(([t, n]) =>
        typesChipsContainer.appendChild(el("span", { class: "ft-chip" }, [t, el("span", { class: "count" }, n)]))
      );
    wrap.appendChild(typesChipsContainer);

    // Type filter (fields-only)
    const fieldFilterRow = el("div", { class: "filters", style: "margin-top:1rem" });
    const fieldTypes = [...new Set(allFields.map((f) => f.type || "").filter(Boolean))].sort();
    typeSelect = el("select", { class: "filter-select" });
    typeSelect.appendChild(el("option", { value: "" }, "All types"));
    fieldTypes.forEach((t) => typeSelect.appendChild(el("option", { value: t }, t)));
    fieldFilterRow.appendChild(
      el("label", { style: "display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;color:var(--text-muted)" },
        ["Type ", typeSelect])
    );
    fieldKindSelect = el("select", { class: "filter-select" });
    [["", "All kinds"], ["added", "Added"], ["inherited", "Inherited"]]
      .forEach(([v, l]) => fieldKindSelect.appendChild(el("option", { value: v }, l)));
    fieldFilterRow.appendChild(
      el("label", { style: "display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;color:var(--text-muted)" },
        ["Kind ", fieldKindSelect])
    );
    wrap.appendChild(fieldFilterRow);

    const fThead = el("thead", {}, [
      el("tr", {}, [
        el("th", {}, "Field"),
        el("th", {}, "Type"),
        el("th", {}, "Label"),
        el("th", {}, "Help"),
        el("th", {}, "Flags"),
        el("th", {}, "Module"),
        el("th", {}, "Status"),
      ]),
    ]);

    fieldsTbody = el("tbody", {});
    allFields
      .slice()
      .sort((a, b) => a.name.localeCompare(b.name))
      .forEach((f) => {
        const label = f.label || (f.label_inferred
          ? f.name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
          : "—");
        const helpText = f.help
          ? (f.help.length > 60 ? f.help.slice(0, 60) + "…" : f.help)
          : "—";
        const flags = [
          f.required && "req",
          f.readonly && "ro",
          f.store === false && "transient",
        ].filter(Boolean).join(" · ");

        let typeCell;
        if (f.comodel_ref) {
          typeCell = el("td", { class: "mono", style: "font-size:.76rem" }, [(f.type || "—") + " → ", renderRef(f.comodel_ref)]);
        } else {
          typeCell = el("td", { class: "mono", style: "font-size:.76rem" }, f.type || "—");
        }

        const statusCell = f.origin_status === "extended"
          ? el("td", {}, [
              el("span", { class: "status-pill extended" }, "extended"),
              f.overrides
                ? el("div", { class: "ovr" }, `→ ${f.overrides.origin_module} (${f.overrides.origin})`)
                : null,
            ])
          : el("td", {}, el("span", { class: "status-pill" }, f.origin_status || "—"));

        const fieldKind = f.origin_status === "extended" ? "inherited" : "added";
        const row = el("tr", { "data-module": f._module, "data-type": f.type || "", "data-kind": fieldKind }, [
          el("td", { class: "mono" }, f.name || "—"),
          typeCell,
          el("td", {}, label),
          el("td", { class: "cell-help" }, helpText),
          el("td", { class: "cell-flags" }, flags || "—"),
          el("td", { class: "mono", style: "font-size:.76rem" }, el("a", { href: "#/module/" + encodeURIComponent(f._module) }, f._module)),
          statusCell,
        ]);
        fieldsTbody.appendChild(row);
      });

    wrap.appendChild(tableWrap(el("table", {}, [fThead, fieldsTbody])));

    const applyFieldFilters = () => {
      const mod  = modSelect.value;
      const type = typeSelect.value;
      const kind = fieldKindSelect.value;
      for (const row of fieldsTbody.querySelectorAll("tr")) {
        const show = (!mod  || row.dataset.module === mod)
          && (!type || row.dataset.type === type)
          && (!kind || row.dataset.kind === kind);
        row.style.display = show ? "" : "none";
      }
    };
    typeSelect.addEventListener("change", applyFieldFilters);
    fieldKindSelect.addEventListener("change", applyFieldFilters);
  }

  // ----- Methods -----
  const allMethods = contributions.flatMap((c) =>
    (c.methods || []).map((m) => ({ ...m, _module: c.module }))
  );

  let methodsTbody         = null;
  let sectionSelect        = null;
  let kindSelect           = null;
  let methodsH2            = null;
  let sectionChipsContainer = null;

  if (allMethods.length) {
    methodsH2 = el("h2", {}, `Methods (${allMethods.length})`);
    wrap.appendChild(methodsH2);

    // Section summary chips
    const bySection = {};
    for (const m of allMethods) {
      const sec = m.section || "OTHER";
      (bySection[sec] = bySection[sec] || []).push(m);
    }
    sectionChipsContainer = el("div", { style: "margin-bottom:1rem" });
    Object.entries(bySection)
      .sort((a, b) => b[1].length - a[1].length)
      .forEach(([s, arr]) =>
        sectionChipsContainer.appendChild(el("span", { class: `ft-chip ${SECTION_CLASS[s] || "other"}` }, [
          s, el("span", { class: "count" }, arr.length),
        ]))
      );
    wrap.appendChild(sectionChipsContainer);

    // Phase 4: Section + kind selectors
    const methodFilterRow = el("div", { class: "filters", style: "margin-bottom:1rem" });

    sectionSelect = el("select", { class: "filter-select" });
    sectionSelect.appendChild(el("option", { value: "" }, "All sections"));
    const presentSections = SECTION_ORDER.filter((s) => bySection[s]?.length);
    for (const sec of presentSections) {
      sectionSelect.appendChild(el("option", { value: sec }, sec));
    }

    kindSelect = el("select", { class: "filter-select" });
    [["", "All kinds"], ["added", "Added"], ["inherited", "Inherited"], ["override", "Overridden"]]
      .forEach(([v, l]) => kindSelect.appendChild(el("option", { value: v }, l)));

    methodFilterRow.appendChild(
      el("label", { style: "display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;color:var(--text-muted)" },
        ["Section ", sectionSelect])
    );
    methodFilterRow.appendChild(
      el("label", { style: "display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;color:var(--text-muted)" },
        ["Kind ", kindSelect])
    );
    wrap.appendChild(methodFilterRow);

    // Phase 4: Unified methods table
    const mThead = el("thead", {}, [el("tr", {}, [
      el("th", {}, "Method"),
      el("th", {}, "Section"),
      el("th", {}, "Kind"),
      el("th", {}, "Module"),
      el("th", {}, "Origin / From"),
      el("th", { class: "num" }, "Lines"),
      el("th", {}, "Doc"),
    ])]);

    methodsTbody = el("tbody", {});

    allMethods
      .slice()
      .sort((a, b) => {
        const si = SECTION_ORDER.indexOf(a.section || "OTHER") - SECTION_ORDER.indexOf(b.section || "OTHER");
        return si !== 0 ? si : (a.name || "").localeCompare(b.name || "");
      })
      .forEach((m) => {
        const kind  = methodKind(m);
        const lines = (m.line_start != null && m.line_end != null)
          ? (m.line_end - m.line_start + 1) : null;

        let originCell;
        if (kind === "override" && m.overrides) {
          const ov = m.overrides;
          originCell = el("td", {}, [
            el("span", { class: "ovr" }, (ov.origin_module || "—") + " "),
            ov.origin ? originBadge(ov.origin) : null,
          ]);
        } else if (kind === "inherited" && m.inherited_from) {
          const ih = m.inherited_from;
          originCell = el("td", {}, [
            el("span", { class: "ovr" }, (ih.origin_module || "—") + " "),
            ih.origin ? originBadge(ih.origin) : null,
          ]);
        } else {
          originCell = el("td", { style: "color:var(--text-muted)" }, "—");
        }

        const row = el("tr", {
          class: "clickable",
          "data-module": m._module,
          "data-section": m.section || "OTHER",
          "data-kind": kind,
        }, [
          el("td", { class: "mono", style: "font-size:.76rem" }, m.name || "—"),
          el("td", {}, el("span", {
            class: `ft-chip ${SECTION_CLASS[m.section || "OTHER"] || "other"}`,
            style: "font-size:.68rem;padding:.05rem .35rem",
          }, m.section || "OTHER")),
          el("td", {}, el("span", { class: `kind-pill kind-${kind}` }, kind)),
          el("td", { class: "mono", style: "font-size:.76rem" }, m._module
            ? el("a", { href: "#/module/" + encodeURIComponent(m._module) }, m._module)
            : "—"),
          originCell,
          el("td", { class: "num" }, lines != null ? lines : "—"),
          el("td", {}, m.docstring
            ? el("span", { class: "doc-yes" }, "✓")
            : el("span", { class: "doc-no" }, "—")),
        ]);

        row.addEventListener("click", () => openMethodDrawer(m));
        methodsTbody.appendChild(row);
      });

    wrap.appendChild(tableWrap(el("table", {}, [mThead, methodsTbody])));

    function applyMethodFilters() {
      const sec  = sectionSelect.value;
      const kind = kindSelect.value;
      const mod  = modSelect.value;
      for (const row of methodsTbody.querySelectorAll("tr")) {
        const show = (!sec || row.dataset.section === sec)
          && (!kind || row.dataset.kind === kind)
          && (!mod  || row.dataset.module  === mod);
        row.style.display = show ? "" : "none";
      }
    }
    sectionSelect.addEventListener("change", applyMethodFilters);
    kindSelect.addEventListener("change", applyMethodFilters);
  }

  // Phase 3: Wire page-wide module selector to both tables and metrics
  function updateMetricsFor(mod) {
    const ff = mod ? allFields.filter((f) => f._module === mod)  : allFields;
    const fm = mod ? allMethods.filter((m) => m._module === mod) : allMethods;

    // Metrics grid
    const fT = ff.length;
    const fA = ff.filter((f) => f.origin_status === "new" || f.origin_status === "base").length;
    const fI = ff.filter((f) => f.origin_status === "extended").length;
    const mT = fm.length;
    const mA = fm.filter((m) => methodKind(m) === "added").length;
    const mI = fm.filter((m) => methodKind(m) === "inherited").length;
    const mO = fm.filter((m) => methodKind(m) === "override").length;
    metricsGrid.innerHTML = "";
    if (fT) {
      metricsGrid.appendChild(el("div", { class: "mm-row" }, [
        el("span", { class: "mm-label" }, "Fields"),
        mkCard(fT, "Total", "total"),
        mkCard(fA, "Added", "own"),
        mkCard(fI, "Inherited", "extended"),
      ]));
    }
    if (mT) {
      metricsGrid.appendChild(el("div", { class: "mm-row" }, [
        el("span", { class: "mm-label" }, "Methods"),
        mkCard(mT, "Total", "total"),
        mkCard(mA, "Added", "own"),
        mkCard(mI, "Inherited", "extended"),
        mkCard(mO, "Overridden", "override"),
      ]));
    }

    // Fields h2 + by-type chips
    if (fieldsH2) fieldsH2.textContent = `Fields (${fT})`;
    if (typesChipsContainer) {
      typesChipsContainer.innerHTML = "";
      const byType = {};
      ff.forEach((f) => { byType[f.type] = (byType[f.type] || 0) + 1; });
      Object.entries(byType).sort((a, b) => b[1] - a[1]).forEach(([t, n]) =>
        typesChipsContainer.appendChild(el("span", { class: "ft-chip" }, [t, el("span", { class: "count" }, n)]))
      );
    }

    // Methods h2 + section chips
    if (methodsH2) methodsH2.textContent = `Methods (${mT})`;
    if (sectionChipsContainer) {
      sectionChipsContainer.innerHTML = "";
      const bySection = {};
      for (const m of fm) {
        const sec = m.section || "OTHER";
        (bySection[sec] = bySection[sec] || []).push(m);
      }
      Object.entries(bySection).sort((a, b) => b[1].length - a[1].length).forEach(([s, arr]) =>
        sectionChipsContainer.appendChild(el("span", { class: `ft-chip ${SECTION_CLASS[s] || "other"}` }, [
          s, el("span", { class: "count" }, arr.length),
        ]))
      );
    }
  }

  modSelect.addEventListener("change", () => {
    const mod = modSelect.value;
    updateMetricsFor(mod);
    if (fieldsTbody) {
      const type = typeSelect      ? typeSelect.value      : "";
      const kind = fieldKindSelect ? fieldKindSelect.value : "";
      for (const row of fieldsTbody.querySelectorAll("tr")) {
        const show = (!mod  || row.dataset.module === mod)
          && (!type || row.dataset.type === type)
          && (!kind || row.dataset.kind === kind);
        row.style.display = show ? "" : "none";
      }
    }
    if (methodsTbody) {
      const sec  = sectionSelect ? sectionSelect.value : "";
      const kind = kindSelect    ? kindSelect.value    : "";
      for (const row of methodsTbody.querySelectorAll("tr")) {
        const show = (!mod  || row.dataset.module  === mod)
          && (!sec  || row.dataset.section === sec)
          && (!kind || row.dataset.kind    === kind);
        row.style.display = show ? "" : "none";
      }
    }
  });

  return wrap;
}

// ----- Search index -----
let _fuseInstance = null;

function buildSearchIndex() {
  if (_fuseInstance) return _fuseInstance;
  const data = window.OOPS;
  const entries = [];

  for (const mod of (data.modules || [])) {
    const name = mod.module || "";
    const inv = mod.inventory || {};
    const mfst = mod.manifest || {};
    entries.push({
      kind: "module", id: name, label: mfst.name || name, module: name,
      text: [name, mfst.name, mfst.summary, mfst.author].filter(Boolean).join(" "),
      hash: "#/module/" + encodeURIComponent(name),
    });
    for (const f of (mod.fields || [])) {
      const bare = (f.model || "").replace(/^[^:]+:/, "");
      const label = f.label || (f.label_inferred
        ? f.name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
        : f.name);
      entries.push({
        kind: "field", id: f.id || (name + ":" + bare + "#" + f.name),
        label, module: name, model: bare,
        text: [f.name, label, f.help, f.type].filter(Boolean).join(" "),
        hash: "#/model/" + encodeURIComponent(bare),
      });
    }
    for (const m of (mod.methods || [])) {
      const bare = (m.model || "").replace(/^[^:]+:/, "");
      entries.push({
        kind: "method", id: m.id || (name + ":" + bare + "#method:" + m.name),
        label: m.name || "", module: name, model: bare, section: m.section,
        text: [m.name, m.docstring].filter(Boolean).join(" "),
        hash: "#/model/" + encodeURIComponent(bare),
      });
    }
  }

  for (const [bare, entry] of Object.entries(data.models_by_bare || {})) {
    entries.push({
      kind: "model", id: bare, label: bare,
      module: (entry.contributions || []).map((c) => c.module).join(", "),
      text: [bare, entry.description].filter(Boolean).join(" "),
      hash: "#/model/" + encodeURIComponent(bare),
    });
  }

  _fuseInstance = new Fuse(entries, {
    keys: ["label", "id", "text"],
    threshold: 0.3,
    minMatchCharLength: 2,
    includeMatches: false,
  });
  return _fuseInstance;
}

// ----- Search view (#/search) -----
function viewSearch() {
  const wrap = el("div", {});
  wrap.appendChild(el("div", { class: "page-header" }, [el("h1", {}, "Search")]));

  const input = el("input", {
    type: "search",
    class: "search-input",
    placeholder: "Type to search modules, models, fields, methods…",
    autocomplete: "off",
    style: "width:100%;margin-bottom:1.5rem",
  });
  wrap.appendChild(input);

  const resultsEl = el("div", {});
  wrap.appendChild(resultsEl);

  function renderResults(query) {
    resultsEl.innerHTML = "";
    if (!query || query.length < 2) {
      resultsEl.appendChild(el("p", { class: "placeholder" }, "Enter at least 2 characters."));
      return;
    }

    const fuse = buildSearchIndex();
    const hits = fuse.search(query, { limit: 60 });

    if (!hits.length) {
      resultsEl.appendChild(el("p", { class: "placeholder" }, `No results for "${query}".`));
      return;
    }

    const groups = { module: [], model: [], field: [], method: [] };
    for (const h of hits) {
      const k = h.item.kind;
      if (groups[k]) groups[k].push(h.item);
    }

    const kindLabels = { module: "Modules", model: "Models", field: "Fields", method: "Methods" };
    for (const [kind, items] of Object.entries(groups)) {
      if (!items.length) continue;
      resultsEl.appendChild(el("h2", {}, kindLabels[kind]));
      const list = el("div", {});
      for (const item of items) {
        const row = el("div", { class: "search-result-item" });
        row.appendChild(el("a", { href: item.hash }, item.label));
        if (item.model && item.kind !== "model") {
          row.appendChild(el("span", { class: "search-result-meta" }, "in " + item.model));
        }
        if (item.section) {
          row.appendChild(el("span", { class: `ft-chip ${SECTION_CLASS[item.section] || "other"}`, style: "margin:0" }, item.section));
        }
        row.appendChild(el("span", { style: "margin-left:auto" },
          badge(_moduleClassification(item.module))));
        list.appendChild(row);
      }
      resultsEl.appendChild(list);
    }

    const total = hits.length;
    resultsEl.appendChild(el("p", {
      style: "color:var(--text-muted);font-size:0.8rem;margin-top:1rem",
    }, total + " result" + (total !== 1 ? "s" : "") + (total === 60 ? " (capped at 60)" : "")));
  }

  input.addEventListener("input", (e) => renderResults(e.target.value));
  const qs = location.hash.split("?")[1] || "";
  const initialQ = new URLSearchParams(qs).get("q") || "";
  if (initialQ) { input.value = initialQ; renderResults(initialQ); }
  setTimeout(() => input.focus(), 0);
  return wrap;
}

function _moduleClassification(moduleName) {
  const mod = (window.OOPS.modules || []).find((m) => m.module === moduleName);
  return (mod?.inventory || {}).classification || "unknown";
}

// ----- Placeholder views -----
function viewMethodPlaceholder(slug) {
  return el("div", {}, [
    el("h1", {}, "Method"),
    el("p", { class: "placeholder" }, slug),
  ]);
}
