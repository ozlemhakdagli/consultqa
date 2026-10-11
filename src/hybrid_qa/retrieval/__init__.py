"""Passage retrieval: dense (FAISS), sparse (BM25) and hybrid fusion."""

from hybrid_qa.retrieval.base import Encoder, Hit, Retriever
from hybrid_qa.retrieval.bm25 import BM25Retriever
from hybrid_qa.retrieval.dense import DenseRetriever
from hybrid_qa.retrieval.fusion import HybridRetriever

__all__ = [
    "BM25Retriever",
    "DenseRetriever",
    "Encoder",
    "Hit",
    "HybridRetriever",
    "Retriever",
]
