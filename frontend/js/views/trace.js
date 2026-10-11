// The retrieval trace: collapsed by default, grouped by stage, with the first rows of each stage.
import { TRACE_ROWS_PER_STAGE } from "../config.js";
import { el } from "../dom.js";
import { formatScore } from "../format.js";
import { has, t } from "../i18n.js";

function labelOr(key, fallback) {
  return has(key) ? t(key) : fallback;
}

function groupByStage(trace) {
  const groups = new Map();
  for (const item of trace) {
    if (!groups.has(item.stage)) groups.set(item.stage, []);
    groups.get(item.stage).push(item);
  }
  return groups;
}

function stageTable(rows) {
  const body = rows.slice(0, TRACE_ROWS_PER_STAGE).map((row) =>
    el(
      "tr",
      {},
      el("td", { text: String(row.rank) }),
      el("td", {}, el("code", { text: row.chunk_id })),
      el("td", { text: formatScore(row.score) }),
      el("td", { text: labelOr(`trace.score.${row.score_type}`, row.score_type) }),
    ),
  );
  const head = el(
    "tr",
    {},
    el("th", { text: t("trace.col.rank") }),
    el("th", { text: t("trace.col.chunk") }),
    el("th", { text: t("trace.col.score") }),
    el("th", { text: t("trace.col.scoreType") }),
  );
  return el(
    "div",
    { class: "table-wrap" },
    el("table", {}, el("thead", {}, head), el("tbody", {}, ...body)),
  );
}

// Returns null for an empty trace, so the page shows nothing for it.
export function renderTrace(trace) {
  if (trace.length === 0) return null;
  const children = [
    el("summary", { text: t("result.traceTitle") }),
    el("p", { class: "help", text: t("result.traceHelp", { count: TRACE_ROWS_PER_STAGE }) }),
  ];
  for (const [stage, rows] of groupByStage(trace)) {
    children.push(el("h4", { text: labelOr(`trace.stage.${stage}`, stage) }), stageTable(rows));
  }
  return el("details", { class: "trace" }, ...children);
}
