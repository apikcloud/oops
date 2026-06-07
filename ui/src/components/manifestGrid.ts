import { el } from "../dom";

export function manifestGrid(manifest: Record<string, unknown>): HTMLElement {
  const grid = el("div", { class: "manifest-grid" });
  for (const [key, value] of Object.entries(manifest)) {
    if (value == null || value === "") continue;
    const display = typeof value === "boolean" ? (value ? "yes" : "no") : String(value);
    grid.appendChild(el("div", { class: "manifest-item" }, [
      el("span", { class: "manifest-label" }, key.replace(/_/g, " ")),
      el("span", { class: "manifest-value" }, display),
    ]));
  }
  return grid;
}
