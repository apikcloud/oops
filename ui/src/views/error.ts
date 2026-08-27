import type { Payload } from "../types";
import type { Source } from "../source";
import { el } from "../dom";

/** Fallback view for `{"metadata": {"command": "error"}, "error": "..."}`
 * payloads — emitted by `run_oops()` on a subprocess crash and by
 * `Api.doc_project()` on any exception in the in-process doc pipeline. */
export function viewError(root: HTMLElement, payload: Payload, _source: Source): void {
  const message = typeof payload.error === "string" && payload.error ? payload.error : "Unknown error.";

  root.appendChild(el("div", { class: "page-header" }, [el("h1", {}, "Error")]));
  root.appendChild(el("div", { class: "warnings" }, [
    el("pre", { style: "white-space:pre-wrap;margin:0" }, message),
  ]));
}
