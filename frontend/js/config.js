// Timing and display constants of the page. Durations are in milliseconds.
// Number and date conventions of each language: Turkish keeps the comma; English uses the UK
// style, which is day-first and 24-hour like Turkish, so no date reads as month first.
export const LOCALES = Object.freeze({ tr: "tr-TR", en: "en-GB" });
// The stored name of the default library. It is the same in every language, and existing
// installs already use it, so the name must not change with the page language.
export const DEFAULT_LIBRARY_NAME = "Belgelerim";
export const READY_POLL_MS = 3000;
export const JOB_POLL_MS = 1000;
export const JOB_MAX_WAIT_MS = 900000;
export const JOB_MAX_POLL_FAILURES = 3;
