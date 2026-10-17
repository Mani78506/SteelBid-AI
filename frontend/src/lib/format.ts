/** Decimal-aware display formatting. Backend returns numeric strings. */

export function fmtMoney(value?: string | number | null, currency = "₹"): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  if (Math.abs(n) >= 1e7) return `${currency}${(n / 1e7).toFixed(2)}Cr`;
  if (Math.abs(n) >= 1e5) return `${currency}${(n / 1e5).toFixed(2)}L`;
  return `${currency}${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export function fmtQty(value?: string | number | null, unit = "MT"): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return `${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })} ${unit}`;
}

export function fmtPct(value?: string | number | null): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value) * 100;
  if (Number.isNaN(n)) return String(value);
  return `${n.toFixed(1)}%`;
}

export function fmtDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtDateTime(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function daysUntil(value?: string | null): number | null {
  if (!value) return null;
  const ms = new Date(value).getTime() - Date.now();
  return Math.round(ms / 86400000);
}
