"""OpenAI-compatible chat client for the LLM reader.

Every failure of the endpoint (timeout, connection error, error status, unusable reply) is raised
as ``LLMUnavailable`` so that the API can answer with ``llm_unavailable``.
"""

import httpx


class LLMUnavailable(Exception):
    """The LLM endpoint timed out, could not be reached, or returned an unusable reply."""


class LLMClient:
    """Posts chat requests to ``{base_url}/v1/chat/completions`` with temperature 0."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        timeout_s: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/chat/completions"
        self._model = model
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout_s = timeout_s
        self._transport = transport

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return the content of the first choice for ``messages``.

        Raises:
            LLMUnavailable: on a timeout, a connection error, an HTTP error status, or a reply
                without ``choices[0].message.content``.
        """
        payload = {"model": self._model, "messages": messages, "temperature": 0}
        try:
            with httpx.Client(
                timeout=self._timeout_s, headers=self._headers, transport=self._transport
            ) as client:
                response = client.post(self._url, json=payload)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPError as exc:
            raise LLMUnavailable(type(exc).__name__) from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMUnavailable("malformed reply") from exc
        if not isinstance(content, str):
            raise LLMUnavailable("reply has no text content")
        return content
