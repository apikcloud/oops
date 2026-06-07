import { StaticSource } from "./adapters/static";
import { BridgeSource } from "./adapters/bridge";
import { HttpSource } from "./adapters/http";
import type { Source } from "./source";
import { render } from "./renderer";
import { bootDashboard } from "./views/dashboard";

function pickSource(): Source {
  const w = window as unknown as { pywebview?: unknown; OOPS?: unknown };
  if (w.pywebview) return new BridgeSource();
  if (w.OOPS) return new StaticSource();
  return new HttpSource();
}

async function boot(): Promise<void> {
  const root = document.getElementById("app");
  if (!root) return;
  const source = pickSource();
  if (source.kind === "bridge") {
    bootDashboard(root, source as BridgeSource);
    return;
  }
  try {
    render(root, await source.load(), source);
  } catch (e) {
    root.textContent = (e as Error).message;
  }
}

// The pywebview bridge is injected slightly after load; wait for it when
// present, otherwise boot static/http after a short grace period.
let booted = false;
const once = () => { if (!booted) { booted = true; void boot(); } };

if ((window as unknown as { pywebview?: unknown }).pywebview) once();
else {
  window.addEventListener("pywebviewready", once, { once: true });
  window.addEventListener("DOMContentLoaded", () => setTimeout(once, 200));
}
