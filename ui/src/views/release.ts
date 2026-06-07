import type { Payload } from "../types";
import type { Source } from "../source";
import { el, renderMetadataBar } from "../dom";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Changelog { entries?: Record<string, string[]>; }

interface Release {
  name: string;
  release_type?: string;
  date?: string;
  author?: string;
  commits?: number;
  changelog?: Changelog;
}

interface ReleaseStats {
  total?: number;
  commits?: number;
  types?: { major?: number; minor?: number; fix?: number };
  first_release?: string;
  last_release?: string;
  delta?: number;
}

interface ReleasePayload {
  releases: Release[];
  stats?: ReleaseStats;
  warnings?: string[];
  metadata: Payload["metadata"];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function formatDate(iso?: string): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${MONTHS[(+m) - 1] ?? "?"} ${+d}, ${y}`;
}

function yearOf(iso?: string): string { return iso ? iso.slice(0, 4) : "—"; }

function renderInlineCode(s: string): string {
  return s.replace(/`([^`]+)`/g, (_, code) => `<code>${code.replace(/</g, "&lt;")}</code>`);
}

function changelogToText(cl?: Changelog): string {
  if (!cl?.entries) return "";
  return Object.values(cl.entries).flat().join(" ");
}

// ---------------------------------------------------------------------------

const SECTION_ORDER = ["Added", "Changed", "Fixed", "Removed", "Deprecated", "Security"];

export function viewRelease(root: HTMLElement, payload: Payload, _source: Source): void {
  const p = payload as unknown as ReleasePayload;
  const RELEASES = p.releases ?? [];
  const STATS    = p.stats   ?? {};
  const warnings = p.warnings ?? [];

  // Metadata bar
  const metaBar = renderMetadataBar(p.metadata);
  if (metaBar) root.appendChild(metaBar);

  // Page header
  const types    = STATS.types ?? {};
  const subtitle = RELEASES.length
    ? `${RELEASES.length} releases from ${formatDate(STATS.first_release)} to ${formatDate(STATS.last_release)}`
    : "No releases";
  root.appendChild(el("div", { class: "page-header" }, [
    el("h1", {}, "Release Timeline"),
    el("p",  { class: "page-subtitle" }, subtitle),
  ]));

  // Warnings
  if (warnings.length) {
    root.appendChild(el("div", { class: "warnings" }, [
      el("ul", {}, warnings.map((w) => el("li", {}, w))),
    ]));
  }

  // Summary cards
  const summaryEl = el("div", { class: "rel-summary" });
  [
    { label: "Releases",   value: STATS.total ?? RELEASES.length, cls: "" },
    { label: "Commits",    value: STATS.commits ?? "—",           cls: "" },
    { label: "Major",      value: types.major ?? 0,               cls: "major" },
    { label: "Minor",      value: types.minor ?? 0,               cls: "minor" },
    { label: "Fix",        value: types.fix   ?? 0,               cls: "fix" },
    { label: "Span (days)", value: STATS.delta ?? "—",            cls: "" },
  ].forEach(({ label, value, cls }) => {
    summaryEl.appendChild(el("div", { class: `rel-card ${cls}`.trim() }, [
      el("div", { class: "rel-card-value" }, String(value)),
      el("div", { class: "rel-card-label" }, label),
    ]));
  });
  root.appendChild(summaryEl);

  // Filter + search bar
  const filtersEl = el("div", { class: "filters" });
  const state = { typeFilter: "all", search: "", collapsed: new Set<string>() };

  // Type filter pills
  const pillDefs = [
    { label: "All",   type: "all" },
    { label: "Major", type: "major" },
    { label: "Minor", type: "minor" },
    { label: "Fix",   type: "fix" },
  ];
  const pillBtns = pillDefs.map(({ label, type }) => {
    const count = type === "all" ? RELEASES.length : RELEASES.filter((r) => r.release_type === type).length;
    const btn = el("button", { class: "filter-btn" + (type === "all" ? " active" : ""), "data-type": type },
      [label, el("span", { class: "filter-count" }, count)]);
    btn.addEventListener("click", () => {
      pillBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.typeFilter = type;
      renderTimeline();
    });
    return btn;
  });
  pillBtns.forEach((b) => filtersEl.appendChild(b));

  const searchInput = el("input", {
    type: "search", class: "search-input", placeholder: "Filter by version or content…",
    autocomplete: "off",
  }) as HTMLInputElement;
  searchInput.addEventListener("input", () => { state.search = searchInput.value; renderTimeline(); });
  filtersEl.appendChild(searchInput);

  // Expand / collapse all
  const btnExpand   = el("button", { class: "filter-btn" }, "Expand all") as HTMLButtonElement;
  const btnCollapse = el("button", { class: "filter-btn" }, "Collapse all") as HTMLButtonElement;
  btnExpand.addEventListener("click",   () => { state.collapsed.clear(); renderTimeline(); });
  btnCollapse.addEventListener("click", () => { RELEASES.forEach((r) => state.collapsed.add(r.name)); renderTimeline(); });
  filtersEl.appendChild(btnExpand);
  filtersEl.appendChild(btnCollapse);
  root.appendChild(filtersEl);

  // Timeline container
  const timeline  = el("div", { class: "rel-timeline" });
  const emptyState = el("div", { class: "empty-state" }, "No releases match.");
  root.appendChild(timeline);
  root.appendChild(emptyState);

  // ── Render ───────────────────────────────────────────────────────────────

  function renderTimeline(): void {
    timeline.innerHTML = "";
    const query = state.search.toLowerCase();
    const filtered = RELEASES.filter((r) => {
      if (state.typeFilter !== "all" && r.release_type !== state.typeFilter) return false;
      if (!query) return true;
      return `${r.name} ${r.author ?? ""} ${changelogToText(r.changelog)}`.toLowerCase().includes(query);
    });

    (emptyState as HTMLElement).style.display = filtered.length === 0 ? "" : "none";
    (timeline   as HTMLElement).style.display = filtered.length === 0 ? "none" : "";

    let currentYear = "";
    for (const r of filtered) {
      const y = yearOf(r.date);
      if (y !== currentYear) {
        currentYear = y;
        timeline.appendChild(el("div", { class: "rel-year-marker" }, y));
      }
      timeline.appendChild(renderRelease(r));
    }
  }

  function renderRelease(r: Release): HTMLElement {
    const type        = r.release_type ?? "unknown";
    const isCollapsed = state.collapsed.has(r.name);

    const article = el("article", { class: `rel-release ${type}${isCollapsed ? " collapsed" : ""}` });

    const commits = r.commits ?? 0;
    const header  = el("div", { class: "rel-header" }, [
      el("span", { class: "rel-version" }, r.name),
      el("span", { class: `rel-type-badge ${type}` }, type),
      el("div",  { class: "rel-meta" }, [
        r.author ? el("span", {}, r.author) : null,
        el("span", { class: "rel-date" }, formatDate(r.date)),
        el("span", { class: "rel-commits", title: "Commits in this release" },
          `${commits} ${commits === 1 ? "commit" : "commits"}`),
        el("span", { class: "rel-caret" }, "▼"),
      ]),
    ]);
    header.addEventListener("click", () => {
      if (state.collapsed.has(r.name)) state.collapsed.delete(r.name);
      else state.collapsed.add(r.name);
      article.classList.toggle("collapsed");
    });
    article.appendChild(header);

    const body = el("div", { class: "rel-body" });
    if (!r.changelog?.entries || !Object.keys(r.changelog.entries).length) {
      body.appendChild(el("div", { class: "rel-no-changelog" }, "No changelog provided for this release."));
    } else {
      const entries = r.changelog.entries;
      const keys = [
        ...SECTION_ORDER.filter((k) => k in entries),
        ...Object.keys(entries).filter((k) => !SECTION_ORDER.includes(k)),
      ];
      for (const section of keys) {
        const items = entries[section] ?? [];
        if (!items.length) continue;
        const sec = el("div", { class: `rel-section ${section.toLowerCase()}` });
        sec.appendChild(el("h4", {}, section));
        const ul = el("ul", {});
        for (const item of items) {
          const li = document.createElement("li");
          li.innerHTML = renderInlineCode(item);
          ul.appendChild(li);
        }
        sec.appendChild(ul);
        body.appendChild(sec);
      }
    }
    article.appendChild(body);
    return article;
  }

  renderTimeline();
}
