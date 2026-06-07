import type { BareModelEntry, ModuleEntry } from "../types";
import { el, numCell, tableWrap, originBadge } from "../dom";
import { methodKind } from "../dom";

export function provenanceTable(entry: BareModelEntry, modules: ModuleEntry[]): HTMLElement {
  const contributions = entry.contributions ?? [];

  const thead = el("thead", {}, [el("tr", {}, [
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

  const rows = contributions.map((c) => {
    const node    = c.model_node;
    const fields  = c.fields  ?? [];
    const methods = c.methods ?? [];
    const fAdded  = fields.filter((f) => f.origin_status === "new" || f.origin_status === "base").length;
    const fInher  = fields.filter((f) => f.origin_status === "extended").length;
    const mAdded  = methods.filter((m) => methodKind(m) === "added").length;
    const mInher  = methods.filter((m) => methodKind(m) === "inherited").length;
    const mOver   = methods.filter((m) => methodKind(m) === "override").length;
    const cls     = modules.find((mod) => mod.module === c.module)?.inventory?.classification;
    const origin  = cls === "third-party" ? "third_party" : (cls ?? null);
    return el("tr", {}, [
      el("td", { class: "mono" }, el("a", { href: "#/module/" + encodeURIComponent(c.module) }, c.module)),
      el("td", {}, node?.status ? el("span", { class: "status-pill" }, node.status) : "—"),
      el("td", {}, origin ? originBadge(origin) : "—"),
      el("td", { class: "mono prov-ancestor" }, node?.ancestor_module ?? "—"),
      numCell(fAdded), numCell(fInher),
      numCell(mAdded), numCell(mInher), numCell(mOver),
    ]);
  });

  const section = el("div", { class: "provenance-section" });
  section.appendChild(el("h2", {}, "Provenance"));
  section.appendChild(tableWrap(el("table", {}, [thead, el("tbody", {}, rows)])));
  return section;
}
