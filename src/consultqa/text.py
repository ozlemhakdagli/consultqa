"""Text folds and tokenisation for consultqa: the Turkish rule and the default rule.

The Turkish rule (``casefold_tr``) maps I to ı, which is right for Turkish text. The default
rule (``casefold_neutral``) maps I to i, which is right for English. A document is folded with
the Turkish rule when it contains a Turkish letter and with the default rule otherwise; see
``document_folds``.
"""

import re
import string
import unicodedata
from collections.abc import Callable, Iterable

from consultqa.models import Chunk

Fold = Callable[[str], str]

_NON_ALNUM = re.compile(r"[\W_]+")
_TURKISH_LETTER = re.compile("[çğıöşüÇĞİÖŞÜ]")
_EDGE_CHARS = string.punctuation + "“”„‟‘’‚«»" + " "


def casefold_tr(text: str) -> str:
    """Lowercase text with Turkish rules: dotted İ becomes i, dotless I becomes ı.

    The text is first put in Unicode NFC form, so that a decomposed spelling ("I" plus a
    combining dot, or "e" plus a combining acute) matches the precomposed one. The substitutions
    then run before ``str.lower()``, which would otherwise map I to i.
    """
    text = unicodedata.normalize("NFC", text)
    return text.replace("İ", "i").replace("I", "ı").lower()


def casefold_neutral(text: str) -> str:
    """Lowercase text with the default rule: I becomes i and dotted İ becomes i too.

    Unlike ``casefold_tr``, I is not turned into ı, so an English capital I matches the
    lowercase letter in questions. The dotless ı is left as it is.
    """
    text = unicodedata.normalize("NFC", text)
    return text.replace("İ", "i").lower()


def has_turkish_letters(text: str) -> bool:
    """True when the NFC form of the text contains one of the letters çğıöşü and their capitals."""
    return _TURKISH_LETTER.search(unicodedata.normalize("NFC", text)) is not None


def tokenize(text: str, prefix: int | None = None, *, fold: Fold = casefold_tr) -> list[str]:
    """Split the folded text into tokens, keeping the first ``prefix`` characters of each."""
    tokens = [token for token in _NON_ALNUM.split(fold(text)) if token]
    if prefix is not None:
        tokens = [token[:prefix] for token in tokens]
    return tokens


def document_folds(chunks: Iterable[Chunk]) -> dict[str, Fold]:
    """The fold of each document: the Turkish rule if any of its chunks has a Turkish letter."""
    folds: dict[str, Fold] = {}
    for chunk in chunks:
        if has_turkish_letters(chunk.text):
            folds[chunk.doc_id] = casefold_tr
        else:
            folds.setdefault(chunk.doc_id, casefold_neutral)
    return folds


def tokenize_tr(text: str, prefix: int | None = None) -> list[str]:
    """Split text into casefolded Turkish tokens, keeping the first ``prefix`` characters."""
    return tokenize(text, prefix, fold=casefold_tr)


def normalize_answer(text: str | None) -> str:
    """Normalise an answer for comparison: casefold, trim edge punctuation, collapse spaces."""
    if text is None:
        return ""
    # Collapse all whitespace to ASCII spaces first, so one strip removes every edge character.
    collapsed = " ".join(casefold_tr(text).split())
    return collapsed.strip(_EDGE_CHARS)
