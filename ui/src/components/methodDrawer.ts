import type { MethodNode } from "../types";
import { el, originBadge, methodKind, SECTION_CLASS } from "../dom";

interface DrawerState {
  panel: HTMLElement;
  overlay: HTMLElement;
  body: HTMLElement;
  close(): void;
}

let _singleton: DrawerState | null = null;

function ensureDrawer(): DrawerState {
  if (_singleton) return _singleton;

  const overlay  = el("div", { class: "drawer-overlay" });
  const panel    = el("div", { class: "drawer-panel" });
  const closeBtn = el("button", { class: "drawer-close", "aria-label": "Close" }, "✕");
  const body     = el("div", { class: "drawer-body" });

  panel.appendChild(closeBtn);
  panel.appendChild(body);
  document.body.appendChild(overlay);
  document.body.appendChild(panel);

  const close = () => {
    panel.classList.remove("drawer-open");
    overlay.classList.remove("drawer-overlay-visible");
  };
  closeBtn.addEventListener("click", close);
  overlay.addEventListener("click", close);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });

  _singleton = { panel, overlay, body, close };
  return _singleton;
}

export function openMethodDrawer(m: MethodNode): void {
  const { panel, overlay, body } = ensureDrawer();
  body.innerHTML = "";

  const kind = methodKind(m);
  const lineCount = m.line_start != null && m.line_end != null
    ? `lines ${m.line_start}–${m.line_end} (${m.line_end - m.line_start + 1} lines)` : null;
  const sig = [m.signature, ...(m.decorators ?? [])].filter(Boolean).join("\n");
  const mAny = m as Record<string, unknown>;

  body.appendChild(el("div", { class: "drawer-method-name mono" }, m.name || "—"));
  body.appendChild(el("div", { class: "drawer-meta" }, [
    el("span", { class: `ft-chip ${SECTION_CLASS[m.section ?? "OTHER"] ?? "other"}` }, m.section ?? "OTHER"),
    el("span", { class: `kind-pill kind-${kind}` }, kind),
  ]));

  if (kind === "override" && m.overrides) {
    const ov = m.overrides as Record<string, string>;
    body.appendChild(el("div", { class: "drawer-row" }, [
      el("span", { class: "drawer-label" }, "Overrides"),
      el("span", {}, [(ov["module"] ?? ov["origin_module"] ?? "—") + " ", ov["origin"] ? originBadge(ov["origin"]) : null]),
    ]));
  } else if (kind === "inherited" && mAny["inherited_from"]) {
    const ih = mAny["inherited_from"] as Record<string, string>;
    body.appendChild(el("div", { class: "drawer-row" }, [
      el("span", { class: "drawer-label" }, "Inherited from"),
      el("span", {}, [(ih["origin_module"] ?? "—") + " ", ih["origin"] ? originBadge(ih["origin"]) : null]),
    ]));
  }

  if (m.docstring) {
    body.appendChild(el("div", { class: "drawer-label" }, "Docstring"));
    body.appendChild(el("p", { class: "drawer-docstring" }, String(m.docstring)));
  }

  if (sig) {
    body.appendChild(el("div", { class: "drawer-label" }, "Signature"));
    body.appendChild(el("pre", { class: "drawer-sig" }, sig));
  }

  if (mAny["source_file"]) {
    body.appendChild(el("div", { class: "drawer-label" }, "File"));
    body.appendChild(el("div", { class: "drawer-path mono" }, String(mAny["source_file"])));
  }
  if (lineCount) {
    body.appendChild(el("div", { class: "drawer-path" }, lineCount));
  }

  panel.classList.add("drawer-open");
  overlay.classList.add("drawer-overlay-visible");
}

export function closeDrawer(): void {
  _singleton?.close();
}
