export function text(value: unknown, fallback = "unknown"): string {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export function prettyJson(value: unknown): string {
  if (value === undefined) {
    return "{}";
  }
  return JSON.stringify(value, null, 2);
}

export function shortDate(value: unknown): string {
  if (typeof value !== "string" || !value) {
    return "unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export function score(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 1 ? value / 100 : value;
  }
  return null;
}

export function percent(value: unknown, fallback = "unknown"): string {
  const normalized = score(value);
  return normalized === null ? fallback : `${Math.round(normalized * 100)}%`;
}

export function numberText(value: unknown, fallback = "0"): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value.toLocaleString();
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toLocaleString() : fallback;
}

export function duration(value: unknown, fallback = "unknown"): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return fallback;
  }
  if (value < 1000) {
    return `${Math.round(value)} ms`;
  }
  return `${(value / 1000).toFixed(1)} s`;
}

export function stringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => text(item, "")).filter(Boolean);
  }
  if (typeof value === "string" && value.trim()) {
    return value.split(",").map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
