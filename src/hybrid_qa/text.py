"""Turkish-aware text normalisation and tokenisation utilities."""

import re

_NON_ALNUM = re.compile(r"[\W_]+")


def casefold_tr(text: str) -> str:
    """Lowercase text using Turkish rules for dotted and dotless I."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def tokenize(text: str, *, prefix: int | None = None) -> list[str]:
    """Split text into lowercase Turkish tokens, optionally truncating each to a prefix."""
    tokens = [token for token in _NON_ALNUM.split(casefold_tr(text)) if token]
    if prefix is not None:
        tokens = [token[:prefix] for token in tokens]
    return tokens


def reference_tokens(text: str) -> list[str]:
    """Tokenise like the reference pipeline: plain lowercase and whitespace split."""
    return text.lower().split()
