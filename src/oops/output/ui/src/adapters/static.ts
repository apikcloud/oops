import type { Payload } from "../types";
import type { Source } from "../source";

// Data frozen into the page as window.OOPS — used by both the export file and
// `oops serve` (which writes data.js). Read-only: no run().
export class StaticSource implements Source {
  readonly kind = "static" as const;
  async load(): Promise<Payload> {
    const data = (window as unknown as { OOPS?: Payload }).OOPS;
    if (!data) throw new Error("static mode: window.OOPS is missing");
    return data;
  }
}
