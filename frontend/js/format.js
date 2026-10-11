// Turkish number, date and size formatting. Each formatter is created once, at load time.
import { LOCALE } from "./config.js";

const SECONDS = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2 });
const SCORE = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 4, maximumFractionDigits: 4 });
const MEGABYTES = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 3 });
const DATE_TIME = new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", timeStyle: "short" });

export function formatDateTime(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : DATE_TIME.format(date);
}

export function formatSeconds(ms) {
  return SECONDS.format(ms / 1000);
}

export function formatScore(value) {
  return SCORE.format(value);
}

export function formatMegabytes(mb) {
  return MEGABYTES.format(mb);
}
