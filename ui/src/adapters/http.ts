import type { Payload } from "../types";
import type { Source } from "../source";

// Stub for a future live `oops serve` exposing POST /api/<method>.
// The current serve uses data.js (StaticSource), so this is not wired yet.
export class HttpSource implements Source {
  readonly kind = "http" as const;
  async load(): Promise<Payload> { return this.run("scan_project"); }
  async run(method: string, ...args: unknown[]): Promise<Payload> {
    const res = await fetch(`/api/${method}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(args),
    });
    if (!res.ok) throw new Error(`http ${method}: ${res.status}`);
    return (await res.json()) as Payload;
  }
}
