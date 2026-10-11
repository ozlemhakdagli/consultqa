"""Domain models shared by ingestion, retrieval and evaluation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    """A passage of one document, in reading order, under one heading path."""

    chunk_id: str
    doc_id: str
    position: int
    heading_path: tuple[str, ...]
    text: str

    @property
    def section_id(self) -> str:
        """Identifier of the heading section that contains this chunk."""
        if not self.heading_path:
            return f"{self.doc_id}/"
        return f"{self.doc_id}/{' > '.join(self.heading_path)}"


@dataclass(frozen=True)
class Hit:
    """A scored chunk returned by one retrieval stage.

    ``score_type`` is one of ``cosine``, ``bm25``, ``ppr``, ``rrf`` or ``cross_encoder``.
    ``channel`` is one of ``dense``, ``sparse``, ``graph``, ``rrf`` or ``rerank``.
    """

    chunk: Chunk
    score: float
    score_type: str
    channel: str
