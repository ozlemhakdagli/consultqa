// Matching a highlight text against the text of PDF pages. Pure functions: no DOM and no pdf.js.
// Text is lowercased with Turkish rules, whitespace is collapsed, and a hyphen at a line end is
// joined to the next line, so "hyphen-" and "ated" match "hyphenated".

const SPACE = /\s/;
// The highlight text is tried whole first, then its first characters; a long answer that the
// text layer splits differently still finds its opening words.
const PREFIX_LENGTHS = [60, 30];

// The index in `raw` of the line end that a hyphen at `start` leads to, or -1 if no line end
// follows it. Spaces between the hyphen and the line end are skipped, and so are the spaces
// that start the next line.
function hyphenBreakEnd(raw, start) {
  let j = start + 1;
  while (j < raw.length && raw[j].ch !== "\n" && SPACE.test(raw[j].ch)) j += 1;
  if (j >= raw.length || raw[j].ch !== "\n") return -1;
  while (j + 1 < raw.length && SPACE.test(raw[j + 1].ch)) j += 1;
  return j;
}

// Items in reading order, each { str, eol } where eol marks a line end. Returns the normalized
// text and, for each character of that text, the index of the item it came from.
export function normalizeItems(items) {
  const raw = [];
  items.forEach((item, index) => {
    for (const ch of item.str) raw.push({ ch, index });
    if (item.eol) raw.push({ ch: "\n", index });
  });
  const chars = [];
  const origins = [];
  for (let i = 0; i < raw.length; i += 1) {
    const { ch, index } = raw[i];
    const breakEnd = ch === "-" ? hyphenBreakEnd(raw, i) : -1;
    if (breakEnd !== -1) {
      i = breakEnd;
      continue;
    }
    if (SPACE.test(ch)) {
      if (chars.length > 0 && chars[chars.length - 1] !== " ") {
        chars.push(" ");
        origins.push(index);
      }
      continue;
    }
    // Code units, not code points, so the origins line up with string offsets.
    const lowered = ch.toLocaleLowerCase("tr");
    for (let k = 0; k < lowered.length; k += 1) {
      chars.push(lowered[k]);
      origins.push(index);
    }
  }
  if (chars[chars.length - 1] === " ") {
    chars.pop();
    origins.pop();
  }
  return { text: chars.join(""), origins };
}

// The strings to look for, most specific first, without repeats.
export function needlesFor(query) {
  const full = normalizeItems([{ str: query, eol: false }]).text;
  if (!full) return [];
  const needles = [full];
  for (const length of PREFIX_LENGTHS) needles.push(full.slice(0, length).trimEnd());
  return [...new Set(needles)].filter((needle) => needle !== "");
}

// The 0-based pages in the order a search reads them: the requested page (1-based), then the page
// after it, because Docling gives a line that runs over a page break to its first page, then the
// other pages in order. Without a usable page the order is the document's own.
export function pageOrder(count, page) {
  const all = Array.from({ length: count }, (_, index) => index);
  const requested = Number(page);
  if (!Number.isInteger(requested) || requested < 1 || requested > count) return all;
  const first = requested - 1;
  const next = first + 1 < count ? [first + 1] : [];
  return [first, ...next, ...all.filter((index) => index !== first && index !== first + 1)];
}

// The first match of the query, looking at the pages in `order` (0-based indexes). `pageText` maps
// an index to the page's normalized text ({ text, origins }), or to null when the search was
// superseded, which ends the search with null. The whole text is looked for on every page in the
// order before any prefix, and pages are read only as far as the search needs them. Returns
// { page, start, end }, the 0-based page and the offsets in its normalized text, or null.
export async function findMatch(pageText, query, order) {
  for (const needle of needlesFor(query)) {
    for (const page of order) {
      const source = await pageText(page);
      if (source === null) return null;
      const start = source.text.indexOf(needle);
      if (start !== -1) return { page, start, end: start + needle.length };
    }
  }
  return null;
}

// The indexes of the items that the characters from start (inclusive) to end (exclusive) came from.
export function itemsInRange(origins, start, end) {
  const items = new Set();
  for (let k = start; k < end; k += 1) items.add(origins[k]);
  return items;
}
