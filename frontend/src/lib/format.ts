export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${Math.max(0, Math.round(ms))} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
  const minutes = Math.floor(ms / 60_000);
  return `${minutes} min ${Math.round((ms % 60_000) / 1000)} s`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  // Spec: "13 Nov 2026, 3:04 pm IST" — always India time, whatever the viewer's zone.
  const day = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });
  const time = date
    .toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: "Asia/Kolkata" })
    .toLowerCase();
  return `${day}, ${time} IST`;
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return `${date
    .toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit", hour12: true, timeZone: "Asia/Kolkata" })
    .toLowerCase()} IST`;
}

export function mask(value: string | null | undefined, visible = 4): string {
  const text = (value ?? "").trim();
  if (!text) return "Not supplied";
  if (text.length <= visible) return "•".repeat(text.length);
  return "•".repeat(Math.min(8, text.length - visible)) + text.slice(-visible);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** "20 min", "3 hours", "2 days" since an ISO time (how long a case has waited). */
export function formatAge(value: string | null | undefined, now: number = Date.now()): string {
  if (!value) return "—";
  const then = Date.parse(value);
  if (Number.isNaN(then)) return "—";
  const minutes = Math.max(0, Math.floor((now - then) / 60_000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? "hour" : "hours"}`;
  const days = Math.floor(hours / 24);
  return `${days} ${days === 1 ? "day" : "days"}`;
}
