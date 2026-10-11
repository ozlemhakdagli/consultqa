// Turkish number, date and size formatting. Each formatter is created once, at load time.
import { LOCALE } from "./config.js";

const SECONDS = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2 });
const MEGABYTES = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 3 });
const DATE_TIME = new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", timeStyle: "short" });

export function formatDateTime(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : DATE_TIME.format(date);
}

export function formatSeconds(ms) {
  return SECONDS.format(ms / 1000);
}

// ".md" becomes "MD"; the order of the extensions is kept.
export function formatFileTypes(extensions) {
  return extensions.map((extension) => extension.replace(/^\./, "").toUpperCase()).join(", ");
}

export function formatMegabytes(mb) {
  return MEGABYTES.format(mb);
}
