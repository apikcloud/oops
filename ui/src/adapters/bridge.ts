import type { Payload } from "../types";
import type { Source } from "../source";

// pywebview: window.pywebview.api.<method>(...) returns a JS object directly.
export class BridgeSource implements Source {
  readonly kind = "bridge" as const;
  private api(): Record<string, (...a: unknown[]) => Promise<Payload>> {
    const pw = (window as unknown as { pywebview?: { api?: Record<string, never> } }).pywebview;
    if (!pw?.api) throw new Error("bridge mode: window.pywebview.api missing");
    return pw.api as never;
  }
  async load(): Promise<Payload> { return this.run("scan_project"); }
  async run(method: string, ...args: unknown[]): Promise<Payload> {
    return await this.api()[method](...args);
  }
}
