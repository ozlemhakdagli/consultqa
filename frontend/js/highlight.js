// Finds an answer inside its source passage and the sentence that holds it, so the page can show
// the whole passage with that sentence marked. Pure functions: no DOM and no page text.

const SENTENCE_END = ".!?…";

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// The answer as it stands in the passage: exactly first, then with any whitespace between its words.
function locate(passage, answer) {
  const exact = passage.indexOf(answer);
  if (exact !== -1) return { start: exact, end: exact + answer.length };
  const words = answer.split(/\s+/).map(escapeRegExp);
  const match = passage.match(new RegExp(words.join("\\s+")));
  return match ? { start: match.index, end: match.index + match[0].length } : null;
}

// The sentence begins after the last line break, or after the last sentence end and its spaces.
function sentenceStart(passage, start) {
  const breaks = [...passage.slice(0, start).matchAll(/[.!?…]\s+|\n/g)];
  const last = breaks.at(-1);
  return last ? last.index + last[0].length : 0;
}

// The sentence ends with its own sentence end (kept), with the next line break (left out), or with
// the passage. An answer that already ends with a sentence end ends the sentence too.
function sentenceEnd(passage, end, answerText) {
  if (SENTENCE_END.includes(answerText.at(-1))) return end;
  const next = passage.slice(end).search(/[.!?…](?=\s|$)|\n/);
  if (next === -1) return passage.length;
  const found = passage[end + next];
  return end + next + (found === "\n" ? 0 : 1);
}

// Splits a passage into the parts before the sentence, the sentence up to the answer, the answer,
// the rest of the sentence and the text after it. Null when the answer is empty or not found.
export function splitPassage(passage, answer) {
  const wanted = (answer ?? "").trim();
  if (wanted === "") return null;
  const found = locate(passage, wanted);
  if (found === null) return null;
  const { start, end } = found;
  const from = sentenceStart(passage, start);
  const to = sentenceEnd(passage, end, passage.slice(start, end));
  return {
    before: passage.slice(0, from),
    lead: passage.slice(from, start),
    answer: passage.slice(start, end),
    tail: passage.slice(end, to),
    after: passage.slice(to),
  };
}
