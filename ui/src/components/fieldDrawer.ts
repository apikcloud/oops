import type { FieldNode } from "../types";
import { el, renderRef, originBadge } from "../dom";
import { ensureDrawer, fetchSource, renderCode } from "./detailDrawer";

export function openFieldDrawer(f: FieldNode & { _module?: string }): void {
  const { panel, overlay, body } = ensureDrawer();
  body.innerHTML = "";

  // Header: field name
  body.appendChild(el("div", { class: "drawer-method-name mono" }, f.name || "—"));

  // Type row (with comodel link for relational fields)
  const typeEl = f.comodel_ref
    ? el("div", { class: "drawer-row" }, [
        el("span", { class: "drawer-label" }, "Type"),
        el("span", { class: "mono" }, [(f.type ?? "—") + " → ", renderRef(f.comodel_ref)]),
      ])
    : el("div", { class: "drawer-row" }, [
        el("span", { class: "drawer-label" }, "Type"),
        el("span", { class: "mono" }, f.type ?? "—"),
      ]);
  body.appendChild(typeEl);

  // Label + help
  if (f.label || f.label_inferred) {
    const label = f.label
      ?? (f.label_inferred ? (f.name ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : null);
    if (label) {
      body.appendChild(el("div", { class: "drawer-row" }, [
        el("span", { class: "drawer-label" }, "Label"),
        el("span", {}, label),
      ]));
    }
  }
  if (f.help) {
    body.appendChild(el("div", { class: "drawer-row" }, [
      el("span", { class: "drawer-label" }, "Help"),
      el("span", { class: "drawer-docstring" }, f.help),
    ]));
  }

  // Flags
  const flags = [
    f.required  && el("span", { class: "ft-chip" }, "required"),
    f.readonly  && el("span", { class: "ft-chip" }, "readonly"),
    f.store === false && el("span", { class: "ft-chip" }, "transient"),
    f.compute   && el("span", { class: "ft-chip" }, "computed"),
  ].filter(Boolean) as HTMLElement[];
  if (flags.length) {
    body.appendChild(el("div", { class: "drawer-row" }, [
      el("span", { class: "drawer-label" }, "Flags"),
      el("div", { class: "drawer-meta" }, flags),
    ]));
  }

  // Origin status + overrides
  if (f.origin_status) {
    const ovr = f.overrides;
    const statusEl = f.origin_status === "extended" && ovr
      ? el("div", { class: "drawer-row" }, [
          el("span", { class: "drawer-label" }, "Status"),
          el("span", {}, [
            el("span", { class: "status-pill extended" }, "extended"),
            el("span", { class: "muted", style: "font-size:0.78rem;margin-left:0.4rem" }, [
              `→ ${ovr.origin_module ?? "—"} `,
              ovr.origin ? originBadge(ovr.origin) : null,
            ]),
          ]),
        ])
      : el("div", { class: "drawer-row" }, [
          el("span", { class: "drawer-label" }, "Status"),
          el("span", {}, el("span", { class: "status-pill" }, f.origin_status)),
        ]);
    body.appendChild(statusEl);
  }

  // Module link
  if (f._module) {
    body.appendChild(el("div", { class: "drawer-row" }, [
      el("span", { class: "drawer-label" }, "Module"),
      el("a", { href: "#/module/" + encodeURIComponent(f._module), class: "mono" }, f._module),
    ]));
  }

  // Source file + code toggle
  if (f.source_file) {
    const lines = f.line_start != null
      ? (f.line_end != null && f.line_end !== f.line_start
          ? `:${f.line_start}–${f.line_end}` : `:${f.line_start}`)
      : "";
    body.appendChild(el("div", { class: "drawer-label" }, "Source"));
    body.appendChild(el("div", { class: "drawer-path mono" }, f.source_file + lines));

    if (f.line_start != null) {
      const codeArea = el("div", { class: "stack-code-area" });
      const toggleBtn = el("button", { class: "stack-code-toggle" }, "Show code");
      let loaded = false;

      toggleBtn.addEventListener("click", async () => {
        const hidden = codeArea.style.display === "none" || codeArea.style.display === "";
        if (!hidden) {
          codeArea.style.display = "none";
          (toggleBtn as HTMLButtonElement).textContent = "Show code";
          return;
        }
        codeArea.style.display = "block";
        (toggleBtn as HTMLButtonElement).textContent = "Hide code";
        if (!loaded) {
          loaded = true;
          codeArea.textContent = "Loading…";
          const code = await fetchSource(f.source_file!, f.line_start!, f.line_end ?? f.line_start!);
          codeArea.innerHTML = "";
          if (code != null) codeArea.appendChild(renderCode(code, f.line_start!));
          else codeArea.appendChild(el("p", { class: "stack-code-unavail" }, "Source not available."));
        }
      });

      codeArea.style.display = "none";
      body.appendChild(toggleBtn);
      body.appendChild(codeArea);
    }
  }

  panel.classList.add("drawer-open");
  overlay.classList.add("drawer-overlay-visible");
}
