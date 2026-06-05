// oops SPA — Phase 3: module page + model page
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

const badge = (cls) => el("span", { class: "badge " + (cls || "unknown") }, cls || "—");

const numCell = (n) =>
  el("td", { class: "num" + (n ? "" : " zero") }, n != null ? String(n) : "0");

// ----- renderRef: DocModel ref → DOM node -----
// ref = {kind:"link", path, anchor} | {kind:"external", name, origin} | null
function renderRef(ref) {
  if (!ref) return el("span", { style: "color:var(--text-muted)" }, "—");
  if (ref.kind === "link") {
    // path is a Markdown site path like "models/res.partner.md" or "methods/pm-…md"
    const hash = mdPathToHash(ref.path);
    const anchor = ref.anchor ? "#" + ref.anchor : "";
    const name = ref.path.replace(/^.*\//, "").replace(/\.md$/, "");
    return el("a", { href: hash + anchor }, name);
  }
  // external
  const wrap = el("span", {});
  wrap.appendChild(document.createTextNode(ref.name || "—"));
  if (ref.origin) {
    wrap.appendChild(document.createTextNode(" "));
    wrap.appendChild(el("span", { class: "badge " + (ref.origin || "unknown"),
      style: "font-size:0.7rem" }, ref.origin));
  }
  return wrap;
}

function mdPathToHash(path) {
  if (!path) return "#/";
  if (path.startsWith("models/")) return "#/model/" + path.slice(7).replace(/\.md$/, "");
  if (path.startsWith("methods/")) return "#/method/" + path.slice(8).replace(/\.md$/, "");
  if (path.startsWith("modules/")) return "#/module/" + path.slice(8).replace(/\.md$/, "");
  return "#/";
}

// ----- Schema descriptor helpers -----
function descriptorTitle(group, key) {
  const schema = window.OOPS.schema || {};
  return (((schema.definitions || {})[group] || {}).properties || {})[key]?.title || key;
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
  return String(value);
}

// ----- Method section order -----
const SECTION_ORDER = ["COMPUTE", "SELECTION", "DEFAULT", "ONCHANGE", "CONSTRAINT",
  "CRUD", "HELPER", "ACTION", "BUSINESS", "OTHER"];

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
  for (const r of ROUTES) {
    const m = hash.match(r.re);
    if (m) { app.innerHTML = ""; app.appendChild(r.view(m)); return; }
  }
  app.innerHTML = "";
  app.appendChild(el("p", { class: "placeholder" }, "Page not found: " + hash));
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", route);

// ----- Repo index view (#/) -----
function viewIndex() {
  const data = window.OOPS;
  const modules = data.modules || [];

  const wrap = el("div", {});
  wrap.appendChild(el("h1", {}, "Project Addons"));

  const byClass = {};
  let totalLoc = 0;
  for (const mod of modules) {
    const inv = mod.inventory || {};
    const cls = inv.classification || "unknown";
    byClass[cls] = (byClass[cls] || 0) + 1;
    totalLoc += (inv.loc || {}).total || 0;
  }

  const summaryParts = [modules.length + " addons", "LOC: " + totalLoc.toLocaleString()];
  for (const [cls, cnt] of Object.entries(byClass)) {
    summaryParts.push(cnt + " " + cls);
  }
  wrap.appendChild(el("p", { style: "color:var(--text-muted);margin-bottom:1.5rem" },
    summaryParts.join(" · ")));

  const thead = el("thead", {}, [
    el("tr", {}, [
      el("th", {}, "Addon"),
      el("th", {}, "Classification"),
      el("th", {}, "Version"),
      el("th", { style: "text-align:right" }, "LOC"),
    ]),
  ]);

  const rows = [];
  for (const mod of modules) {
    const inv = mod.inventory || {};
    const name = mod.module || "—";
    const cls = inv.classification || "unknown";
    const version = inv.version || "—";
    const loc = (inv.loc || {}).total || 0;
    rows.push(el("tr", {}, [
      el("td", {}, el("a", { href: "#/module/" + encodeURIComponent(name) }, name)),
      el("td", {}, badge(cls)),
      el("td", {}, version),
      numCell(loc),
    ]));
  }

  rows.push(el("tr", { class: "summary-row" }, [
    el("td", {}, "Total (" + modules.length + " addons)"),
    el("td", {}, Object.entries(byClass).map(([c, n]) =>
      el("span", { style: "margin-right:0.5rem" }, [badge(c), " " + n])
    )),
    el("td", {}),
    numCell(totalLoc),
  ]));

  wrap.appendChild(el("table", {}, [thead, el("tbody", {}, rows)]));
  return wrap;
}

// ----- Module page (#/module/:name) -----
function viewModule(name) {
  const data = window.OOPS;
  const mod = (data.modules || []).find((m) => m.module === name);
  if (!mod) {
    return el("p", { class: "placeholder" }, "Module not found: " + name);
  }

  const wrap = el("div", {});

  // Title + classification badge
  const inv = mod.inventory || {};
  const titleRow = el("div", { style: "display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem" });
  titleRow.appendChild(el("h1", { style: "margin:0" }, name));
  if (inv.classification) titleRow.appendChild(badge(inv.classification));
  wrap.appendChild(titleRow);

  // Version + submodule
  const meta = [];
  if (inv.version) meta.push("v" + inv.version);
  if (inv.submodule) meta.push("submodule: " + inv.submodule);
  if (inv.branch) meta.push("branch: " + inv.branch);
  if (meta.length) {
    wrap.appendChild(el("p", { style: "color:var(--text-muted);margin:0 0 1.5rem" },
      meta.join(" · ")));
  }

  // README
  const readme = mod.readme || {};
  if (readme.present && readme.content) {
    wrap.appendChild(el("h2", {}, "README"));
    wrap.appendChild(el("pre", { style: "white-space:pre-wrap" }, readme.content));
  }

  // Stat cards: manifest + metrics + loc
  wrap.appendChild(el("h2", {}, "Statistics"));
  const statsGrid = el("div", { class: "stats-grid" });

  for (const [group, values] of [
    ["manifest", mod.manifest || {}],
    ["metrics", mod.metrics || {}],
    ["loc", mod.loc || {}],
  ]) {
    for (const [key, value] of Object.entries(values)) {
      if (value == null) continue;
      const title = descriptorTitle(group, key);
      const kind = descriptorKind(group, key);
      const card = el("div", { class: "stat-card" });
      card.appendChild(el("div", { class: "stat-label" }, title));
      card.appendChild(el("div", { class: "stat-value" }, formatValue(value, kind)));
      statsGrid.appendChild(card);
    }
  }
  wrap.appendChild(statsGrid);

  // not_analysed
  if (mod.not_analysed && mod.not_analysed.length) {
    wrap.appendChild(el("h2", {}, "Not analysed"));
    wrap.appendChild(el("p", { style: "color:var(--text-muted)" },
      mod.not_analysed.map((p) => el("code", { style: "margin-right:0.5rem" }, p))
    ));
  }

  // Models contributed by this module
  const modelEntries = Object.entries(data.models_by_bare || {})
    .filter(([, entry]) =>
      (entry.contributions || []).some((c) => c.module === name)
    );

  if (modelEntries.length) {
    wrap.appendChild(el("h2", {}, "Models"));
    const thead = el("thead", {}, [
      el("tr", {}, [
        el("th", {}, "Model"),
        el("th", {}, "Status"),
        el("th", { style: "text-align:right" }, "Fields"),
        el("th", { style: "text-align:right" }, "Methods"),
      ]),
    ]);
    const rows = modelEntries.map(([bare, entry]) => {
      const contrib = (entry.contributions || []).find((c) => c.module === name) || {};
      const node = contrib.model_node || {};
      return el("tr", {}, [
        el("td", {}, el("a", { href: "#/model/" + encodeURIComponent(bare) }, bare)),
        el("td", {}, node.status || "—"),
        numCell((contrib.fields || []).length),
        numCell((contrib.methods || []).length),
      ]);
    });
    wrap.appendChild(el("table", {}, [thead, el("tbody", {}, rows)]));
  }

  return wrap;
}

// ----- Model page (#/model/:bare) -----
function viewModel(bare) {
  const data = window.OOPS;
  const entry = (data.models_by_bare || {})[bare];
  if (!entry) {
    return el("p", { class: "placeholder" }, "Model not found: " + bare);
  }

  const contributions = entry.contributions || [];
  const wrap = el("div", {});

  // Title
  wrap.appendChild(el("h1", {}, bare));

  // Description
  if (entry.description) {
    const descEl = el("p", { style: "color:var(--text-muted);font-style:italic;margin:0 0 0.5rem" },
      entry.description);
    if (entry.description_inherited_from) {
      descEl.appendChild(document.createTextNode(
        " (inherited from " + entry.description_inherited_from + ")"
      ));
    }
    wrap.appendChild(descEl);
  }

  // Provenance
  wrap.appendChild(el("h2", {}, "Provenance"));
  const prov = el("p", { style: "color:var(--text-muted)" });
  prov.appendChild(document.createTextNode(
    "Extended by " + contributions.length + " module" + (contributions.length !== 1 ? "s" : "") + ": "
  ));
  contributions.forEach((c, i) => {
    if (i > 0) prov.appendChild(document.createTextNode(", "));
    prov.appendChild(el("a", { href: "#/module/" + encodeURIComponent(c.module) }, c.module));
    prov.appendChild(document.createTextNode(
      " (" + (c.fields || []).length + " fields, " + (c.methods || []).length + " methods)"
    ));
  });
  wrap.appendChild(prov);

  // ----- Fields table with module + type filter -----
  const allFields = contributions.flatMap((c) =>
    (c.fields || []).map((f) => ({ ...f, _module: c.module }))
  );

  if (allFields.length) {
    wrap.appendChild(el("h2", {}, "Fields"));

    // Filter controls
    const modules = [...new Set(allFields.map((f) => f._module))];
    const types = [...new Set(allFields.map((f) => f.type || "").filter(Boolean))].sort();

    const filterRow = el("div", { style: "display:flex;gap:1rem;margin-bottom:0.75rem;align-items:center" });
    const modSelect = el("select", { style: "padding:0.3rem 0.5rem;border:1px solid var(--border);border-radius:4px" });
    modSelect.appendChild(el("option", { value: "" }, "All modules"));
    modules.forEach((m) => modSelect.appendChild(el("option", { value: m }, m)));
    const typeSelect = el("select", { style: "padding:0.3rem 0.5rem;border:1px solid var(--border);border-radius:4px" });
    typeSelect.appendChild(el("option", { value: "" }, "All types"));
    types.forEach((t) => typeSelect.appendChild(el("option", { value: t }, t)));
    filterRow.appendChild(el("label", {}, ["Module: ", modSelect]));
    filterRow.appendChild(el("label", {}, ["Type: ", typeSelect]));
    wrap.appendChild(filterRow);

    const thead = el("thead", {}, [
      el("tr", {}, [
        el("th", {}, "Field"),
        el("th", {}, "Type"),
        el("th", {}, "Label"),
        el("th", {}, "Help"),
        el("th", {}, "Flags"),
        el("th", {}, "Module"),
        el("th", {}, "Kind"),
      ]),
    ]);

    const tbody = el("tbody", {});
    allFields.forEach((f) => {
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
      ].filter(Boolean).join(" ");
      const status = f.origin_status === "new" ? "addition"
        : f.origin_status === "extended" ? "inheritance" : (f.origin_status || "—");

      // Type cell: comodel_ref if present
      let typeCell;
      if (f.comodel_ref) {
        typeCell = el("td", {}, [(f.type || "—") + " → ", renderRef(f.comodel_ref)]);
      } else {
        typeCell = el("td", {}, f.type || "—");
      }

      const row = el("tr", {
        "data-module": f._module,
        "data-type": f.type || "",
      }, [
        el("td", {}, el("code", {}, f.name || "—")),
        typeCell,
        el("td", {}, label),
        el("td", { style: "font-size:0.8rem;color:var(--text-muted)" }, helpText),
        el("td", { style: "font-size:0.8rem" }, flags || "—"),
        el("td", {}, badge((data.modules || []).find((m) => m.module === f._module)?.inventory?.classification)),
        el("td", { style: "font-size:0.8rem" }, status),
      ]);
      tbody.appendChild(row);
    });

    const table = el("table", {}, [thead, tbody]);
    wrap.appendChild(table);

    // Wire filters
    function applyFilters() {
      const mod = modSelect.value;
      const type = typeSelect.value;
      for (const row of tbody.querySelectorAll("tr")) {
        const show = (!mod || row.dataset.module === mod) &&
                     (!type || row.dataset.type === type);
        row.style.display = show ? "" : "none";
      }
    }
    modSelect.addEventListener("change", applyFilters);
    typeSelect.addEventListener("change", applyFilters);
  }

  // ----- Methods grouped by section -----
  const allMethods = contributions.flatMap((c) =>
    (c.methods || []).map((m) => ({ ...m, _module: c.module }))
  );

  if (allMethods.length) {
    wrap.appendChild(el("h2", {}, "Methods"));

    // Group by section
    const bySection = {};
    for (const m of allMethods) {
      const sec = m.section || "OTHER";
      (bySection[sec] = bySection[sec] || []).push(m);
    }

    const sectionOrder = [...SECTION_ORDER];
    for (const sec of Object.keys(bySection)) {
      if (!sectionOrder.includes(sec)) sectionOrder.push(sec);
    }

    for (const sec of sectionOrder) {
      const methods = bySection[sec];
      if (!methods || !methods.length) continue;

      wrap.appendChild(el("h3", { style: "font-size:1rem;margin:1.25rem 0 0.5rem;color:var(--text-muted)" },
        sec));

      const thead = el("thead", {}, [
        el("tr", {}, [
          el("th", {}, "Method"),
          el("th", {}, "Signature"),
          el("th", {}, "Module"),
          el("th", {}, "Overrides"),
          el("th", {}, "Docstring"),
        ]),
      ]);

      const rows = methods.map((m) => {
        // Decorators (api.depends targets)
        const decorators = (m.decorators || []).join(", ");
        const sig = (m.signature || "") + (decorators ? "\n" + decorators : "");

        let overrideCell;
        if (m.overrides) {
          const ov = m.overrides;
          if (m.model_ref) {
            overrideCell = renderRef(m.model_ref);
          } else {
            const originText = ov.origin_module || "—";
            overrideCell = el("span", {}, [
              originText,
              ov.origin ? el("span", {}, [" ", el("span", {
                class: "badge " + ov.origin, style: "font-size:0.7rem"
              }, ov.origin)]) : null,
            ]);
          }
        } else {
          overrideCell = el("span", { style: "color:var(--text-muted)" }, "—");
        }

        const docText = m.docstring
          ? (m.docstring.length > 80 ? m.docstring.slice(0, 80) + "…" : m.docstring)
          : "—";

        return el("tr", {}, [
          el("td", {}, el("code", {}, m.name || "—")),
          el("td", {}, el("code", { style: "font-size:0.8rem;white-space:pre" }, sig)),
          el("td", {}, m._module ? badge(
            (data.modules || []).find((mod) => mod.module === m._module)?.inventory?.classification
          ) : "—"),
          el("td", {}, overrideCell),
          el("td", { style: "font-size:0.8rem;color:var(--text-muted)" }, docText),
        ]);
      });

      wrap.appendChild(el("table", {}, [thead, el("tbody", {}, rows)]));
    }
  }

  // Override graph placeholder
  wrap.appendChild(el("h2", {}, "Override Graph"));
  wrap.appendChild(el("p", { class: "placeholder" }, "Graph view coming soon."));

  return wrap;
}

