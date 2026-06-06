import type { Payload } from "./types";

/** A hydration source. The renderer never knows which one is wired. */
export interface Source {
  readonly kind: "static" | "bridge" | "http";
  /** Payload to render on boot. */
  load(): Promise<Payload>;
  /** Run a command live. Present only on interactive sources. */
  run?(method: string, ...args: unknown[]): Promise<Payload>;
}
