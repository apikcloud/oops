import * as d3 from "d3";
import { el, fmt } from "../dom";

// ---------------------------------------------------------------------------
// Types (structural match with analyze.ts DomainProfile — no shared import
// needed; TypeScript checks structural compatibility at call site).
// ---------------------------------------------------------------------------

export interface DomainIndicators {
  models_extended: number; fields_new: number; fields_override: number;
  methods_new: number; methods_inherited: number; methods_override: number;
  views_primary: number; views_extended: number; loc: number;
}

export interface DomainEntry {
  domain: string; label: string; weight_raw: number;
  score_proportional: number; score_relative: number;
  indicators: DomainIndicators;
}

export interface DomainProfile {
  domains: DomainEntry[];
  pillars: DomainEntry[];
  custom_models: number;
}

type Mode = "proportional" | "relative";

// ---------------------------------------------------------------------------
// Indicator labels (mirrors METRIC_LABELS / LOC_LABELS precedent)
// ---------------------------------------------------------------------------

const INDICATOR_LABELS: Record<keyof DomainIndicators, string> = {
  models_extended: "Models extended",
  fields_new: "New fields",
  fields_override: "Overridden fields",
  methods_new: "New methods",
  methods_inherited: "Inherited methods",
  methods_override: "Overridden methods",
  views_primary: "Primary views",
  views_extended: "Extended views",
  loc: "Method LoC",
};
const INDICATOR_ORDER = Object.keys(INDICATOR_LABELS) as (keyof DomainIndicators)[];

const scoreOf = (e: DomainEntry, mode: Mode): number =>
  mode === "proportional" ? e.score_proportional : e.score_relative;

function readColor(v: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(v).trim() || "#505ba6";
}

// ---------------------------------------------------------------------------
// Detail panel (shared by radar axes, bar rows, and pillar chips)
// ---------------------------------------------------------------------------

interface DetailPanel {
  node: HTMLElement;
  show(entry: DomainEntry, mode: Mode): void;
  reset(): void;
}

function makeDetailPanel(): DetailPanel {
  const node = el("div", { class: "dp-detail" });

  const reset = (): void => {
    node.innerHTML = "";
    node.appendChild(el("div", { class: "dp-detail-empty" }, "Hover an axis for indicators"));
  };

  const show = (entry: DomainEntry, mode: Mode): void => {
    node.innerHTML = "";
    node.appendChild(el("div", { class: "dp-detail-title" }, [
      entry.label,
      el("span", { class: "dp-detail-score" }, `${(scoreOf(entry, mode) * 100).toFixed(0)}%`),
    ]));
    const grid = el("div", { class: "dp-indicators" });
    for (const k of INDICATOR_ORDER) {
      const v = entry.indicators[k] ?? 0;
      grid.appendChild(el("div", { class: "dp-indicator" + (v ? "" : " zero") }, [
        el("span", { class: "dp-ind-label" }, INDICATOR_LABELS[k]),
        el("span", { class: "dp-ind-value" }, fmt(v)),
      ]));
    }
    node.appendChild(grid);
  };

  reset();
  return { node, show, reset };
}

// ---------------------------------------------------------------------------
// Radar chart (≥3 domains)
// ---------------------------------------------------------------------------

const SIZE = 240, R = 78, CX = 0, CY = 0;
const LEVELS = [0.25, 0.5, 0.75, 1];

function angleFor(i: number, n: number): number {
  return (i / n) * 2 * Math.PI - Math.PI / 2;
}
function point(angle: number, radius: number): [number, number] {
  return [CX + radius * Math.cos(angle), CY + radius * Math.sin(angle)];
}

interface VertDatum { entry: DomainEntry; x: number; y: number }

function renderRadar(
  container: HTMLElement,
  domains: DomainEntry[],
  mode: () => Mode,
  detail: DetailPanel,
): (newMode: Mode) => void {
  const stroke = readColor("--border");
  const accent = readColor("--accent");
  const muted  = readColor("--text-muted");
  const n = domains.length;

  const svg = d3.select(container).append("svg")
    .attr("viewBox", `${-SIZE / 2} ${-SIZE / 2} ${SIZE} ${SIZE}`)
    .attr("width", "100%")
    .style("display", "block");

  // Grid rings
  for (const lvl of LEVELS) {
    svg.append("polygon")
      .attr("class", "dp-grid")
      .attr("points", domains.map((_, i) => point(angleFor(i, n), R * lvl).join(",")).join(" "))
      .attr("fill", "none").attr("stroke", stroke);
  }

  // Spokes + axis labels
  let pinnedEntry: DomainEntry | null = null;

  const pinEntry = (entry: DomainEntry): void => {
    if (pinnedEntry === entry) { pinnedEntry = null; detail.reset(); }
    else { pinnedEntry = entry; detail.show(entry, mode()); }
  };
  const onLeave = (): void => { if (pinnedEntry == null) detail.reset(); };

  domains.forEach((d, i) => {
    const a = angleFor(i, n);
    const [ex, ey] = point(a, R);
    svg.append("line").attr("class", "dp-spoke")
      .attr("x1", CX).attr("y1", CY).attr("x2", ex).attr("y2", ey)
      .attr("stroke", stroke);

    const [lx, ly] = point(a, R + 16);
    const anchor = Math.abs(Math.cos(a)) < 0.3 ? "middle" : (Math.cos(a) > 0 ? "start" : "end");
    svg.append("text").attr("class", "dp-axis-label")
      .attr("x", lx).attr("y", ly)
      .attr("text-anchor", anchor).attr("dy", "0.32em")
      .style("fill", muted).style("font-size", ".62rem")
      .text(d.label)
      .on("mouseenter", () => detail.show(d, mode()))
      .on("mouseleave", () => onLeave())
      .on("click", () => pinEntry(d));
  });

  // Data polygon
  const poly = svg.append("polygon").attr("class", "dp-poly")
    .attr("fill", accent).attr("fill-opacity", 0.18)
    .attr("stroke", accent).attr("stroke-width", 2);

  // Vertex group (redrawn on mode change)
  const vertsG = svg.append("g");

  function draw(m: Mode): void {
    const vdata: VertDatum[] = domains.map((d, i) => {
      const [x, y] = point(angleFor(i, n), R * scoreOf(d, m));
      return { entry: d, x, y };
    });

    poly.attr("points", vdata.map((v) => `${v.x},${v.y}`).join(" "));

    const sel = vertsG
      .selectAll<SVGCircleElement, VertDatum>("circle.dp-vertex")
      .data(vdata);

    sel.join(
      (enter) => enter.append("circle").attr("class", "dp-vertex")
        .attr("r", 3).attr("fill", accent)
        .on("mouseenter", (_e, v) => detail.show(v.entry, mode()))
        .on("mouseleave", () => onLeave())
        .on("click", (_e, v) => pinEntry(v.entry)),
      (update) => update,
    )
      .attr("cx", (v) => v.x)
      .attr("cy", (v) => v.y);
  }

  draw(mode());
  return draw;
}

