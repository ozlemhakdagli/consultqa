"""Turkish-aware text normalisation and tokenisation for docrag."""

import re
import string
import unicodedata

_NON_ALNUM = re.compile(r"[\W_]+")
_EDGE_CHARS = string.punctuation + "“”„‟‘’‚«»" + " "


def casefold_tr(text: str) -> str:
    """Lowercase text with Turkish rules: dotted İ becomes i, dotless I becomes ı.

    The text is first put in Unicode NFC form, so that a decomposed spelling ("I" plus a
    combining dot, or "e" plus a combining acute) matches the precomposed one. The substitutions
    then run before ``str.lower()``, which would otherwise map I to i.
    """
    text = unicodedata.normalize("NFC", text)
    return text.replace("İ", "i").replace("I", "ı").lower()


def tokenize_tr(text: str, prefix: int | None = None) -> list[str]:
    """Split text into casefolded Turkish tokens, keeping the first ``prefix`` characters."""
    tokens = [token for token in _NON_ALNUM.split(casefold_tr(text)) if token]
    if prefix is not None:
        tokens = [token[:prefix] for token in tokens]
    return tokens


def normalize_answer(text: str | None) -> str:
    """Normalise an answer for comparison: casefold, trim edge punctuation, collapse spaces."""
    if text is None:
        return ""
    # Collapse all whitespace to ASCII spaces first, so one strip removes every edge character.
    collapsed = " ".join(casefold_tr(text).split())
    return collapsed.strip(_EDGE_CHARS)
