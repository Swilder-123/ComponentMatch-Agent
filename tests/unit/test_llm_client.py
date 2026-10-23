import asyncio
import json
import time

import httpx
import openai
import pytest
from componentmatch.core.config import Settings
from componentmatch.llm.client import DeepSeekTransport, JSONModel, LLMFailure, LLMReply
from componentmatch_contracts.agent import RequirementDraft


class SequenceTransport:
    source = "mock"
    model_name = "sequence-test"

    def __init__(self, replies):
        self.replies, self.count = list(replies), 0

    async def generate(self, *args):
        self.count += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def invoke(transport, *, retries=0, deadline=None):
    calls = []
    model = JSONModel(transport, Settings(llm_max_retries=retries))
    result = asyncio.run(
        model.complete(
            RequirementDraft,
            phase="parse",
            system="json",
            payload={},
            deadline=deadline or time.monotonic() + 10,
            calls=calls,
        )
    )
    return result, calls


@pytest.mark.parametrize(
    "reply,code",
    [
        (LLMReply(""), "LLM_EMPTY_CONTENT"),
        (LLMReply("{bad}"), "LLM_JSON_INVALID"),
        (LLMReply('{"quantity":true}'), "LLM_SCHEMA_INVALID"),
        (LLMReply('{"quantity":NaN}'), "LLM_JSON_INVALID"),
        (LLMReply('{"quantity":1,"quantity":2}'), "LLM_JSON_INVALID"),
        (LLMReply("{}", "length"), "LLM_TRUNCATED"),
        (LLMReply("{}", "content_filter"), "LLM_FINISH_INVALID"),
        (TimeoutError(), "LLM_TIMEOUT"),
    ],
)
def test_malformed_or_failed_model_call(reply, code):
    transport = SequenceTransport([reply])
    with pytest.raises(LLMFailure, match=code):
        invoke(transport)
    assert transport.count == 1


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (401, "LLM_AUTH_ERROR", False),
        (403, "LLM_AUTH_ERROR", False),
        (402, "LLM_BALANCE_ERROR", False),
        (400, "LLM_CONFIG_ERROR", False),
        (404, "LLM_CONFIG_ERROR", False),
        (429, "LLM_RATE_LIMIT", True),
        (500, "LLM_UNAVAILABLE", True),
    ],
)
def test_provider_error_classification_and_single_retry_layer(status, code, retryable):
    response = httpx.Response(status, request=httpx.Request("POST", "https://example.invalid"))
    error = openai.APIStatusError("secret provider error body", response=response, body={})
    transport = SequenceTransport([error, LLMReply("{}")])
    if retryable:
        result, calls = invoke(transport, retries=1)
        assert isinstance(result, RequirementDraft) and len(calls) == 2
        assert calls[0].error_code == code
    else:
        with pytest.raises(LLMFailure, match=code):
            invoke(transport, retries=1)
        assert transport.count == 1


def test_json_repair_shares_same_attempt_budget():
    transport = SequenceTransport([LLMReply("{bad}"), LLMReply("{}")])
    _, calls = invoke(transport, retries=1)
    assert transport.count == 2 and [c.outcome for c in calls] == ["error", "success"]


def test_expired_deadline_has_no_model_call():
    transport = SequenceTransport([])
    with pytest.raises(LLMFailure, match="AGENT_TIMEOUT"):
        invoke(transport, deadline=time.monotonic() - 1)
    assert transport.count == 0


def test_per_call_timeout_and_total_request_deadline_are_distinct():
    class Slow(SequenceTransport):
        async def generate(self, *args):
            self.count += 1
            await asyncio.sleep(10)
            return LLMReply("{}")

    async def check(settings, expected):
        transport = Slow([])
        model = JSONModel(transport, settings)
        calls = []
        with pytest.raises(LLMFailure, match=expected):
            await model.complete(
                RequirementDraft,
                phase="parse",
                system="json",
                payload={},
                deadline=time.monotonic() + settings.agent_timeout_seconds,
                calls=calls,
            )
        assert transport.count == 1 and len(calls) == 1

    asyncio.run(
        check(
            Settings(llm_timeout_seconds=0.01, agent_timeout_seconds=10, llm_max_retries=0),
            "LLM_TIMEOUT",
        )
    )
    asyncio.run(
        check(
            Settings(llm_timeout_seconds=10, agent_timeout_seconds=0.01, llm_max_retries=0),
            "AGENT_TIMEOUT",
        )
    )


def test_missing_key_does_not_fabricate_model_success(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    transport = DeepSeekTransport(Settings())
    with pytest.raises(LLMFailure, match="CONFIG_MISSING"):
        invoke(transport)


def test_installed_langchain_sdk_request_compatibility_without_real_network():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "offline-http-mock",
                "object": "chat.completion",
                "created": 1,
                "model": "configured-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "{}"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as async_http:
            with httpx.Client(transport=httpx.MockTransport(handler)) as sync_http:
                settings = Settings(
                    deepseek_api_key="test-only-key",
                    deepseek_model="configured-model",
                    deepseek_base_url="https://provider.example/v1",
                )
                transport = DeepSeekTransport(
                    settings, http_client=sync_http, http_async_client=async_http
                )
                calls = []
                await JSONModel(transport, settings).complete(
                    RequirementDraft,
                    phase="parse",
                    system="json",
                    payload={},
                    deadline=time.monotonic() + 10,
                    calls=calls,
                )
                assert transport.client().root_async_client.max_retries == 0
                assert calls[0].input_tokens == 3 and calls[0].output_tokens == 2

    asyncio.run(run())
    assert len(requests) == 1
    assert str(requests[0].url) == "https://provider.example/v1/chat/completions"
    payload = json.loads(requests[0].content)
    assert payload["model"] == "configured-model"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["thinking"] == {"type": "disabled"}