// ---------------------------------------------------------------------------
// Bar fallback (1–2 domains)
// ---------------------------------------------------------------------------

function renderBars(
  container: HTMLElement,
  domains: DomainEntry[],
  mode: () => Mode,
  detail: DetailPanel,
): (newMode: Mode) => void {
  const accent = readColor("--accent");
  const list = el("div", { class: "dp-bars" });

  const rows = domains.map((d) => {
    const fill = el("div", { class: "dp-bar-fill" });
    (fill as HTMLElement).style.background = accent;
    const track = el("div", { class: "dp-bar-track" }, fill);
    const row = el("div", { class: "dp-bar-row" }, [
      el("span", { class: "dp-bar-label" }, d.label),
      track,
    ]);
    row.addEventListener("mouseenter", () => detail.show(d, mode()));
    list.appendChild(row);
    return { d, fill: fill as HTMLElement };
  });

  container.appendChild(list);

  const draw = (m: Mode): void => {
    rows.forEach((r) => { r.fill.style.width = `${scoreOf(r.d, m) * 100}%`; });
  };
  draw(mode());
  return draw;
}

// ---------------------------------------------------------------------------
// Top-level assembly
// ---------------------------------------------------------------------------

export function domainProfile(profile: DomainProfile): HTMLElement | null {
  const domains = profile.domains ?? [];
  const pillars = profile.pillars ?? [];
  if (!domains.length && !pillars.length) return null;

  let mode: Mode = "proportional";
  const card = el("div", { class: "chart-card dp-card" });
  card.appendChild(el("h3", {}, "Domain Profile"));

  // Toggle (only meaningful with ≥1 domain)
  let redraw: (m: Mode) => void = () => {};
  if (domains.length) {
    const btnDist = el("button", { class: "filter-btn active" }, "Distribution") as HTMLButtonElement;
    const btnInt  = el("button", { class: "filter-btn" }, "Intensity") as HTMLButtonElement;
    const setMode = (m: Mode, on: HTMLButtonElement, off: HTMLButtonElement): void => {
      mode = m;
      on.classList.add("active");
      off.classList.remove("active");
      redraw(m);
    };
    btnDist.addEventListener("click", () => setMode("proportional", btnDist, btnInt));
    btnInt.addEventListener("click",  () => setMode("relative",     btnInt,  btnDist));
    card.appendChild(el("div", { class: "dp-toggle filters" }, [btnDist, btnInt]));
  }

  const row    = el("div", { class: "dp-row" });
  const chart  = el("div", { class: "chart-container dp-chart" });
  const detail = makeDetailPanel();
  row.appendChild(chart);
  row.appendChild(detail.node);
  card.appendChild(row);

  if (domains.length >= 3)     redraw = renderRadar(chart, domains, () => mode, detail);
  else if (domains.length > 0) redraw = renderBars(chart, domains,  () => mode, detail);

  // Pillar chips — hover fills the detail panel using relative scores
  if (pillars.length) {
    const chips = el("div", { class: "dp-pillars chip-list" });
    for (const p of pillars) {
      const pct  = (p.score_relative * 100).toFixed(0);
      const chip = el("span", { class: "chip dp-pillar" }, `${p.label} ${pct}%`);
      chip.addEventListener("mouseenter", () => detail.show(p, "relative"));
      chips.appendChild(chip);
    }
    card.appendChild(el("div", { class: "dp-pillars-wrap" }, [
      el("div", { class: "dp-subhead" }, "Pillars"),
      chips,
    ]));
  }

  if (profile.custom_models > 0) {
    card.appendChild(el("div", { class: "dp-custom muted" },
      `Custom models (unattributed): ${profile.custom_models}`));
  }

  return card;
}
