import * as d3 from "d3";
import type { Payload, ListPayload, Addon, MetricGroup } from "../types";
import { el, fmt, humanize, badge, numCell, tableWrap, renderMetadataBar } from "../dom";

// Extend Addon with precomputed total
type RichAddon = Addon & { _locTotal: number; summary?: string };

const LOC_KEYS = ["python", "xml", "javascript", "docs"] as const;

function locTotal(a: Addon): number {
  return a.loc ? a.loc.python + a.loc.xml + a.loc.javascript + a.loc.docs : 0;
}

function readColor(varName: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
}

export function viewList(root: HTMLElement, payload: Payload): void {
  const p = payload as unknown as ListPayload;
  const addons = (p.data ?? []) as RichAddon[];

  // Precompute per-addon totals
  const byClass: Record<string, number> = {};
  const locTotals: Record<string, number> = { python: 0, xml: 0, javascript: 0, docs: 0 };
  for (const a of addons) {
    a._locTotal = locTotal(a);
    const cls = a.classification || "unknown";
    byClass[cls] = (byClass[cls] || 0) + 1;
    for (const k of LOC_KEYS) locTotals[k] += a.loc?.[k] ?? 0;
  }

  // --- Metadata bar ---
  const metaBar = renderMetadataBar(p.metadata);
  if (metaBar) root.append(metaBar);

  // --- Page header ---
  const totalLoc = addons.reduce((s, a) => s + a._locTotal, 0);
  root.append(el("div", { class: "page-header" }, [
    el("h1", {}, "Addons"),
    el("p", { class: "page-subtitle" }, `${addons.length} addons · ${fmt(totalLoc)} total LoC`),
  ]));

  // --- Warnings ---
  if (p.warnings?.length) {
    root.append(el("div", { class: "warnings" },
      el("ul", {}, p.warnings.map((w) => el("li", {}, w)))
    ));
  }

  // --- Metrics cards ---
  if (p.metrics?.length) {
    const cards = el("div", { class: "stats-grid" });
    for (const g of p.metrics as MetricGroup[]) {
      const card = el("div", { class: "stat-card" }, el("div", { class: "stat-card-label" }, g.label));
      for (const v of g.values) {
        const isTotal = (v.name || "").toLowerCase() === "total";
        card.append(el("div", { class: `stat-row${isTotal ? " is-total" : ""}` }, [
          el("span", { class: "label" }, String(v.label ?? humanize(v.name))),
          el("span", { class: "value" }, fmt(v.value)),
        ]));
      }
      cards.append(card);
    }
    root.append(cards);
  }

  // --- Charts row (D3 renders after DOM insertion via setTimeout) ---
  const donutContainer = el("div", { class: "chart-container" });
  const donutLegend = el("div", { class: "legend" });
  const locContainer = el("div", { class: "chart-container" });
  const locLegend = el("div", { class: "legend" });
  root.append(el("div", { class: "charts-row" }, [
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
    const CCOLORS: Record<string, string> = {
      oca: readColor("--oca"),
      custom: readColor("--custom"),
      "third-party": readColor("--third-party"),
    };
    const LCOLORS: Record<string, string> = {
      python: readColor("--loc-python"),
      xml: readColor("--loc-xml"),
      javascript: readColor("--loc-javascript"),
      docs: readColor("--loc-docs"),
    };

    // Classification donut
    const cData = Object.entries(byClass)
      .map(([key, value]) => ({ key, value }))
      .sort((a, b) => b.value - a.value);
    if (cData.length) {
      const w = 220, h = 220, r = Math.min(w, h) / 2;
      const svg = d3.select(donutContainer).append("svg")
        .attr("viewBox", `${-w / 2} ${-h / 2} ${w} ${h}`)
        .attr("width", w).attr("height", h);
      const pie = d3.pie<{ key: string; value: number }>().value((d) => d.value).sort(null);
      const arc = d3.arc<d3.PieArcDatum<{ key: string; value: number }>>()
        .innerRadius(r * 0.55).outerRadius(r - 5);
      svg.selectAll<SVGPathElement, d3.PieArcDatum<{ key: string; value: number }>>("path")
        .data(pie(cData)).join("path")
        .attr("d", arc)
        .attr("fill", (d) => CCOLORS[d.data.key] || "#999")
        .attr("stroke", "white").attr("stroke-width", 2);
      svg.append("text").attr("text-anchor", "middle").attr("dy", "-0.2em")
        .style("font-size", "1.4rem").style("font-weight", "600")
        .style("font-family", "var(--mono)").text(addons.length);
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
    const lData = Object.entries(locTotals)
      .filter(([, v]) => v > 0)
      .map(([key, value]) => ({ key, value }));
    if (lData.length) {
      const w = 300, h = 220;
      const m = { top: 10, right: 10, bottom: 28, left: 52 };
      const iW = w - m.left - m.right, iH = h - m.top - m.bottom;
      const svg = d3.select(locContainer).append("svg")
        .attr("viewBox", `0 0 ${w} ${h}`).attr("width", w).attr("height", h);
      const g = svg.append("g").attr("transform", `translate(${m.left},${m.top})`);
      const x = d3.scaleBand().domain(lData.map((d) => d.key)).range([0, iW]).padding(0.3);
      const y = d3.scaleLinear()
        .domain([0, d3.max(lData, (d) => d.value) ?? 0]).nice().range([iH, 0]);
      g.selectAll("rect").data(lData).join("rect")
        .attr("x", (d) => x(d.key) ?? 0).attr("y", (d) => y(d.value))
        .attr("width", x.bandwidth()).attr("height", (d) => iH - y(d.value))
        .attr("fill", (d) => LCOLORS[d.key] || "#999").attr("rx", 2);
      g.selectAll<SVGTextElement, { key: string; value: number }>("text.bar-label")
        .data(lData).join("text")
        .attr("class", "bar-label")
        .attr("x", (d) => (x(d.key) ?? 0) + x.bandwidth() / 2)
        .attr("y", (d) => y(d.value) - 4)
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

  // --- Filter + search ---
  const state = { sortKey: "_locTotal", sortDir: "desc" as "asc" | "desc", classification: "all", search: "" };

  root.append(el("h2", {}, "All addons"));

  const filtersEl = el("div", { class: "filters" });
  const searchInput = el("input", {
    type: "search", class: "search-input",
    placeholder: "Search addons…", autocomplete: "off",
  }) as HTMLInputElement;
  filtersEl.append(searchInput);

  const pillDefs = [
    { label: "All", cls: "all" },
    { label: "OCA", cls: "oca" },
    { label: "Custom", cls: "custom" },
    { label: "Third-party", cls: "third-party" },
  ];
  const pillBtns = pillDefs.map(({ label, cls }) => {
    const count = cls === "all" ? addons.length : (byClass[cls] || 0);
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
      el("th", { class: "sortable", "data-sort": "technical_name" }, "Addon"),
      el("th", { class: "sortable", "data-sort": "classification" }, "Type"),
      el("th", { class: "sortable", "data-sort": "version" }, "Version"),
      el("th", { class: "muted sortable", "data-sort": "submodule" }, "Submodule"),
      el("th", { class: "num sortable", "data-sort": "_locTotal" }, "LoC"),
      el("th", {}, "Breakdown"),
      el("th", { class: "num muted", "data-sort": "loc_pct" }, "%"),
    ]),
  ]);
  for (const th of thead.querySelectorAll<HTMLElement>("th[data-sort]")) {
    th.addEventListener("click", () => {
      const key = th.dataset.sort!;
      state.sortDir = state.sortKey === key && state.sortDir === "desc" ? "asc" : "desc";
      state.sortKey = key;
      renderTable();
    });
  }

  const tbody = el("tbody", {});
  const emptyState = el("div", { class: "empty-state" }, "No addons match.");
  (emptyState as HTMLElement).style.display = "none";
  root.append(tableWrap(el("table", {}, [thead, tbody])));
  root.append(emptyState);

  function renderTable() {
    tbody.innerHTML = "";
    const query = state.search.toLowerCase();
    const filtered = addons.filter((a) => {
      if (state.classification !== "all" && (a.classification || "unknown") !== state.classification) return false;
      if (!query) return true;
      return (
        a.technical_name.toLowerCase().includes(query) ||
        ((a.summary ?? "") as string).toLowerCase().includes(query) ||
        ((a.author ?? "") as string).toLowerCase().includes(query) ||
        ((a.submodule ?? "") as string).toLowerCase().includes(query)
      );
    });

    const sorted = [...filtered].sort((a, b) => {
      const av: unknown = (a as Record<string, unknown>)[state.sortKey];
      const bv: unknown = (b as Record<string, unknown>)[state.sortKey];
      if (typeof av === "number" && typeof bv === "number")
        return state.sortDir === "asc" ? av - bv : bv - av;
      return state.sortDir === "asc"
        ? String(av ?? "").localeCompare(String(bv ?? ""))
        : String(bv ?? "").localeCompare(String(av ?? ""));
    });

    (emptyState as HTMLElement).style.display = sorted.length === 0 ? "" : "none";

    // Read colors each render (theme-safe)
    const LCOLORS: Record<string, string> = {
      python: readColor("--loc-python"),
      xml: readColor("--loc-xml"),
      javascript: readColor("--loc-javascript"),
      docs: readColor("--loc-docs"),
    };

    for (const a of sorted) {
      const bar = el("div", { class: "loc-bar" });
      for (const k of LOC_KEYS) {
        const v = a.loc?.[k] ?? 0;
        if (!a._locTotal || !v) continue;
        const seg = el("div", {
          class: "loc-bar-segment",
          title: `${k}: ${fmt(v)} (${((v / a._locTotal) * 100).toFixed(1)}%)`,
        });
        (seg as HTMLElement).style.width = `${(v / a._locTotal) * 100}%`;
        (seg as HTMLElement).style.background = LCOLORS[k] ?? "#999";
        bar.append(seg);
      }

      const nameCell = el("td", {}, [
        el("div", { class: "addon-name" }, a.technical_name),
        a.summary ? el("div", { class: "addon-summary" }, a.summary as string) : null,
      ]);

      tbody.append(el("tr", {}, [
        nameCell,
        el("td", {}, badge(a.classification)),
        el("td", { class: "muted" }, a.version ?? "—"),
        el("td", { class: "muted" }, a.submodule ?? "—"),
        numCell(a._locTotal || null),
        el("td", {}, bar),
        el("td", { class: "num muted" }, `${a.loc_pct ?? 0}%`),
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
