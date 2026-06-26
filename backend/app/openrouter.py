import json
from collections.abc import AsyncIterator

import httpx

from .config import Settings


class OpenRouterError(Exception):
    """Raised when OpenRouter returns an error or is misconfigured."""


def _headers(settings: Settings) -> dict[str, str]:
    if not settings.openrouter_api_key:
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not set. Add it to your environment / .env file."
        )
    return {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        # OpenRouter uses these for app attribution / rankings.
        "HTTP-Referer": settings.app_url,
        "X-Title": settings.app_title,
    }


def _payload(
    settings: Settings,
    messages: list[dict],
    model: str | None,
    temperature: float,
    stream: bool,
) -> dict:
    chat_messages = [{"role": "system", "content": settings.system_prompt}, *messages]
    return {
        "model": model or settings.openrouter_model,
        "messages": chat_messages,
        "temperature": temperature,
        "stream": stream,
    }


async def chat_completion(
    settings: Settings,
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
) -> tuple[str, str]:
    """Non-streaming completion. Returns (reply_text, model_used)."""
    payload = _payload(settings, messages, model, temperature, stream=False)
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers=_headers(settings),
            json=payload,
        )
    if resp.status_code != 200:
        raise OpenRouterError(f"OpenRouter error {resp.status_code}: {resp.text}")

    data = resp.json()
    try:
        reply = data["choices"][0]["message"]["content"]
        used_model = data.get("model", payload["model"])
    except (KeyError, IndexError) as exc:
        raise OpenRouterError(f"Unexpected OpenRouter response: {data}") from exc
    return reply, used_model


async def stream_chat_completion(
    settings: Settings,
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    """Streaming completion. Yields content text chunks as they arrive."""
    payload = _payload(settings, messages, model, temperature, stream=True)
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        async with client.stream(
            "POST",
            f"{settings.openrouter_base_url}/chat/completions",
            headers=_headers(settings),
            json=payload,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise OpenRouterError(
                    f"OpenRouter error {resp.status_code}: {body.decode(errors='ignore')}"
                )

            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[len("data: ") :].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content
