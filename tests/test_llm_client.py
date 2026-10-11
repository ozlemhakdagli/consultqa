# tests/test_llm_client.py
import httpx
import pytest

from docrag.generate.llm_client import LLMClient, LLMUnavailable


def _client(handler):
    return LLMClient("http://llm:11434", "m", transport=httpx.MockTransport(handler))


def test_returns_the_message_content():
    body = {"choices": [{"message": {"content": "Cevap [1]"}}]}
    assert _client(lambda request: httpx.Response(200, json=body)).chat([]) == "Cevap [1]"


# [R5] A timeout becomes a coded, catchable error.
def test_timeout_raises_llm_unavailable():
    def handler(request):
        raise httpx.ConnectTimeout("slow")

    with pytest.raises(LLMUnavailable):
        _client(handler).chat([])


def test_server_error_raises_llm_unavailable():
    with pytest.raises(LLMUnavailable):
        _client(lambda request: httpx.Response(503)).chat([])
