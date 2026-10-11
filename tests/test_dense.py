import numpy as np
import pytest

from docrag.models import Chunk
from docrag.retrieve.dense import DenseChannel, NumpyDenseBackend
from docrag.stub import HashEncoder


def test_numpy_backend_returns_the_best_match_first():
    backend = NumpyDenseBackend()
    backend.upsert(["a", "b", "c"], np.eye(3, dtype=np.float32))
    assert backend.search(np.array([0, 1, 0], dtype=np.float32), k=2)[0][0] == "b"


def test_re_upsert_replaces_and_delete_removes():
    backend = NumpyDenseBackend()
    backend.upsert(["a"], np.array([[1.0, 0.0]], dtype=np.float32))
    backend.upsert(["a"], np.array([[0.0, 1.0]], dtype=np.float32))
    backend.delete([])
    assert len(backend.search(np.array([0.0, 1.0], dtype=np.float32), k=5)) == 1
    backend.delete(["a"])
    assert backend.search(np.array([0.0, 1.0], dtype=np.float32), k=5) == []


def test_identical_text_ranks_first():
    chunks = {
        "d1#0": Chunk("d1#0", "d1", 0, (), "Sipariş modülü tablo filtreleme"),
        "d1#1": Chunk("d1#1", "d1", 1, (), "Stok modülü performans"),
    }
    encoder = HashEncoder(dim=256)
    backend = NumpyDenseBackend()
    backend.upsert(list(chunks), encoder.encode_passages([c.text for c in chunks.values()]))
    hits = DenseChannel(chunks, encoder, backend).search(chunks["d1#0"].text, k=2)
    assert hits[0].chunk.chunk_id == "d1#0"


def test_hash_encoder_is_deterministic_across_instances():
    a = HashEncoder(dim=8).encode_query("sipariş")
    b = HashEncoder(dim=8).encode_query("sipariş")
    assert np.allclose(a, b)


@pytest.mark.model
def test_real_bge_m3_encoder_dimension():
    from docrag.retrieve.dense import ENCODER_SPECS, SentenceEncoder

    vector = SentenceEncoder(ENCODER_SPECS["bge-m3"]).encode_query("sipariş")
    assert vector.shape == (1024,)


# The background loader and the ingest worker may both ask for the model: it is built once.
def test_concurrent_loads_build_the_model_once():
    import threading
    import time

    from docrag.retrieve.dense import ENCODER_SPECS, SentenceEncoder

    built: list[tuple[str, str]] = []

    def loader(model_id, revision):
        built.append((model_id, revision))
        time.sleep(0.05)  # widen the window in which a second load could start
        return object()

    encoder = SentenceEncoder(ENCODER_SPECS["bge-m3"], loader=loader)
    barrier = threading.Barrier(8)
    models: list[object] = []

    def load():
        barrier.wait()
        models.append(encoder._load())

    threads = [threading.Thread(target=load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert len(built) == 1
    assert len({id(model) for model in models}) == 1 and len(models) == 8
