import type { Schema } from "./types";
import { fmt, humanize } from "./dom";

export function descriptorTitle(group: string, key: string, schema?: Schema): string {
  const defs = schema?.definitions ?? {};
  return (defs[group]?.properties?.[key] as { title?: string } | undefined)?.title ?? humanize(key);
}

export function descriptorKind(group: string, key: string, schema?: Schema): string {
  const defs = schema?.definitions ?? {};
  return ((defs[group]?.properties?.[key] as Record<string, string> | undefined)?.["x-kind"]) ?? "count";
}

export function formatValue(value: unknown, kind: string): string {
  if (value == null) return "—";
  if (kind === "boolean") return value ? "✓" : "✗";
  if (kind === "percent") return Number(value).toFixed(1) + "%";
  if (kind === "bytes") {
    const n = Number(value);
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / (1024 * 1024)).toFixed(1) + " MB";
  }
  return typeof value === "number" ? fmt(value) : String(value);
}
