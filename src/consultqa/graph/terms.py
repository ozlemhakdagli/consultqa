"""Term and cross-reference extraction for the evidence graph. Uses no models."""

import re

from consultqa.config import BM25_PREFIX_LEN
from consultqa.text import tokenize_tr

MIN_TERM_LENGTH = 4

# Version-like identifiers such as "3.2" or "v1.0.4".
_IDENTIFIER = re.compile(r"\b[vV]?\d+(?:\.\d+)+\b")
# A number that follows a reference keyword, e.g. "Bölüm 3" or "bkz. 3.2".
_CROSS_REFERENCE = re.compile(r"\b(?:bkz|bölüm|section|see)\.?\s*(\d+(?:\.\d+)*)", re.IGNORECASE)


def extract_terms(text: str) -> set[str]:
    """Return the lowercased identifiers and the Turkish prefix tokens of length >= 4."""
    identifiers = {match.group(0).lower() for match in _IDENTIFIER.finditer(text)}
    tokens = tokenize_tr(text, prefix=BM25_PREFIX_LEN)
    words = {token for token in tokens if len(token) >= MIN_TERM_LENGTH}
    return identifiers | words


def cross_references(text: str) -> set[str]:
    """Return the section numbers that the text refers to by keyword."""
    return {match.group(1) for match in _CROSS_REFERENCE.finditer(text)}
