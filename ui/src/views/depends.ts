import * as d3 from "d3";
import type { Payload } from "../types";
import type { Source } from "../source";
import { el } from "../dom";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Addon {
  name: string;
  origin?: string;
  location?: string;
  depends: string[];
  missing_deps: string[];
  depth?: number;
  reverse_depth?: number;
  ancestors_count?: number;
  descendants_count?: number;
}

interface DependsStats {
  total?: number;
  roots?: string[];
  leaves_count?: number;
  unresolved?: string[];
}

interface DependsPayload {
  addons: Addon[];
  stats?: DependsStats;
  warnings?: string[];
  metadata: Payload["metadata"];
}

interface GNode extends d3.SimulationNodeDatum {
  id: string;
  origin: string;
  data: Addon;
}

interface GLink extends d3.SimulationLinkDatum<GNode> {
  source: GNode | string;
  target: GNode | string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const NODE_RADIUS_BASE = 4;
const LAYER_HEIGHT = 80;
const NODE_HSPACING = 110;
const LABELS_VISIBLE_AT = 1.2;
const ORIGIN_KEYS = ["custom", "oca", "third-party", "odoo", "enterprise", "unknown"] as const;

// ---------------------------------------------------------------------------
// viewDepends
// ---------------------------------------------------------------------------

export function viewDepends(root: HTMLElement, payload: Payload, _source: Source): void {
  const p = payload as unknown as DependsPayload;
  const ADDONS: Addon[] = p.addons ?? [];
  const STATS: DependsStats = p.stats ?? {};
  const warnings = p.warnings ?? [];

  // Switch #app to full-screen layout
  root.classList.add("depends-full");

  // Clean up on next route change (hashchange fires before render clears root)
  const cleanup = () => { root.classList.remove("depends-full"); };
  window.addEventListener("hashchange", cleanup, { once: true });

  // Origin colors from CSS variables
  const cs = getComputedStyle(document.documentElement);
  const ORIGIN_COLORS: Record<string, string> = {};
  for (const o of ORIGIN_KEYS) {
    const v = cs.getPropertyValue(`--origin-${o}`).trim();
    ORIGIN_COLORS[o] = v || "#9aa1b4";
  }
  ORIGIN_COLORS["third-party"] = cs.getPropertyValue("--origin-third_party").trim() || "#b07449";

  const BY_NAME = new Map(ADDONS.map((a) => [a.name, a]));
  const ALL_ORIGINS = [...new Set(ADDONS.map((a) => a.origin ?? "unknown"))].sort();

  const MAX_RDEPTH = d3.max(ADDONS, (a) => a.reverse_depth ?? 0) ?? 0;
  const DEFAULT_RDEPTH = Math.min(MAX_RDEPTH, 3);

  const state = {
    enabledOrigins: new Set(ALL_ORIGINS),
    search: "",
    focus: null as string | null,
    focusSet: null as Set<string> | null,
    layout: "hierarchical" as "hierarchical" | "force",
    maxReverseDepth: DEFAULT_RDEPTH,
  };

  // Adjacency
  const forward = new Map<string, Set<string>>();
  const reverse = new Map<string, Set<string>>();
  for (const a of ADDONS) {
    forward.set(a.name, new Set(a.depends.filter((d) => BY_NAME.has(d))));
    for (const d of a.depends) {
      if (!BY_NAME.has(d)) continue;
      if (!reverse.has(d)) reverse.set(d, new Set());
      reverse.get(d)!.add(a.name);
    }
  }

  function transitiveSet(start: string, graph: Map<string, Set<string>>): Set<string> {
    const seen = new Set([start]);
    const stack = [start];
    while (stack.length) {
      for (const nxt of graph.get(stack.pop()!)  ?? []) {
        if (!seen.has(nxt)) { seen.add(nxt); stack.push(nxt); }
      }
    }
    return seen;
  }

  // D3 graph data
  const nodes: GNode[] = ADDONS.map((a) => ({
    id: a.name,
    origin: a.origin ?? "unknown",
    data: a,
  }));
  const links: GLink[] = [];
  for (const a of ADDONS) {
    for (const dep of a.depends) {
      if (BY_NAME.has(dep)) links.push({ source: a.name, target: dep });
    }
  }

  // ── Build layout ────────────────────────────────────────────────────────

  // Left sidebar
  const sidebar = el("aside", { class: "dep-sidebar" });

  if (warnings.length) {
    const wc = el("div", {});
    warnings.forEach((w) => wc.appendChild(el("div", { class: "warning-banner" }, w)));
    sidebar.appendChild(wc);
  }

  // Search
  const searchSection = el("div", { class: "dep-section" });
  searchSection.appendChild(el("div", { class: "dep-section-title" }, "Search"));
  const searchInput = el("input", {
    type: "search", placeholder: "Filter by module name…", class: "dep-search",
  }) as HTMLInputElement;
  searchSection.appendChild(searchInput);
  sidebar.appendChild(searchSection);

  // Depth slider
  const depthSection = el("div", { class: "dep-section" });
  depthSection.appendChild(el("div", { class: "dep-section-title" }, "Depth from your modules"));
  const sliderWrap = el("div", { class: "dep-slider-wrap" });
  const depthSlider = el("input", { type: "range", min: "0", max: String(MAX_RDEPTH), value: String(DEFAULT_RDEPTH), step: "1" }) as HTMLInputElement;
  const depthValueEl = el("span", { class: "dep-slider-value" }, String(DEFAULT_RDEPTH));
  sliderWrap.append(depthSlider, depthValueEl);
  const depthHintEl = el("div", { class: "dep-slider-hint" });
  depthSection.append(sliderWrap, depthHintEl);
  sidebar.appendChild(depthSection);

  // Origin filters
  const originSection = el("div", { class: "dep-section" });
  originSection.appendChild(el("div", { class: "dep-section-title" }, "By origin"));
  const originList = el("div", { class: "dep-checkbox-list" });
  const originCbs: Map<string, HTMLInputElement> = new Map();
  for (const origin of ALL_ORIGINS) {
    const count = ADDONS.filter((a) => (a.origin ?? "unknown") === origin).length;
    const cb = el("input", { type: "checkbox", checked: "true", "data-origin": origin }) as HTMLInputElement;
    originCbs.set(origin, cb);
    const color = ORIGIN_COLORS[origin] ?? "#9aa1b4";
    const label = el("label", { class: "dep-origin-label" }, [
      cb,
      el("span", { class: "dep-swatch", style: `background:${color}` }),
      el("span", {}, origin),
      el("span", { class: "dep-origin-count" }, count),
    ]);
    originList.appendChild(label);
  }
  originSection.appendChild(originList);
  sidebar.appendChild(originSection);

  // Layout buttons
  const layoutSection = el("div", { class: "dep-section" });
  layoutSection.appendChild(el("div", { class: "dep-section-title" }, "Layout"));
  const btnHier  = el("button", { class: "dep-btn dep-btn-primary" }, "Hierarchical") as HTMLButtonElement;
  const btnForce = el("button", { class: "dep-btn" }, "Force-directed") as HTMLButtonElement;
  layoutSection.append(btnHier, btnForce);
  sidebar.appendChild(layoutSection);

  // Quick toggles
  const toggleSection = el("div", { class: "dep-section" });
  toggleSection.appendChild(el("div", { class: "dep-section-title" }, "Quick toggles"));
  const btnHideOdoo = el("button", { class: "dep-btn" }, "Hide Odoo + Enterprise") as HTMLButtonElement;
  const btnShowAll  = el("button", { class: "dep-btn" }, "Show all") as HTMLButtonElement;
  toggleSection.append(btnHideOdoo, btnShowAll);
  sidebar.appendChild(toggleSection);

  // Stats
  const statsSection = el("div", { class: "dep-section" });
  statsSection.appendChild(el("div", { class: "dep-section-title" }, "Stats"));
  const statsGrid = el("div", { class: "dep-stats-grid" });
  [
    ["Modules", STATS.total ?? ADDONS.length],
    ["Roots",   (STATS.roots ?? []).length],
    ["Leaves",  STATS.leaves_count ?? 0],
    ["Unresolved", (STATS.unresolved ?? []).length],
  ].forEach(([label, value]) => {
    statsGrid.appendChild(el("div", { class: "dep-stat" }, [
      el("div", { class: "dep-stat-value" }, String(value)),
      el("div", { class: "dep-stat-label" }, String(label)),
    ]));
  });
  statsSection.appendChild(statsGrid);
  sidebar.appendChild(statsSection);

  // Legend
  const legendSection = el("div", { class: "dep-section" });
  legendSection.appendChild(el("div", { class: "dep-section-title" }, "Legend"));
  const legendEl = el("div", { class: "dep-legend" });
  for (const origin of ALL_ORIGINS) {
    const color = ORIGIN_COLORS[origin] ?? "#9aa1b4";
    legendEl.appendChild(el("div", { class: "dep-legend-item" }, [
      el("span", { class: "dep-legend-swatch", style: `background:${color}` }),
      el("span", {}, origin),
    ]));
  }
  legendSection.appendChild(legendEl);
  sidebar.appendChild(legendSection);

  // ── Center: SVG graph ───────────────────────────────────────────────────
  const graphCenter = el("div", { class: "dep-graph" });

  // Floating controls
  const floatControls = el("div", { class: "dep-float-controls" });
  const btnZoomIn  = el("button", { title: "Zoom in" }, "+") as HTMLButtonElement;
  const btnZoomOut = el("button", { title: "Zoom out" }, "−") as HTMLButtonElement;
  const btnZoomFit = el("button", { title: "Fit to screen" }, "⊡") as HTMLButtonElement;
  const btnReset   = el("button", { title: "Restart layout" }, "↻") as HTMLButtonElement;
  floatControls.append(btnZoomIn, btnZoomOut, btnZoomFit, btnReset);
  graphCenter.appendChild(floatControls);

  // Focus banner
  const focusBanner = el("div", { class: "dep-focus-banner" });
  const focusNameEl = el("strong", {});
  const focusClear  = el("button", {}, "×") as HTMLButtonElement;
  focusBanner.appendChild(el("span", {}, ["Focus: ", focusNameEl]));
  focusBanner.appendChild(focusClear);
  graphCenter.appendChild(focusBanner);

  const svgEl = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svgEl.id = "dep-graph-svg";
  graphCenter.appendChild(svgEl);

  // ── Right details panel ─────────────────────────────────────────────────
  const detailsPanel = el("aside", { class: "dep-details" });
  detailsPanel.appendChild(el("div", { class: "dep-details-empty" }, "Click a node to see details"));

  // ── Mount layout ────────────────────────────────────────────────────────
  root.append(sidebar, graphCenter, detailsPanel);

  // ── D3 setup ────────────────────────────────────────────────────────────
  const svg = d3.select<SVGSVGElement, unknown>(svgEl);
  const width = () => svgEl.clientWidth;
  const height = () => svgEl.clientHeight;

  const g = svg.append("g");

  const zoom = d3.zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.05, 6])
    .on("zoom", (e: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
      g.attr("transform", e.transform.toString());
      svgEl.classList.toggle("dep-labels-visible", e.transform.k >= LABELS_VISIBLE_AT);
    });
  svg.call(zoom);

  svg.on("click", () => { clearFocus(); renderDetails(null); nodeSel.classed("selected", false); });

  function nodeRadius(a: Addon) {
    return NODE_RADIUS_BASE + Math.sqrt(a.descendants_count ?? 0) * 2;
  }

  // Links
  const linkSel = g.append("g").attr("class", "dep-links")
    .selectAll<SVGLineElement, GLink>("line")
    .data(links).join("line").attr("class", "dep-link");

  // Nodes
  const nodeSel = g.append("g").attr("class", "dep-nodes")
    .selectAll<SVGGElement, GNode>("g.dep-node")
    .data(nodes).join("g")
    .attr("class", "dep-node")
    .call(
      d3.drag<SVGGElement, GNode>()
        .on("start", (event: d3.D3DragEvent<SVGGElement, GNode, GNode>, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on("drag", (event: d3.D3DragEvent<SVGGElement, GNode, GNode>, d) => {
          d.fx = event.x; d.fy = event.y;
        })
        .on("end", (event: d3.D3DragEvent<SVGGElement, GNode, GNode>, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        })
    )
    .on("click", (event: MouseEvent, d: GNode) => {
      event.stopPropagation();
      selectNode(d.id);
    });

  nodeSel.append("circle")
    .attr("r", (d) => nodeRadius(d.data))
    .attr("fill", (d) => ORIGIN_COLORS[d.origin] ?? ORIGIN_COLORS["unknown"]);

  nodeSel.append("text")
    .attr("dy", (d) => nodeRadius(d.data) + 11)
    .text((d) => d.id);

  // Force simulation
  const simulation = d3.forceSimulation<GNode, GLink>(nodes)
    .force("link", d3.forceLink<GNode, GLink>(links).id((d) => d.id).distance(60).strength(0.3))
    .force("charge", d3.forceManyBody<GNode>().strength(-220))
    .force("center", d3.forceCenter<GNode>(0, 0))
    .force("collide", d3.forceCollide<GNode>().radius((d) => nodeRadius(d.data) + 6))
    .on("tick", () => {
      linkSel
        .attr("x1", (d) => (d.source as GNode).x ?? 0)
        .attr("y1", (d) => (d.source as GNode).y ?? 0)
        .attr("x2", (d) => (d.target as GNode).x ?? 0)
        .attr("y2", (d) => (d.target as GNode).y ?? 0);
      nodeSel.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

  // ── Layout functions ─────────────────────────────────────────────────────

  function visibleNodeIds(): Set<string> {
    const query = state.search.toLowerCase();
    const ids = new Set<string>();
    for (const n of nodes) {
      if (!state.enabledOrigins.has(n.origin)) continue;
      if ((n.data.reverse_depth ?? 0) > state.maxReverseDepth) continue;
      if (query && !n.id.toLowerCase().includes(query)) continue;
      if (state.focusSet && !state.focusSet.has(n.id)) continue;
      ids.add(n.id);
    }
    return ids;
  }

  function applyHierarchicalLayout(): void {
    const visIds = visibleNodeIds();
    const vis = nodes.filter((n) => visIds.has(n.id));
    const byLayer = d3.group(vis, (n) => n.data.reverse_depth ?? 0);

    Array.from(byLayer.entries())
      .sort((a, b) => a[0] - b[0])
      .forEach(([, layer]) => {
        layer.sort(
          (a, b) =>
            (b.data.descendants_count ?? 0) - (a.data.descendants_count ?? 0) ||
            a.id.localeCompare(b.id)
        );
        const layerWidth = (layer.length - 1) * NODE_HSPACING;
        layer.forEach((n, i) => {
          n.x = i * NODE_HSPACING - layerWidth / 2;
          n.y = (n.data.reverse_depth ?? 0) * LAYER_HEIGHT;
          n.fx = n.x;
          n.fy = n.y;
        });
      });

    nodeSel.style("display", (d) => (visIds.has(d.id) ? null : "none"));
    linkSel.style("display", (l) => {
      const sId = (l.source as GNode).id ?? "";
      const tId = (l.target as GNode).id ?? "";
      return visIds.has(sId) && visIds.has(tId) ? null : "none";
    });

    simulation.alpha(0.3).restart();
  }

  function applyForceLayout(): void {
    nodes.forEach((n) => { n.fx = null; n.fy = null; });
    applyForceVisibility();
    simulation.alpha(1).restart();
  }

  function applyForceVisibility(): void {
    const visIds = visibleNodeIds();
    nodeSel.style("display", (d) => (visIds.has(d.id) ? null : "none"));
    linkSel.style("display", (l) => {
      const sId = (l.source as GNode).id ?? "";
      const tId = (l.target as GNode).id ?? "";
      return visIds.has(sId) && visIds.has(tId) ? null : "none";
    });
  }

  function rebuildLayout(): void {
    if (state.layout === "hierarchical") applyHierarchicalLayout();
    else applyForceLayout();
  }

  function fitToContent(): void {
    const visIds = visibleNodeIds();
    const vis = nodes.filter((n) => visIds.has(n.id) && n.x != null && n.y != null);
    if (!vis.length) return;
    const xs = vis.map((n) => n.x!);
    const ys = vis.map((n) => n.y!);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const w = maxX - minX + 120;
    const h = maxY - minY + 120;
    const scale = Math.min(width() / w, height() / h, 1);
    const tx = width() / 2 - (scale * (minX + maxX)) / 2;
    const ty = height() / 2 - (scale * (minY + maxY)) / 2;
    svg.transition().duration(400)
      .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
  }

  // ── Focus / selection ────────────────────────────────────────────────────

  function selectNode(name: string): void {
    const ancestors    = transitiveSet(name, forward);
    const descendants  = transitiveSet(name, reverse);
    const subgraph     = new Set([...ancestors, ...descendants]);
    state.focus    = name;
    state.focusSet = subgraph;

    nodeSel
      .classed("dep-dimmed",       (d) => !subgraph.has(d.id))
      .classed("dep-focus-member", (d) =>  subgraph.has(d.id))
      .classed("selected",         (d) =>  d.id === name);

    linkSel
      .classed("dep-highlighted", (l) => {
        const sId = (l.source as GNode).id ?? "";
        const tId = (l.target as GNode).id ?? "";
        return subgraph.has(sId) && subgraph.has(tId);
      })
      .classed("dep-dimmed", (l) => {
        const sId = (l.source as GNode).id ?? "";
        const tId = (l.target as GNode).id ?? "";
        return !subgraph.has(sId) || !subgraph.has(tId);
      });

    focusBanner.classList.add("active");
    focusNameEl.textContent = `${name} (${subgraph.size} related)`;
    renderDetails(name);
  }

  function clearFocus(): void {
    state.focus = null;
    state.focusSet = null;
    nodeSel.classed("dep-dimmed", false).classed("selected", false).classed("dep-focus-member", false);
    linkSel.classed("dep-highlighted", false).classed("dep-dimmed", false);
    focusBanner.classList.remove("active");
    if (state.layout === "hierarchical") applyHierarchicalLayout();
    else applyForceVisibility();
  }

  // ── Details panel ─────────────────────────────────────────────────────────

  function renderDetails(name: string | null): void {
    detailsPanel.innerHTML = "";
    if (!name) {
      detailsPanel.appendChild(el("div", { class: "dep-details-empty" }, "Click a node to see details"));
      return;
    }
    const a = BY_NAME.get(name);
    if (!a) return;
    const color = ORIGIN_COLORS[a.origin ?? "unknown"] ?? "#9aa1b4";

    detailsPanel.appendChild(el("h2", {}, a.name));
    const badgeEl = el("span", { class: "dep-origin-badge", style: `background:${color}` }, a.origin ?? "unknown");
    detailsPanel.appendChild(badgeEl);

    const infoRows: [string, string | number][] = [
      ["Location",           a.location ?? "—"],
      ["Depth (from base)",  a.depth ?? "—"],
      ["Depth (from leaves)", a.reverse_depth ?? "—"],
      ["Ancestors",          a.ancestors_count ?? "—"],
      ["Descendants",        a.descendants_count ?? "—"],
      ["Direct deps",        a.depends.length],
      ["Missing deps",       a.missing_deps.length],
    ];
    for (const [label, value] of infoRows) {
      detailsPanel.appendChild(el("div", { class: "dep-detail-row" }, [
        el("span", { class: "dep-detail-label" }, String(label)),
        el("span", { class: "dep-detail-value" }, String(value)),
      ]));
    }

    if (a.depends.length) {
      const wrap = el("div", { class: "dep-deps-list" });
      wrap.appendChild(el("h3", {}, "Depends on"));
      for (const d of a.depends) {
        const missing = a.missing_deps.includes(d);
        const item = el("a", { class: "dep-dep" + (missing ? " dep-missing" : "") },
          d + (missing ? " (missing)" : ""));
        if (!missing) {
          item.addEventListener("click", (e) => { e.preventDefault(); selectNode(d); });
        }
        wrap.appendChild(item);
      }
      detailsPanel.appendChild(wrap);
    }

    const reverseDeps = [...(reverse.get(a.name) ?? [])].sort();
    if (reverseDeps.length) {
      const wrap = el("div", { class: "dep-deps-list" });
      wrap.appendChild(el("h3", {}, "Required by"));
      for (const d of reverseDeps) {
        const item = el("a", { class: "dep-dep" }, d);
        item.addEventListener("click", (e) => { e.preventDefault(); selectNode(d); });
        wrap.appendChild(item);
      }
      detailsPanel.appendChild(wrap);
    }
  }

  // ── Sidebar event handlers ───────────────────────────────────────────────

  searchInput.addEventListener("input", () => {
    state.search = searchInput.value;
    rebuildLayout();
  });

  for (const [origin, cb] of originCbs) {
    cb.addEventListener("change", () => {
      if (cb.checked) state.enabledOrigins.add(origin);
      else state.enabledOrigins.delete(origin);
      rebuildLayout();
    });
  }

  depthSlider.addEventListener("input", () => {
    state.maxReverseDepth = Number(depthSlider.value);
    updateDepthHint();
    rebuildLayout();
  });

  function updateDepthHint(): void {
    const visible = ADDONS.filter((a) => (a.reverse_depth ?? 0) <= state.maxReverseDepth).length;
    depthValueEl.textContent = String(state.maxReverseDepth);
    depthHintEl.textContent = `${visible} of ${ADDONS.length} modules (${state.maxReverseDepth}/${MAX_RDEPTH} levels)`;
  }
  updateDepthHint();

  btnHier.addEventListener("click", () => {
    state.layout = "hierarchical";
    btnHier.classList.add("dep-btn-primary");
    btnForce.classList.remove("dep-btn-primary");
    rebuildLayout();
  });
  btnForce.addEventListener("click", () => {
    state.layout = "force";
    btnForce.classList.add("dep-btn-primary");
    btnHier.classList.remove("dep-btn-primary");
    rebuildLayout();
  });

  btnHideOdoo.addEventListener("click", () => {
    for (const o of ["odoo", "enterprise"]) {
      state.enabledOrigins.delete(o);
      const cb = originCbs.get(o);
      if (cb) cb.checked = false;
    }
    rebuildLayout();
  });
  btnShowAll.addEventListener("click", () => {
    for (const o of ALL_ORIGINS) {
      state.enabledOrigins.add(o);
      const cb = originCbs.get(o);
      if (cb) cb.checked = true;
    }
    rebuildLayout();
  });

  focusClear.addEventListener("click", (e) => {
    e.stopPropagation();
    clearFocus();
    renderDetails(null);
  });

  btnZoomIn.addEventListener("click",  () => svg.transition().call(zoom.scaleBy, 1.4));
  btnZoomOut.addEventListener("click", () => svg.transition().call(zoom.scaleBy, 1 / 1.4));
  btnZoomFit.addEventListener("click", fitToContent);
  btnReset.addEventListener("click",   () => { simulation.alpha(1).restart(); });

  // ── Initial render ───────────────────────────────────────────────────────
  requestAnimationFrame(() => {
    rebuildLayout();
    setTimeout(fitToContent, 120);
  });
}
