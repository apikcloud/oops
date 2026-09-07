import * as d3 from "d3";
import type { Payload } from "../types";
import type { Source } from "../source";
import { el, fmt, numCell, tableWrap, originBadge, renderMetadataBar } from "../dom";

interface UpgradeOrigin { kind: string; repo: string | null; ref: string | null; }
interface UpgradePR { number: number; url: string; title: string; }
interface UpgradeModule {
  origin: UpgradeOrigin;
  depends_on: string[];
  upstream_available: boolean | null;
  upstream_prs: UpgradePR[];
}
interface UpgradeMetrics {
  total: number; custom: number; oca: number; third_party: number;
  upstream_available: number; upstream_missing: number;
  not_probed: number; target_deps_fetched: number;
}
interface UpgradeEffort { to_pull: number; in_pr: number; to_port: number; not_probed: number; }
interface UpgradeParams {
  from_version?: string;
  to_version?: string;
  [k: string]: unknown;
}
interface UpgradePayload {
  source_ref: string;
  state_path: string;
  metrics: UpgradeMetrics;
  effort: UpgradeEffort;
  modules: Record<string, UpgradeModule>;
  warnings?: string[];
  metadata: Payload["metadata"] & { parameters?: UpgradeParams };
}

type RichModule = UpgradeModule & { _name: string; _depCount: number; _upstreamKey: number; };

function readColor(varName: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
}

function upstreamCell(m: RichModule): HTMLElement {
  const { origin, upstream_available, upstream_prs } = m;
  if (origin.kind === "custom") {
    return el("span", { class: "upstream dim" }, "—");
  }
  if (upstream_available === null) {
    return el("span", { class: "upstream dim" }, "?");
  }
  if (upstream_available === true) {
    return el("span", { class: "upstream ok" }, "✓");
  }
  if (upstream_prs?.length > 0) {
    return el("a", { class: "upstream pr", href: upstream_prs[0].url, target: "_blank" }, "~ PR");
  }
  return el("span", { class: "upstream danger" }, "✗");
}

function upstreamSortKey(m: UpgradeModule): number {
  if (m.origin.kind === "custom") return 4;
  if (m.upstream_available === null) return 3;
  if (m.upstream_available === true) return 0;
  if (m.upstream_prs?.length > 0) return 1;
  return 2;
}

