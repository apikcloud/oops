import type { MethodNode } from "../types";
import { el, tableWrap, originBadge, methodKind, SECTION_ORDER, SECTION_CLASS } from "../dom";
import { openMethodDrawer } from "./methodDrawer";

type RichMethod = MethodNode & { _module?: string };

export interface MethodsTable {
  element: HTMLElement;
  filterBy(filters: { module?: string; section?: string; kind?: string }): void;
  chipsContainer: HTMLElement;
  updateChips(methods: RichMethod[]): void;
  h2: HTMLElement;
}

export function methodsTable(allMethods: RichMethod[]): MethodsTable {
  const h2 = el("h2", {}, `Methods (${allMethods.length})`);

  // Section summary chips
  const chipsContainer = el("div", { style: "margin-bottom:1rem" });
  function rebuildChips(methods: RichMethod[]) {
    chipsContainer.innerHTML = "";
    const bySection: Record<string, number> = {};
    for (const m of methods) bySection[m.section ?? "OTHER"] = (bySection[m.section ?? "OTHER"] ?? 0) + 1;
    Object.entries(bySection).sort((a, b) => b[1] - a[1]).forEach(([s, n]) =>
      chipsContainer.appendChild(el("span", { class: `ft-chip ${SECTION_CLASS[s] ?? "other"}` }, [
        s, el("span", { class: "count" }, n),
      ]))
    );
  }
  rebuildChips(allMethods);

  // Section + kind selectors
  const filterRow = el("div", { class: "filters", style: "margin-bottom:1rem" });
  const bySection: Record<string, number> = {};
  for (const m of allMethods) bySection[m.section ?? "OTHER"] = (bySection[m.section ?? "OTHER"] ?? 0) + 1;

  const sectionSelect = el("select", { class: "filter-select" }) as HTMLSelectElement;
  sectionSelect.appendChild(el("option", { value: "" }, "All sections"));
  SECTION_ORDER.filter((s) => bySection[s]).forEach((s) =>
    sectionSelect.appendChild(el("option", { value: s }, s))
  );

  const kindSelect = el("select", { class: "filter-select" }) as HTMLSelectElement;
  [["", "All kinds"], ["added", "Added"], ["inherited", "Inherited"], ["override", "Overridden"]]
    .forEach(([v, l]) => kindSelect.appendChild(el("option", { value: v }, l)));

  filterRow.appendChild(
    el("label", { style: "display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;color:var(--text-muted)" },
      ["Section ", sectionSelect])
  );
  filterRow.appendChild(
    el("label", { style: "display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;color:var(--text-muted)" },
      ["Kind ", kindSelect])
  );

  // Table
  const thead = el("thead", {}, [el("tr", {}, [
    el("th", {}, "Method"),
    el("th", {}, "Section"),
    el("th", {}, "Kind"),
    el("th", {}, "Module"),
    el("th", {}, "Origin / From"),
    el("th", { class: "num" }, "Lines"),
    el("th", {}, "Doc"),
  ])]);

  const tbody = el("tbody", {});
  allMethods.slice()
    .sort((a, b) => {
      const si = SECTION_ORDER.indexOf(a.section as never ?? "OTHER") - SECTION_ORDER.indexOf(b.section as never ?? "OTHER");
      return si !== 0 ? si : (a.name ?? "").localeCompare(b.name ?? "");
    })
    .forEach((m) => {
      const kind  = methodKind(m);
      const lines = m.line_start != null && m.line_end != null ? (m.line_end - m.line_start + 1) : null;
      const mAny  = m as Record<string, unknown>;

      let originCell: HTMLElement;
      if (kind === "override" && m.overrides) {
        const ov = m.overrides as Record<string, string>;
        originCell = el("td", {}, [
          el("span", { class: "ovr" }, (ov["module"] ?? ov["origin_module"] ?? "—") + " "),
          ov["origin"] ? originBadge(ov["origin"]) : null,
        ]);
      } else if (kind === "inherited" && mAny["inherited_from"]) {
        const ih = mAny["inherited_from"] as Record<string, string>;
        originCell = el("td", {}, [
          el("span", { class: "ovr" }, (ih["origin_module"] ?? "—") + " "),
          ih["origin"] ? originBadge(ih["origin"]) : null,
        ]);
      } else {
        originCell = el("td", { style: "color:var(--text-muted)" }, "—");
      }

      const row = el("tr", {
        class: "clickable",
        "data-module":  m._module       ?? "",
        "data-section": m.section       ?? "OTHER",
        "data-kind":    kind,
      }, [
        el("td", { class: "mono", style: "font-size:.76rem" }, m.name ?? "—"),
        el("td", {}, el("span", {
          class: `ft-chip ${SECTION_CLASS[m.section ?? "OTHER"] ?? "other"}`,
          style: "font-size:.68rem;padding:.05rem .35rem",
        }, m.section ?? "OTHER")),
        el("td", {}, el("span", { class: `kind-pill kind-${kind}` }, kind)),
        el("td", { class: "mono", style: "font-size:.76rem" },
          m._module ? el("a", { href: "#/module/" + encodeURIComponent(m._module) }, m._module) : "—"),
        originCell,
        el("td", { class: "num" }, lines != null ? lines : "—"),
        el("td", {}, mAny["docstring"]
          ? el("span", { class: "doc-yes" }, "✓")
          : el("span", { class: "doc-no" }, "—")),
      ]);

      row.addEventListener("click", () => openMethodDrawer(m));
      tbody.appendChild(row);
    });

  const tableEl = tableWrap(el("table", {}, [thead, tbody]));
  const container = el("div", {});
  container.appendChild(filterRow);
  container.appendChild(tableEl);
  const wrap = container;

  function applyFilter(filters: { module?: string; section?: string; kind?: string }) {
    const mod  = filters.module  ?? "";
    const sec  = filters.section ?? sectionSelect.value;
    const kind = filters.kind    ?? kindSelect.value;
    for (const row of tbody.querySelectorAll<HTMLElement>("tr")) {
      const show = (!mod  || row.dataset["module"]  === mod)
        && (!sec  || row.dataset["section"] === sec)
        && (!kind || row.dataset["kind"]    === kind);
      row.style.display = show ? "" : "none";
    }
  }

  sectionSelect.addEventListener("change", () => applyFilter({}));
  kindSelect.addEventListener("change",    () => applyFilter({}));

  return {
    element: wrap,
    filterBy(filters) { applyFilter(filters); },
    chipsContainer,
    updateChips: rebuildChips,
    h2,
  };
}