// ----- Search index (built once, cached) -----
let _fuseInstance = null;

function buildSearchIndex() {
  if (_fuseInstance) return _fuseInstance;
  const data = window.OOPS;
  const entries = [];

  for (const mod of (data.modules || [])) {
    const name = mod.module || "";
    const inv = mod.inventory || {};
    const mfst = mod.manifest || {};

    // Module entry
    entries.push({
      kind: "module",
      id: name,
      label: mfst.name || name,
      module: name,
      text: [name, mfst.name, mfst.summary, mfst.author].filter(Boolean).join(" "),
      hash: "#/module/" + encodeURIComponent(name),
    });

    // Field entries
    for (const f of (mod.fields || [])) {
      const bare = (f.model || "").replace(/^[^:]+:/, "");
      const label = f.label || (f.label_inferred
        ? f.name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
        : f.name);
      entries.push({
        kind: "field",
        id: f.id || (name + ":" + bare + "#" + f.name),
        label: label,
        module: name,
        model: bare,
        text: [f.name, label, f.help, f.type].filter(Boolean).join(" "),
        hash: "#/model/" + encodeURIComponent(bare),
      });
    }

    // Method entries
    for (const m of (mod.methods || [])) {
      const bare = (m.model || "").replace(/^[^:]+:/, "");
      entries.push({
        kind: "method",
        id: m.id || (name + ":" + bare + "#method:" + m.name),
        label: m.name || "",
        module: name,
        model: bare,
        section: m.section,
        text: [m.name, m.docstring].filter(Boolean).join(" "),
        hash: "#/model/" + encodeURIComponent(bare),
      });
    }
  }

  // Model entries (deduplicated from models_by_bare)
  for (const [bare, entry] of Object.entries(data.models_by_bare || {})) {
    entries.push({
      kind: "model",
      id: bare,
      label: bare,
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
  wrap.appendChild(el("h1", {}, "Search"));

  const input = el("input", {
    type: "search",
    placeholder: "Type to search modules, models, fields, methods…",
    style: "width:100%;padding:0.6rem 0.8rem;font-size:1rem;border:1px solid var(--border);border-radius:6px;margin-bottom:1.5rem",
    autocomplete: "off",
  });
  wrap.appendChild(input);

  const resultsEl = el("div", {});
  wrap.appendChild(resultsEl);

  function renderResults(query) {
    resultsEl.innerHTML = "";
    if (!query || query.length < 2) {
      resultsEl.appendChild(el("p", { style: "color:var(--text-muted)" },
        "Enter at least 2 characters."));
      return;
    }

    const fuse = buildSearchIndex();
    const hits = fuse.search(query, { limit: 60 });

    if (!hits.length) {
      resultsEl.appendChild(el("p", { class: "placeholder" }, 'No results for "' + query + '".'));
      return;
    }

    // Group by kind
    const groups = { module: [], model: [], field: [], method: [] };
    for (const h of hits) {
      const k = h.item.kind;
      if (groups[k]) groups[k].push(h.item);
    }

    const kindLabels = { module: "Modules", model: "Models", field: "Fields", method: "Methods" };
    for (const [kind, items] of Object.entries(groups)) {
      if (!items.length) continue;
      resultsEl.appendChild(el("h2", { style: "margin-top:1.25rem" }, kindLabels[kind]));
      const list = el("ul", { style: "list-style:none;padding:0;margin:0" });
      for (const item of items) {
        const li = el("li", {
          style: "padding:0.5rem 0;border-bottom:1px solid var(--border);display:flex;gap:0.75rem;align-items:baseline",
        });
        const link = el("a", { href: item.hash }, item.label);
        li.appendChild(link);
        if (item.model && item.kind !== "model") {
          li.appendChild(el("span", { style: "font-size:0.8rem;color:var(--text-muted)" },
            "in " + item.model));
        }
        if (item.section) {
          li.appendChild(el("span", { style: "font-size:0.75rem;color:var(--text-muted)" },
            "[" + item.section + "]"));
        }
        li.appendChild(el("span", { style: "margin-left:auto" },
          badge(_moduleClassification(item.module))));
        list.appendChild(li);
      }
      resultsEl.appendChild(list);
    }

    const total = hits.length;
    resultsEl.appendChild(el("p", {
      style: "color:var(--text-muted);font-size:0.8rem;margin-top:1rem",
    }, total + " result" + (total !== 1 ? "s" : "") + (total === 60 ? " (capped at 60)" : "")));
  }

  // Focus input and wire event
  input.addEventListener("input", (e) => renderResults(e.target.value));
  // Restore query from URL hash if present: #/search?q=foo
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
  const wrap = el("div", {});
  wrap.appendChild(el("h1", {}, "Method"));
  wrap.appendChild(el("p", { class: "placeholder" }, slug));
  return wrap;
}