export function viewUpgradeAnalyze(root: HTMLElement, payload: Payload, _source: Source): void {
  const p = payload as unknown as UpgradePayload;
  const metrics = p.metrics;
  const effort = p.effort;

  const allModules: RichModule[] = Object.entries(p.modules).map(([name, m]) => ({
    ...m,
    _name: name,
    _depCount: (m.depends_on ?? []).length,
    _upstreamKey: upstreamSortKey(m),
  }));

  const byClass: Record<string, number> = {
    custom: metrics.custom,
    oca: metrics.oca,
    "third-party": metrics.third_party,
  };

  // --- Metadata bar ---
  const metaBar = renderMetadataBar(p.metadata);
  if (metaBar) root.append(metaBar);

  // --- Page header ---
  const params = p.metadata?.parameters;
  const fromVer = params?.from_version ?? "?";
  const toVer   = params?.to_version   ?? "?";
  const versionIndicator = el("div", { class: "upgrade-indicator" }, [
    el("span", { class: "upgrade-version from" }, fromVer),
    el("span", { class: "upgrade-arrow" }, "→"),
    el("span", { class: "upgrade-version to" }, toVer),
  ]);
  root.append(el("div", { class: "page-header" }, [
    el("div", { class: "page-header-row" }, [
      el("h1", {}, "Upgrade analysis"),
      versionIndicator,
    ]),
    el("p", { class: "page-subtitle" }, `${metrics.total} modules · ${metrics.custom} custom · ${metrics.oca} OCA · ${metrics.third_party} third-party`),
  ]));

  // --- Warnings ---
  if (p.warnings?.length) {
    root.append(el("div", { class: "warnings" },
      el("ul", {}, p.warnings.map((w) => el("li", {}, w)))
    ));
  }

  // --- Metric card ---
  const effortRows: [string, number][] = [
    ["To pull", effort.to_pull],
    ["In PR", effort.in_pr],
    ["To port", effort.to_port],
  ];
  if (effort.not_probed) effortRows.push(["Not probed", effort.not_probed]);

  const effortCard = el("div", { class: "stat-card" }, el("div", { class: "stat-card-label" }, "Effort"));
  for (const [label, value] of effortRows) {
    effortCard.append(el("div", { class: "stat-row" }, [
      el("span", { class: "label" }, label),
      el("span", { class: "value" }, fmt(value)),
    ]));
  }

  // --- D3 donut ---
  const donutContainer = el("div", { class: "chart-container" });
  const donutLegend = el("div", { class: "legend" });

  root.append(el("div", { class: "charts-row" }, [
    effortCard,
    el("div", { class: "chart-card" }, [
      el("h3", {}, "Effort breakdown"),
      donutContainer,
      donutLegend,
    ]),
  ]));

  setTimeout(() => {
    const COLORS: Record<string, string> = {
      to_pull:    readColor("--ok"),
      in_pr:      readColor("--warning"),
      to_port:    readColor("--danger"),
      not_probed: readColor("--text-muted"),
    };
    const slices = [
      { key: "to_pull",    label: "To pull",    value: effort.to_pull },
      { key: "in_pr",      label: "In PR",      value: effort.in_pr },
      { key: "to_port",    label: "To port",    value: effort.to_port },
      { key: "not_probed", label: "Not probed", value: effort.not_probed },
    ].filter((d) => d.value > 0);

    if (slices.length) {
      const w = 220, h = 220, r = Math.min(w, h) / 2;
      const svg = d3.select(donutContainer).append("svg")
        .attr("viewBox", `${-w / 2} ${-h / 2} ${w} ${h}`)
        .attr("width", w).attr("height", h);
      const pie = d3.pie<{ key: string; label: string; value: number }>().value((d) => d.value).sort(null);
      const arc = d3.arc<d3.PieArcDatum<{ key: string; label: string; value: number }>>()
        .innerRadius(r * 0.55).outerRadius(r - 5);
      svg.selectAll<SVGPathElement, d3.PieArcDatum<{ key: string; label: string; value: number }>>("path")
        .data(pie(slices)).join("path")
        .attr("d", arc)
        .attr("fill", (d) => COLORS[d.data.key] || "#999")
        .attr("stroke", "white").attr("stroke-width", 2);
      svg.append("text").attr("text-anchor", "middle").attr("dy", "-0.2em")
        .style("font-size", "1.4rem").style("font-weight", "600")
        .style("font-family", "var(--mono)").text(metrics.total);
      svg.append("text").attr("text-anchor", "middle").attr("dy", "1.2em")
        .style("font-size", ".7rem").style("fill", "var(--text-muted)")
        .style("text-transform", "uppercase").style("letter-spacing", ".05em").text("modules");
      slices.forEach((d) => {
        const li = d3.select(donutLegend).append("div").attr("class", "legend-item");
        li.append("span").attr("class", "legend-swatch").style("background", COLORS[d.key] || "#999");
        li.append("span").text(`${d.label} (${d.value})`);
      });
    }
  }, 0);

  // --- Filter + search ---
  const state = {
    sortKey: "_name", sortDir: "asc" as "asc" | "desc",
    classification: "all", search: "",
  };

  root.append(el("h2", {}, "Modules"));

  const filtersEl = el("div", { class: "filters" });
  const searchInput = el("input", {
    type: "search", class: "search-input",
    placeholder: "Search by name or repo…", autocomplete: "off",
  }) as HTMLInputElement;
  filtersEl.append(searchInput);

  const pillDefs = [
    { label: "All", cls: "all" },
    { label: "Custom", cls: "custom" },
    { label: "OCA", cls: "oca" },
    { label: "Third-party", cls: "third-party" },
  ];
  const pillBtns = pillDefs.map(({ label, cls }) => {
    const count = cls === "all" ? metrics.total : (byClass[cls] || 0);
    const btn = el("button", {
      class: "filter-btn" + (cls === "all" ? " active" : ""),
      "data-cls": cls,
    }, [label, el("span", { class: "filter-count" }, count)]);
    btn.addEventListener("click", () => {
      pillBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.classification = cls;
      renderTable();
    });
    filtersEl.append(btn);
    return btn;
  });
  root.append(filtersEl);

  // --- Sortable table ---
  const thead = el("thead", {}, [
    el("tr", {}, [
      el("th", { class: "sortable", "data-sort": "_name" }, "Module"),
      el("th", { class: "sortable", "data-sort": "origin.kind" }, "Origin"),
      el("th", { class: "muted sortable", "data-sort": "origin.repo" }, "Repo"),
      el("th", { class: "num sortable", "data-sort": "_depCount" }, "Deps"),
      el("th", { class: "sortable", "data-sort": "_upstreamKey" }, "Upstream"),
    ]),
  ]);
  for (const th of thead.querySelectorAll<HTMLElement>("th[data-sort]")) {
    th.addEventListener("click", () => {
      const key = th.dataset.sort!;
      state.sortDir = state.sortKey === key && state.sortDir === "asc" ? "desc" : "asc";
      state.sortKey = key;
      renderTable();
    });
  }

  const tbody = el("tbody", {});
  const emptyState = el("div", { class: "empty-state" }, "No modules match.");
  (emptyState as HTMLElement).style.display = "none";
  root.append(tableWrap(el("table", {}, [thead, tbody])));
  root.append(emptyState);

  function sortVal(m: RichModule, key: string): unknown {
    if (key === "_name") return m._name;
    if (key === "_depCount") return m._depCount;
    if (key === "_upstreamKey") return m._upstreamKey;
    if (key === "origin.kind") return m.origin.kind;
    if (key === "origin.repo") return m.origin.repo ?? "";
    return "";
  }

  function renderTable() {
    tbody.innerHTML = "";
    const query = state.search.toLowerCase();
    const filtered = allModules.filter((m) => {
      if (state.classification !== "all" && m.origin.kind !== state.classification) return false;
      if (!query) return true;
      return (
        m._name.toLowerCase().includes(query) ||
        (m.origin?.repo ?? "").toLowerCase().includes(query)
      );
    });

    const sorted = [...filtered].sort((a, b) => {
      const av = sortVal(a, state.sortKey);
      const bv = sortVal(b, state.sortKey);
      if (typeof av === "number" && typeof bv === "number")
        return state.sortDir === "asc" ? av - bv : bv - av;
      return state.sortDir === "asc"
        ? String(av ?? "").localeCompare(String(bv ?? ""))
        : String(bv ?? "").localeCompare(String(av ?? ""));
    });

    (emptyState as HTMLElement).style.display = sorted.length === 0 ? "" : "none";

    for (const m of sorted) {
      tbody.append(el("tr", {}, [
        el("td", {}, el("div", { class: "addon-name" }, m._name)),
        el("td", {}, originBadge(m.origin.kind)),
        el("td", { class: "muted mono" }, m.origin.repo ?? "—"),
        numCell(m._depCount || null),
        el("td", {}, upstreamCell(m)),
      ]));
    }

    for (const th of thead.querySelectorAll<HTMLElement>("th[data-sort]")) {
      th.classList.remove("sorted-asc", "sorted-desc");
      if (th.dataset.sort === state.sortKey)
        th.classList.add(state.sortDir === "asc" ? "sorted-asc" : "sorted-desc");
    }
  }

  searchInput.addEventListener("input", () => { state.search = searchInput.value; renderTable(); });
  renderTable();
}
