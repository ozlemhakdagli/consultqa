"""The words a non-technical reader must not meet on the page. The static and the browser
plain-language checks share this list."""

import re

# Display name -> pattern, matched without regard to case. "graf" is matched only at the start of
# a word, so that "paragraf" and "fotoğraf" are not reported.
FORBIDDEN: dict[str, str] = {
    "koleksiyon": r"koleksiyon",
    "parça": r"parça",
    "pasaj": r"pasaj",
    "indeks": r"indeks",
    "dizin": r"\bdizin",
    "LLM": r"llm",
    "L2 to L5": r"\bL[2-5]\b",
    "+llm": r"\+llm",
    "token": r"token",
    "RRF": r"\brrf\b",
    "graf": r"\bgraf",
    "önbellek": r"önbellek",
    "PageRank": r"pagerank",
    "BM25": r"bm25",
    "kosinüs": r"kosinüs",
    "Qdrant": r"qdrant",
    "vektör": r"vektör",
    "model": r"\bmodel",
    "sunucu": r"sunucu",
}
_PATTERNS = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in FORBIDDEN.items()}


def find_forbidden(text: str) -> list[str]:
    """The display names of the forbidden words that occur in ``text``, sorted."""
    return sorted(name for name, pattern in _PATTERNS.items() if pattern.search(text))
