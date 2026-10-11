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


# A base URL that already ends in /v1 must not produce /v1/v1/chat/completions.
@pytest.mark.parametrize(
    "base_url",
    [
        "http://ollama:11434/v1",
        "http://ollama:11434/v1/",
        "http://ollama:11434/",
        "http://ollama:11434",
    ],
)
def test_base_url_is_normalised_to_one_chat_endpoint(base_url):
    seen: list[str] = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "tamam"}}]})

    client = LLMClient(base_url, "m", transport=httpx.MockTransport(handler))
    assert client.chat([]) == "tamam"
    assert seen == ["http://ollama:11434/v1/chat/completions"]
