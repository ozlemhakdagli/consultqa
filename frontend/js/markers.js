// Splits an answer into text and citation markers such as [1] or [1, 2].
// A bracket right after a letter, digit or underscore is an index (arr[3]), not a citation.
const MARKER = /(?<![\p{L}\p{N}_])\[(\d+(?:\s*,\s*\d+)*)\]/gu;

export function splitMarkers(text) {
  const parts = [];
  let last = 0;
  for (const match of text.matchAll(MARKER)) {
    if (match.index > last) parts.push({ type: "text", value: text.slice(last, match.index) });
    parts.push({ type: "marker", numbers: match[1].split(",").map((n) => Number(n.trim())) });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ type: "text", value: text.slice(last) });
  return parts;
}
