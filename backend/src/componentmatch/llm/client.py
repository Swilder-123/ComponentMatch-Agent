"""One async transport, one bounded retry layer; never log provider exception bodies."""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Literal, Protocol

import httpx
import openai
from langchain_deepseek import ChatDeepSeek
from langsmith import tracing_context
from pydantic import BaseModel, ValidationError

from componentmatch.core.config import Settings
from componentmatch_contracts.agent import LLMCallRecord


class LLMFailure(Exception):
    def __init__(self, code: str, *, retryable=False, http_status=503):
        super().__init__(code)
        self.code, self.retryable, self.http_status = code, retryable, http_status


@dataclass(frozen=True)
class LLMReply:
    text: str
    finish_reason: str = "stop"
    usage: dict = field(default_factory=dict)


class JSONTransport(Protocol):
    source: Literal["deepseek", "mock"]
    model_name: str

    async def generate(self, system: str, payload: str, timeout: float) -> LLMReply: ...


class DeepSeekTransport:
    source = "deepseek"

    def __init__(self, settings: Settings, *, http_client=None, http_async_client=None):
        self.settings = settings
        self.model_name = settings.deepseek_model
        self._client = None
        self._http_client, self._http_async_client = http_client, http_async_client

    def client(self):
        if self._client is not None:
            return self._client
        s = self.settings
        if not s.deepseek_api_key or not s.deepseek_api_key.get_secret_value().strip():
            raise LLMFailure("CONFIG_MISSING")
        try:
            url = httpx.URL(s.deepseek_base_url)
        except httpx.InvalidURL:
            raise LLMFailure("LLM_CONFIG_ERROR") from None
        if url.scheme not in {"http", "https"} or not url.host or url.userinfo:
            raise LLMFailure("LLM_CONFIG_ERROR")
        if not s.deepseek_model.strip():
            raise LLMFailure("LLM_CONFIG_ERROR")
        # Native ChatDeepSeek fields verified against installed 1.1.1.
        self._client = ChatDeepSeek(
            model=s.deepseek_model,
            api_key=s.deepseek_api_key,
            base_url=s.deepseek_base_url,
            timeout=s.llm_timeout_seconds,
            max_retries=0,
            max_tokens=s.llm_max_tokens,
            streaming=False,
            http_client=self._http_client,
            http_async_client=self._http_async_client,
            extra_body={"thinking": {"type": "disabled"}},
        )
        return self._client

    async def generate(self, system, payload, timeout):
        # No .with_retry(), no SDK retries, no LangGraph retry policy. Do not upload prompts.
        with tracing_context(enabled=False):
            message = (
                await self.client()
                .bind(response_format={"type": "json_object"})
                .ainvoke(
                    [("system", system), ("human", payload)],
                    config={"callbacks": []},
                    timeout=timeout,
                )
            )
        content = message.content
        return LLMReply(
            text=content if isinstance(content, str) else "",
            finish_reason=message.response_metadata.get("finish_reason", "unknown"),
            usage=message.usage_metadata or {},
        )

    async def aclose(self):
        """Close owned SDK clients once when the application's lifespan ends."""
        client, self._client = self._client, None
        if client is not None:
            try:
                if self._http_async_client is None:
                    await client.root_async_client.close()
            finally:
                if self._http_client is None:
                    client.root_client.close()


def classify_error(exc: Exception) -> LLMFailure:
    if isinstance(exc, LLMFailure):
        return exc
    if isinstance(exc, (TimeoutError, openai.APITimeoutError, httpx.TimeoutException)):
        return LLMFailure("LLM_TIMEOUT", retryable=True)
    if isinstance(exc, openai.APIStatusError):
        code = exc.status_code
        if code in {401, 403}:
            return LLMFailure("LLM_AUTH_ERROR")
        if code == 402:
            return LLMFailure("LLM_BALANCE_ERROR")
        if code == 429:
            return LLMFailure("LLM_RATE_LIMIT", retryable=True)
        if code >= 500:
            return LLMFailure("LLM_UNAVAILABLE", retryable=True)
        return LLMFailure("LLM_CONFIG_ERROR")
    if isinstance(exc, (openai.APIConnectionError, httpx.TransportError)):
        return LLMFailure("LLM_CONNECTION_ERROR", retryable=True)
    if isinstance(exc, ValidationError):
        return LLMFailure("LLM_SCHEMA_INVALID", retryable=True)
    if isinstance(exc, (json.JSONDecodeError, ValueError)):
        return LLMFailure("LLM_JSON_INVALID", retryable=True)
    return LLMFailure("LLM_CALL_FAILED")


def load_json(text):
    def pairs(items):
        output = {}
        for key, value in items:
            if key in output:
                raise ValueError("Duplicate JSON key")
            output[key] = value
        return output

    def invalid_constant(_):
        raise ValueError("Nonfinite JSON number")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)


class JSONModel:
    def __init__(self, transport: JSONTransport, settings: Settings):
        self.transport, self.settings = transport, settings

    async def complete(
        self, schema: type[BaseModel], *, phase, system, payload, deadline, calls, validate=None
    ):
        last = LLMFailure("LLM_CALL_FAILED")
        for attempt in range(1, self.settings.llm_max_retries + 2):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LLMFailure("AGENT_TIMEOUT", http_status=504)
            started, reply = time.monotonic(), None
            timeout_scope = asyncio.timeout(min(remaining, self.settings.llm_timeout_seconds))
            try:
                async with timeout_scope:
                    reply = await self.transport.generate(
                        system,
                        json.dumps(payload, ensure_ascii=False),
                        min(remaining, self.settings.llm_timeout_seconds),
                    )
                if reply.finish_reason != "stop":
                    raise LLMFailure(
                        "LLM_TRUNCATED"
                        if reply.finish_reason in {"length", "max_tokens"}
                        else "LLM_FINISH_INVALID",
                        retryable=True,
                    )
                if not reply.text.strip():
                    raise LLMFailure("LLM_EMPTY_CONTENT", retryable=True)
                parsed = schema.model_validate(load_json(reply.text))
                if validate is not None:
                    validate(parsed)
                outcome, last = "success", None
            except Exception as exc:
                outcome, last = "error", classify_error(exc)
                # asyncio timers may fire one clock-resolution early on Windows.
                # Only an expired local timeout scope can identify our limiting request budget.
                # An SDK-raised TimeoutError may occur early and must remain LLM_TIMEOUT.
                if (
                    timeout_scope.expired() and remaining <= self.settings.llm_timeout_seconds
                ) or time.monotonic() >= deadline:
                    last = LLMFailure("AGENT_TIMEOUT", http_status=504)
            usage = reply.usage if reply is not None else {}
            calls.append(
                LLMCallRecord(
                    phase=phase,
                    attempt=attempt,
                    source=self.transport.source,
                    model_name=self.transport.model_name,
                    outcome=outcome,
                    error_code=last.code if last else None,
                    duration_ms=round((time.monotonic() - started) * 1000, 3),
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                )
            )
            if last is None:
                return parsed
            if not last.retryable or attempt > self.settings.llm_max_retries:
                raise last
            delay = min(0.25 * attempt, max(0, deadline - time.monotonic()))
            await asyncio.sleep(delay)
        raise last
