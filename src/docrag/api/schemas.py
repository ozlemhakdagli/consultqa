"""Pydantic request and response models for the HTTP API."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# Whitespace-stripped text of 1 to 500 characters
BoundedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
# Whitespace-stripped collection name of 1 to 80 characters
CollectionName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]


class CreateCollection(BaseModel):
    """Body of a collection creation request."""

    name: CollectionName


class AskRequest(BaseModel):
    """Body of a question. ``k`` is the number of passages the LLM reader sees."""

    question: BoundedText
    preset: str = "L5"
    k: int | None = Field(default=None, ge=1, le=20)


class SearchRequest(BaseModel):
    """Body of a passage search request."""

    query: BoundedText
    k: int = Field(default=5, ge=1, le=20)


class Citation(BaseModel):
    """A passage that an answer cites, with its number in the answer's ``[n]`` markers."""

    number: int
    chunk_id: str
    doc_id: str
    heading_path: list[str]
    text: str


class TraceItem(BaseModel):
    """One ranked chunk as it left one stage of retrieval."""

    stage: str
    chunk_id: str
    rank: int
    score: float
    score_type: str
    channel: str


class AskResponse(BaseModel):
    """Answer to a question, its citations and the retrieval trace. ``answer`` is None when none."""

    answer: str | None
    citations: list[Citation]
    trace: list[TraceItem]
    preset: str
    latency_ms: float


class SearchResponse(BaseModel):
    """Ranked passages for a search query."""

    hits: list[TraceItem]
    preset: str
    latency_ms: float
