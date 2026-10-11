// Number, date and size formatting in the page's current language. The formatters of a language
// are created on first use and then reused.
import { LOCALES } from "./config.js";
import { currentLanguage } from "./i18n.js";

const formatters = new Map();

function formattersForLanguage() {
  const language = currentLanguage();
  if (!formatters.has(language)) {
    const locale = LOCALES[language];
    formatters.set(language, {
      seconds: new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }),
      megabytes: new Intl.NumberFormat(locale, { maximumFractionDigits: 3 }),
      dateTime: new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }),
    });
  }
  return formatters.get(language);
}

export function formatDateTime(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : formattersForLanguage().dateTime.format(date);
}

export function formatSeconds(ms) {
  return formattersForLanguage().seconds.format(ms / 1000);
}

// ".md" becomes "MD"; the order of the extensions is kept.
export function formatFileTypes(extensions) {
  return extensions.map((extension) => extension.replace(/^\./, "").toUpperCase()).join(", ");
}

export function formatMegabytes(mb) {
  return formattersForLanguage().megabytes.format(mb);
}
