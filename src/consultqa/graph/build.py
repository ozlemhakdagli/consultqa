"""Evidence graph: an undirected, weighted, LLM-free graph over chunks, sections and terms."""

from __future__ import annotations

import io
import json
import math
import struct
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import scipy.sparse

from consultqa.graph.terms import cross_references, extract_terms
from consultqa.models import Chunk

STRUCTURE_WEIGHT = 1.0  # chunk to its section, and section to its parent section
NEXT_CHUNK_WEIGHT = 0.5  # chunk to the following chunk of the same document
CROSS_REFERENCE_WEIGHT = 1.0
MIN_TERM_DF = 2


@dataclass
class EvidenceGraph:
    """A symmetric weighted graph. Rows and columns of ``adjacency`` follow ``nodes``.

    Node names are ``c:<chunk_id>``, ``s:<section_id>`` and ``t:<term>``.
    """

    chunk_ids: list[str]
    nodes: list[str]
    node_index: dict[str, int]
    adjacency: scipy.sparse.csr_matrix

    def to_bytes(self) -> bytes:
        """Serialise as a 4-byte big-endian header length, a JSON header, then the matrix."""
        header = json.dumps(
            {"chunk_ids": self.chunk_ids, "nodes": self.nodes}, ensure_ascii=False
        ).encode("utf-8")
        matrix = io.BytesIO()
        scipy.sparse.save_npz(matrix, self.adjacency)
        return struct.pack(">I", len(header)) + header + matrix.getvalue()

    @classmethod
    def from_bytes(cls, data: bytes) -> EvidenceGraph:
        """Inverse of ``to_bytes``. Never unpickles anything."""
        (header_length,) = struct.unpack(">I", data[:4])
        header = json.loads(data[4 : 4 + header_length].decode("utf-8"))
        adjacency = scipy.sparse.load_npz(io.BytesIO(data[4 + header_length :])).tocsr()
        nodes = list(header["nodes"])
        return cls(
            chunk_ids=list(header["chunk_ids"]),
            nodes=nodes,
            node_index={name: index for index, name in enumerate(nodes)},
            adjacency=adjacency,
        )


def build_graph(chunks: Sequence[Chunk]) -> EvidenceGraph:
    """Build the evidence graph over ``chunks``. Node order follows the input order."""
    chunk_list = list(chunks)
    total = len(chunk_list)
    nodes: list[str] = []
    node_index: dict[str, int] = {}
    rows: list[int] = []
    cols: list[int] = []
    weights: list[float] = []

    def node(name: str) -> int:
        if name not in node_index:
            node_index[name] = len(nodes)
            nodes.append(name)
        return node_index[name]

    def connect(left: str, right: str, weight: float) -> None:
        i, j = node(left), node(right)
        rows.extend((i, j))
        cols.extend((j, i))
        weights.extend((weight, weight))

    for chunk in chunk_list:
        node(f"c:{chunk.chunk_id}")

    # Chunk to section, and section to parent section. The document root has no parent.
    section_links: set[tuple[str, str]] = set()
    for chunk in chunk_list:
        connect(f"c:{chunk.chunk_id}", f"s:{chunk.section_id}", STRUCTURE_WEIGHT)
        path = chunk.heading_path
        for depth in range(len(path), 0, -1):
            child = _section_id(chunk.doc_id, path[:depth])
            parent = _section_id(chunk.doc_id, path[: depth - 1])
            section_links.add((child, parent))
    for child, parent in sorted(section_links):
        connect(f"s:{child}", f"s:{parent}", STRUCTURE_WEIGHT)

    # A term links chunks only if it occurs in at least 2 and at most max(2, floor(0.2 N)) chunks.
    term_sets = [extract_terms(chunk.text) for chunk in chunk_list]
    doc_freq = Counter(term for terms in term_sets for term in terms)
    max_df = max(MIN_TERM_DF, total // 5)  # floor(0.2 * N), exact in integers
    for chunk, terms in zip(chunk_list, term_sets, strict=True):
        for term in sorted(terms):
            df = doc_freq[term]
            if MIN_TERM_DF <= df <= max_df:
                weight = math.log((total + 1) / (df + 1)) + 1.0
                connect(f"c:{chunk.chunk_id}", f"t:{term}", weight)

    # Each chunk links to the chunk that follows it in the same document.
    by_position = {(chunk.doc_id, chunk.position): chunk for chunk in chunk_list}
    for chunk in chunk_list:
        following = by_position.get((chunk.doc_id, chunk.position + 1))
        if following is not None:
            connect(f"c:{chunk.chunk_id}", f"c:{following.chunk_id}", NEXT_CHUNK_WEIGHT)

    # A reference such as "Bölüm 3" links to chunks of the same document whose
    # top-level heading starts with that number.
    headed = [chunk for chunk in chunk_list if chunk.heading_path]
    for chunk in chunk_list:
        for number in sorted(cross_references(chunk.text)):
            for target in headed:
                if (
                    target.doc_id == chunk.doc_id
                    and target.chunk_id != chunk.chunk_id
                    and _heading_has_number(target.heading_path[0], number)
                ):
                    connect(
                        f"c:{chunk.chunk_id}",
                        f"c:{target.chunk_id}",
                        CROSS_REFERENCE_WEIGHT,
                    )

    size = len(nodes)
    adjacency = scipy.sparse.coo_matrix((weights, (rows, cols)), shape=(size, size)).tocsr()
    return EvidenceGraph(
        chunk_ids=[chunk.chunk_id for chunk in chunk_list],
        nodes=nodes,
        node_index=node_index,
        adjacency=adjacency,
    )


def _section_id(doc_id: str, heading_path: tuple[str, ...]) -> str:
    """Section identifier for a heading path, in the same format as ``Chunk.section_id``."""
    if not heading_path:
        return f"{doc_id}/"
    return f"{doc_id}/{' > '.join(heading_path)}"


def _heading_has_number(heading: str, number: str) -> bool:
    """True if the heading starts with ``number`` and then a dot, a space or the end."""
    if not heading.startswith(number):
        return False
    rest = heading[len(number) :]
    return rest == "" or rest[0] in ". "
