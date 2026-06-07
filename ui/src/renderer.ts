import type { Payload } from "./types";
import type { Source } from "./source";
import { viewList }    from "./views/list";
import { viewServe }   from "./views/serve";
import { viewAnalyze } from "./views/analyze";
import { viewDepends } from "./views/depends";
import { viewRelease } from "./views/release";
import { viewChecks }  from "./views/checks";

export type View = (root: HTMLElement, payload: Payload, source: Source) => void;

// Add an entry here as each view is ported (depends show, release show, checks…).
const VIEWS: Record<string, View> = {
  "addons list":    viewList,
  "project serve":  viewServe,
  "addons analyze": viewAnalyze,
  "depends show":   viewDepends,
  "release show":   viewRelease,
  "checks":         viewChecks,
  "project check":  viewChecks,
  "requirements check": viewChecks,
};

function viewUnknown(root: HTMLElement, payload: Payload): void {
  root.textContent = `No view registered for command: ${payload.metadata?.command ?? "—"}`;
}

/** Pure: payload in, DOM out. No I/O, no source detection here. */
export function render(root: HTMLElement, payload: Payload, source: Source): void {
  root.innerHTML = "";
  const cmd = payload.metadata?.command ?? "";
  const brand = document.getElementById("brand-cmd");
  if (brand) brand.textContent = cmd;
  (VIEWS[cmd] ?? viewUnknown)(root, payload, source);
}
