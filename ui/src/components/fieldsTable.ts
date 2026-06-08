import type { FieldNode, Schema } from "../types";
import { el, tableWrap, renderRef, originBadge } from "../dom";

type RichField = FieldNode & { _module?: string };

export interface FieldsTable {
  element: HTMLElement;
  filterBy(filters: { module?: string; type?: string; kind?: string }): void;
  /** Re-render the by-type chips for a given subset of fields. */
  chipsContainer: HTMLElement;
  updateChips(fields: RichField[]): void;
  h2: HTMLElement;
}

export function fieldsTable(allFields: RichField[], _schema?: Schema): FieldsTable {
  const h2 = el("h2", {}, `Fields (${allFields.length})`);

  // By-type chips
  const chipsContainer = el("div", {});
  function rebuildChips(fields: RichField[]) {
    chipsContainer.innerHTML = "";
    const byType: Record<string, number> = {};
    for (const f of fields) byType[f.type ?? "—"] = (byType[f.type ?? "—"] ?? 0) + 1;
    Object.entries(byType).sort((a, b) => b[1] - a[1]).forEach(([t, n]) =>
      chipsContainer.appendChild(el("span", { class: "ft-chip" }, [t, el("span", { class: "count" }, n)]))
    );
  }
  rebuildChips(allFields);

  // Type + kind selectors
  const filterRow = el("div", { class: "filters", style: "margin-top:1rem" });
  const fieldTypes = [...new Set(allFields.map((f) => f.type ?? "").filter(Boolean))].sort();
  const typeSelect = el("select", { class: "filter-select" }) as HTMLSelectElement;
  typeSelect.appendChild(el("option", { value: "" }, "All types"));
  fieldTypes.forEach((t) => typeSelect.appendChild(el("option", { value: t }, t)));
  const kindSelect = el("select", { class: "filter-select" }) as HTMLSelectElement;
  [["", "All kinds"], ["added", "Added"], ["inherited", "Inherited"]]
    .forEach(([v, l]) => kindSelect.appendChild(el("option", { value: v }, l)));
  filterRow.appendChild(
    el("label", { style: "display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;color:var(--text-muted)" },
      ["Type ", typeSelect])
  );
  filterRow.appendChild(
    el("label", { style: "display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;color:var(--text-muted)" },
      ["Kind ", kindSelect])
  );

  // Table
  const thead = el("thead", {}, [el("tr", {}, [
    el("th", {}, "Field"),
    el("th", {}, "Type"),
    el("th", {}, "Label"),
    el("th", {}, "Help"),
    el("th", {}, "Flags"),
    el("th", {}, "Module"),
    el("th", {}, "Status"),
  ])]);

  const tbody = el("tbody", {});
  allFields.slice().sort((a, b) => (a.name ?? "").localeCompare(b.name ?? "")).forEach((f) => {
    const label = f.label
      ?? (f.label_inferred ? (f.name ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "—");
    const helpText = f.help
      ? (f.help.length > 60 ? f.help.slice(0, 60) + "…" : f.help) : "—";
    const flags = [
      (f as Record<string, unknown>)["required"] && "req",
      (f as Record<string, unknown>)["readonly"] && "ro",
      f.store === false && "transient",
    ].filter(Boolean).join(" · ");

    const comodelRef = (f as Record<string, unknown>)["comodel_ref"] as FieldNode["comodel_ref"] | undefined;
    const typeCell = comodelRef
      ? el("td", { class: "mono", style: "font-size:.76rem" }, [(f.type ?? "—") + " → ", renderRef(comodelRef)])
      : el("td", { class: "mono", style: "font-size:.76rem" }, f.type ?? "—");

    const ovr = (f as Record<string, unknown>)["overrides"] as Record<string, string> | undefined;
    const statusCell = f.origin_status === "extended"
      ? el("td", {}, [
          el("span", { class: "status-pill extended" }, "extended"),
          ovr ? el("div", { class: "ovr" }, `→ ${ovr["origin_module"] ?? "—"} (${ovr["origin"] ?? "—"})`) : null,
        ])
      : el("td", {}, el("span", { class: "status-pill" }, f.origin_status ?? "—"));

    const fieldKind = f.origin_status === "extended" ? "inherited" : "added";
    const row = el("tr", { "data-module": f._module ?? "", "data-type": f.type ?? "", "data-kind": fieldKind }, [
      el("td", { class: "mono", style: "font-size:.76rem" }, f.name ?? "—"),
      typeCell,
      el("td", {}, label),
      el("td", { class: "cell-help" }, helpText),
      el("td", { class: "cell-flags" }, flags || "—"),
      el("td", { class: "mono", style: "font-size:.76rem" },
        f._module ? el("a", { href: "#/module/" + encodeURIComponent(f._module) }, f._module) : "—"),
      statusCell,
    ]);
    tbody.appendChild(row);
  });

  const tableEl = tableWrap(el("table", {}, [thead, tbody]));
  const container = el("div", {});
  container.appendChild(filterRow);
  container.appendChild(tableEl);
  const wrap = container;

  function applyFilter(filters: { module?: string; type?: string; kind?: string }) {
    const mod  = filters.module  ?? "";
    const type = filters.type    ?? typeSelect.value;
    const kind = filters.kind    ?? kindSelect.value;
    for (const row of tbody.querySelectorAll<HTMLElement>("tr")) {
      const show = (!mod  || row.dataset["module"] === mod)
        && (!type || row.dataset["type"] === type)
        && (!kind || row.dataset["kind"] === kind);
      row.style.display = show ? "" : "none";
    }
  }

  typeSelect.addEventListener("change", () => applyFilter({}));
  kindSelect.addEventListener("change", () => applyFilter({}));

  return {
    element: wrap,
    filterBy(filters) { applyFilter(filters); },
    chipsContainer,
    updateChips: rebuildChips,
    h2,
  };
}
