"""OpenRouter chat client with model fallback, JSON extraction and a daily quota guard."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .config import settings
from .db import execute, fetch_one

log = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    pass


def calls_today() -> int:
    row = fetch_one("SELECT count(*) AS n FROM llm_calls WHERE created_at > date_trunc('day', now())")
    return int(row["n"]) if row else 0


def budget_remaining() -> int:
    return max(0, settings.llm_daily_budget - calls_today())


def _log_call(purpose: str, model: Optional[str], ok: bool, started: float, error: Optional[str] = None) -> None:
    execute(
        "INSERT INTO llm_calls (purpose, model, ok, latency_ms, error) VALUES (%s,%s,%s,%s,%s)",
        (purpose, model, ok, int((time.time() - started) * 1000), (error or "")[:500] or None),
    )


def _extract_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start:text.rfind("}" if text[start] == "{" else "]") + 1])


def chat_json(
    purpose: str,
    system: str,
    user: str,
    schema: Optional[Dict[str, Any]] = None,
    max_tokens: int = 4000,
    temperature: float = 0.0,
) -> Tuple[Any, str]:
    """Return (parsed_json, model_used). Raises LLMUnavailable when out of budget or all models fail."""
    if not settings.openrouter_api_key:
        raise LLMUnavailable("OPENROUTER_API_KEY is not set")
    if budget_remaining() <= 0:
        raise LLMUnavailable("daily free-tier LLM budget used up; try again tomorrow")

    body: Dict[str, Any] = {
        "models": settings.llm_models,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        # Reasoning-capable free models otherwise spend the whole budget thinking and return no content.
        "reasoning": {"enabled": False},
    }
    if schema:
        # Strict json_schema decoding is slow or unsupported on several free models; JSON mode
        # plus the schema in the prompt is faster, and we validate the result ourselves.
        body["messages"][-1]["content"] = user + "\n\nReturn ONLY JSON matching this schema:\n" + json.dumps(schema)
        body["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "TrialMatch",
    }
    started = time.time()
    last_err = "unknown error"
    attempts: List[Dict[str, Any]] = [body]
    if schema:  # second try without response_format for models that reject it
        relaxed = dict(body)
        relaxed.pop("response_format")
        attempts.append(relaxed)

    for payload in attempts:
        try:
            resp = httpx.post(f"{settings.openrouter_base_url}/chat/completions", json=payload,
                              headers=headers, timeout=httpx.Timeout(90, connect=10))
            data = resp.json()
            if resp.status_code >= 400 or "error" in data:
                last_err = json.dumps(data.get("error", data))[:400]
                continue
            model = data.get("model", "?")
            content = data["choices"][0]["message"].get("content") or ""
            parsed = _extract_json(content)
            _log_call(purpose, model, True, started)
            return parsed, model
        except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            log.warning("LLM attempt failed: %s", last_err)
    _log_call(purpose, None, False, started, last_err)
    raise LLMUnavailable(last_err)
