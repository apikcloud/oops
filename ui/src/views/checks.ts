import type { Payload } from "../types";
import type { Source } from "../source";
import { el, numCell, tableWrap, renderMetadataBar } from "../dom";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CheckItem {
  label: string;
  status: "passed" | "failed" | "skipped" | string;
  items?: string[];
}

interface CheckSection {
  title: string;
  data?: CheckItem[];
  warnings?: string[];
  error?: string;
}

// Flat payload (`project check`, `requirements check`)
interface FlatChecksPayload {
  data: CheckItem[];
  warnings?: string[];
  metadata: Payload["metadata"];
}

// Grouped payload (`checks`)
interface GroupedChecksPayload {
  sections: CheckSection[];
  metadata: Payload["metadata"];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusBadgeCls(status: string): string {
  if (status === "passed")  return "custom";
  if (status === "failed")  return "third-party";
  if (status === "skipped") return "oca";
  return "unknown";
}

function buildCheckTable(data: CheckItem[]): HTMLElement {
  const thead = el("thead", {}, [el("tr", {}, [
    el("th", {}, "Check"),
    el("th", {}, "Status"),
    el("th", {}, "Items"),
  ])]);
  const tbody = el("tbody", {});
  for (const c of data) {
    const items = c.items ?? [];
    tbody.appendChild(el("tr", {}, [
      el("td", {}, c.label),
      el("td", {}, el("span", { class: `badge badge-${statusBadgeCls(c.status)}` }, c.status)),
      el("td", { class: "chk-items" }, items.join(", ") || "—"),
    ]));
  }
  return tableWrap(el("table", {}, [thead, tbody]));
}

function summaryCards(counts: { total: number; passed: number; failed: number; skipped: number }): HTMLElement {
  const grid = el("div", { class: "chk-summary" });
  [
    { label: "Total",   value: counts.total,   cls: "" },
    { label: "Passed",  value: counts.passed,  cls: "passed" },
    { label: "Failed",  value: counts.failed,  cls: "failed" },
    { label: "Skipped", value: counts.skipped, cls: "skipped" },
  ].forEach(({ label, value, cls }) => {
    grid.appendChild(el("div", { class: `chk-card ${cls}`.trim() }, [
      el("div", { class: "chk-card-value" }, String(value)),
      el("div", { class: "chk-card-label" }, label),
    ]));
  });
  return grid;
}

// ---------------------------------------------------------------------------
// viewChecks — handles both flat and grouped payloads
// ---------------------------------------------------------------------------

export function viewChecks(root: HTMLElement, payload: Payload, _source: Source): void {
  const cmd = payload.metadata?.command ?? "";
  const metaBar = renderMetadataBar(payload.metadata);
  if (metaBar) root.appendChild(metaBar);

  if (cmd === "checks") {
    _renderGrouped(root, payload as unknown as GroupedChecksPayload);
  } else {
    _renderFlat(root, payload as unknown as FlatChecksPayload);
  }
}

// ── Flat: project check / requirements check ─────────────────────────────

function _renderFlat(root: HTMLElement, p: FlatChecksPayload): void {
  const data     = p.data     ?? [];
  const warnings = p.warnings ?? [];

  root.appendChild(el("div", { class: "page-header" }, [el("h1", {}, "Checks")]));

  if (warnings.length) {
    root.appendChild(el("div", { class: "warnings" }, [
      el("ul", {}, warnings.map((w) => el("li", {}, w))),
    ]));
  }

  const counts = { total: data.length, passed: 0, failed: 0, skipped: 0 };
  for (const c of data) {
    if (c.status === "passed")  counts.passed++;
    else if (c.status === "failed")  counts.failed++;
    else if (c.status === "skipped") counts.skipped++;
  }
  root.appendChild(summaryCards(counts));
  if (data.length) root.appendChild(buildCheckTable(data));
  else root.appendChild(el("div", { class: "empty-state" }, "No checks run."));
}

// ── Grouped: checks ──────────────────────────────────────────────────────

function _renderGrouped(root: HTMLElement, p: GroupedChecksPayload): void {
  const sections = p.sections ?? [];

  root.appendChild(el("div", { class: "page-header" }, [
    el("h1", {}, "All Checks"),
    el("p", { class: "page-subtitle" }, `${sections.length} section${sections.length !== 1 ? "s" : ""}`),
  ]));

  const counts = { total: 0, passed: 0, failed: 0, skipped: 0 };
  for (const s of sections) {
    for (const c of s.data ?? []) {
      counts.total++;
      if (c.status === "passed")  counts.passed++;
      else if (c.status === "failed")  counts.failed++;
      else if (c.status === "skipped") counts.skipped++;
    }
  }
  root.appendChild(summaryCards(counts));

  for (const s of sections) {
    root.appendChild(el("h2", {}, s.title));

    if (s.error) {
      root.appendChild(el("div", { class: "warnings" }, [
        el("div", { style: "font-weight:600;margin-bottom:0.25rem" }, "Not run"),
        el("div", {}, s.error),
      ]));
      continue;
    }

    if (s.warnings?.length) {
      root.appendChild(el("div", { class: "warnings" }, [
        el("ul", {}, s.warnings.map((w) => el("li", {}, w))),
      ]));
    }

    const data = s.data ?? [];
    if (data.length) root.appendChild(buildCheckTable(data));
    else root.appendChild(el("div", { class: "empty-state" }, "No checks in this section."));
  }
}
