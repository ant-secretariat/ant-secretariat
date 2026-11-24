"""토론 리빌드 Solar 호출(llm.py) 테스트. 실제 API는 부르지 않는다."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from agents.debate_renewal import config
from agents.debate_renewal import llm
from agents.debate_renewal.llm import (
    LLMOutputInvalidError, LLMUnavailableError, complete_structured,
)
from agents.debate_renewal.schemas import BullOutput
from core.errors import UpstreamUnavailableError

_REQ = httpx.Request("POST", "https://api.upstage.ai/v1/chat/completions")
MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
VALID = json.dumps({
    "claims": [{"claim_id": "C1", "text": "영업이익 개선", "claim_type": "event", "evidence_ids": ["S1"]}],
    "confidence": "mid",
}, ensure_ascii=False)


def _resp(content, prompt=10, completion=5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )


class FakeClient:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


async def test_valid_output_parsed_with_usage():
    client = FakeClient(_resp(VALID))
    result = await complete_structured(MESSAGES, BullOutput, client=client, model="m")
    assert isinstance(result.output, BullOutput)
    assert result.output.claims[0].claim_id == "C1"
    assert (result.model, result.attempts) == ("m", 1)
    assert (result.prompt_tokens, result.completion_tokens) == (10, 5)
    call = client.calls[0]
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["strict"] is True
    assert call["messages"] == MESSAGES


async def test_invalid_then_valid_retries_once_with_error_note():
    client = FakeClient(_resp("{not json"), _resp(VALID))
    result = await complete_structured(MESSAGES, BullOutput, client=client, model="m")
    assert result.attempts == 2
    assert (result.prompt_tokens, result.completion_tokens) == (20, 10)  # 두 번 합산
    retry_msgs = client.calls[1]["messages"]
    assert retry_msgs[:2] == MESSAGES
    assert retry_msgs[2] == {"role": "assistant", "content": "{not json"}
    assert retry_msgs[3]["role"] == "user" and "스키마" in retry_msgs[3]["content"]


async def test_invalid_twice_raises_output_invalid():
    bad = json.dumps({"claims": [], "confidence": "mid", "extra": 1})
    client = FakeClient(_resp(bad), _resp(bad))
    with pytest.raises(LLMOutputInvalidError) as ei:
        await complete_structured(MESSAGES, BullOutput, client=client, model="m")
    assert isinstance(ei.value, UpstreamUnavailableError)
    assert len(client.calls) == 2


@pytest.mark.parametrize("exc", [
    openai.APIConnectionError(request=_REQ),
    openai.APITimeoutError(request=_REQ),
    openai.RateLimitError("rate", response=httpx.Response(429, request=_REQ), body=None),
    openai.InternalServerError("boom", response=httpx.Response(503, request=_REQ), body=None),
])
async def test_upstream_errors_map_to_503(exc):
    with pytest.raises(LLMUnavailableError) as ei:
        await complete_structured(MESSAGES, BullOutput, client=FakeClient(exc), model="m")
    assert ei.value.status == 503
    assert "다시 시도" in ei.value.message


async def test_client_errors_propagate():
    exc = openai.BadRequestError("bad schema", response=httpx.Response(400, request=_REQ), body=None)
    with pytest.raises(openai.BadRequestError):
        await complete_structured(MESSAGES, BullOutput, client=FakeClient(exc), model="m")


async def test_missing_usage_is_none():
    r = _resp(VALID)
    r.usage = None
    result = await complete_structured(MESSAGES, BullOutput, client=FakeClient(r), model="m")
    assert result.prompt_tokens is None and result.completion_tokens is None


async def test_model_and_temperature_from_env(monkeypatch):
    monkeypatch.setenv("DEBATE_RENEWAL_LLM_MODEL", "solar-mini-4")
    monkeypatch.setenv("DEBATE_RENEWAL_LLM_TEMPERATURE", "0")
    client = FakeClient(_resp(VALID))
    result = await complete_structured(MESSAGES, BullOutput, client=client)
    assert result.model == "solar-mini-4"
    assert client.calls[0]["model"] == "solar-mini-4"
    assert client.calls[0]["temperature"] == 0.0


def test_config_defaults(monkeypatch):
    for name in ("DEBATE_RENEWAL_LLM_MODEL", "DEBATE_RENEWAL_LLM_TEMPERATURE", "DEBATE_RENEWAL_LLM_TIMEOUT_S", "DEBATE_RENEWAL_LLM_MAX_RETRIES"):
        monkeypatch.delenv(name, raising=False)
    assert config.llm_model() == config.DEFAULT_MODEL == "solar-pro-4"
    assert config.llm_temperature() == 0.2
    assert config.llm_timeout_s() == 60.0
    assert config.llm_max_retries() == 2


class SlowClient:
    """동시에 몇 개가 들어와 있는지 센다."""
    def __init__(self):
        self.active = self.peak = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return _resp(VALID)


async def test_concurrent_calls_are_capped(monkeypatch):
    monkeypatch.setenv("DEBATE_RENEWAL_LLM_MAX_CONCURRENCY", "2")
    client = SlowClient()
    await asyncio.gather(*[complete_structured(MESSAGES, BullOutput, client=client, model="m") for _ in range(6)])
    assert client.peak == 2


def test_max_concurrency_default_and_invalid(monkeypatch):
    monkeypatch.delenv("DEBATE_RENEWAL_LLM_MAX_CONCURRENCY", raising=False)
    assert config.llm_max_concurrency() == 3
    monkeypatch.setenv("DEBATE_RENEWAL_LLM_MAX_CONCURRENCY", "0")
    with pytest.raises(ValueError):
        config.llm_max_concurrency()


async def test_default_client_is_reused_within_loop(monkeypatch):
    made = []
    monkeypatch.setattr(llm, "make_client", lambda: made.append(FakeClient(_resp(VALID), _resp(VALID))) or made[-1])
    await complete_structured(MESSAGES, BullOutput, model="m")
    await complete_structured(MESSAGES, BullOutput, model="m")
    assert len(made) == 1


async def test_usage_kept_when_retry_response_has_none():
    no_usage = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=VALID))], usage=None)
    client = FakeClient(_resp("{not json"), no_usage)
    result = await complete_structured(MESSAGES, BullOutput, client=client, model="m")
    assert (result.prompt_tokens, result.completion_tokens) == (10, 5)
