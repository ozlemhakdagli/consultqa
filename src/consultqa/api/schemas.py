"""Pydantic request and response models for the HTTP API."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from consultqa.api.services import DEFAULT_PRESET

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
    """Body of a question. ``k`` is the number of passages the LLM reader sees. ``doc_id`` limits
    the question to one document of the folder."""

    question: BoundedText
    preset: str = DEFAULT_PRESET
    k: int | None = Field(default=None, ge=1, le=20)
    doc_id: str | None = Field(default=None, max_length=64)


class SearchRequest(BaseModel):
    """Body of a passage search request. ``doc_id`` limits the search to one document."""

    query: BoundedText
    k: int = Field(default=5, ge=1, le=20)
    doc_id: str | None = Field(default=None, max_length=64)


class Citation(BaseModel):
    """A passage that an answer cites, with its number in the answer's ``[n]`` markers."""

    number: int
    chunk_id: str
    doc_id: str
    heading_path: list[str]
    text: str
    page: int | None


class RelatedPage(BaseModel):
    """The top passage of one page of the answer's sources, for the page to link to."""

    chunk_id: str
    doc_id: str
    page: int | None
    heading_path: list[str]


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
    related: list[RelatedPage]
    trace: list[TraceItem]
    preset: str
    latency_ms: float


class SearchResponse(BaseModel):
    """Ranked passages for a search query."""

    hits: list[TraceItem]
    preset: str
    latency_ms: float


class PresetInfo(BaseModel):
    """One method as the page sees it: whether it can be used now and, if not, why."""

    name: str
    available: bool
    reason: str | None
    uses_llm: bool


class DocumentTextPage(BaseModel):
    """The passages of one page of a document; ``page`` is None for a text or Markdown file."""

    page: int | None
    text: str


class DocumentText(BaseModel):
    """The passages of a document in reading order, grouped by page."""

    pages: list[DocumentTextPage]


class Capabilities(BaseModel):
    """What the page may offer: readiness, upload limits and the methods that can be used."""

    ready: bool
    llm_configured: bool
    max_upload_mb: float
    extensions: list[str]
    default_preset: str
    presets: list[PresetInfo]
