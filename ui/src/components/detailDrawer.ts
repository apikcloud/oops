import { el } from "../dom";

interface DrawerState {
  panel: HTMLElement;
  overlay: HTMLElement;
  body: HTMLElement;
  close(): void;
}

let _singleton: DrawerState | null = null;

export function ensureDrawer(): DrawerState {
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

export function closeDrawer(): void {
  _singleton?.close();
}

type PwApi = Record<string, (...a: unknown[]) => Promise<{ code?: string }>>;

export async function fetchSource(file: string, start: number, end: number): Promise<string | null> {
  try {
    const pw = (window as unknown as Record<string, unknown>).pywebview as { api?: PwApi } | undefined;
    if (pw?.api?.read_source) {
      const data = await pw.api.read_source(file, start, end);
      return data.code ?? null;
    }
    const url = `/api/source?file=${encodeURIComponent(file)}&start=${start}&end=${end}`;
    const res = await fetch(url);
    if (!res.ok) return null;
    const data = await res.json() as { code?: string };
    return data.code ?? null;
  } catch {
    return null;
  }
}

export function renderCode(code: string, startLine: number): HTMLElement {
  const pre = el("pre", { class: "source-code" });
  const lines = code.split("\n");
  for (let i = 0; i < lines.length; i++) {
    pre.appendChild(el("div", { class: "source-line" }, [
      el("span", { class: "source-lineno" }, String(startLine + i)),
      el("span", { class: "source-linetext" }, lines[i] || ""),
    ]));
  }
  return pre;
}
