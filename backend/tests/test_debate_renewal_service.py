"""단일 모드 run_debate 테스트. LLM·데이터는 가짜로 주입한다."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents.debate_renewal.contracts import AgendaId as A
from agents.debate_renewal.contracts import DataTier, ExcludedAgenda, PrecheckResult
from agents.debate_renewal.evidence import EvidencePool, to_evidence
from agents.debate_renewal.llm import LLMOutputInvalidError
from agents.debate_renewal.schemas import CompanyMeta, UserProfile
from agents.debate_renewal.service import run_debate

CO = CompanyMeta(ticker="005930", company="삼성전자", sector="IT", data_tier=DataTier.REPORT)


def _doc(chunk, doc_type="report", **kw):
    return {"chunk_id": chunk, "document_type": doc_type, "title": f"문서 {chunk}", "source": "교보증권",
            "author_org": "교보증권", "date": "2026-10-29T00:00:00+09:00", "url": "", "content": "본문 " * 400, **kw}


def _claims(prefix, n, ev="S1"):
    return [{"claim_id": f"{prefix}{i}", "text": f"주장 {i}", "claim_type": "event", "evidence_ids": [ev]}
            for i in range(1, n + 1)]


def _resp(payload):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False)))],
                           usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50))


class FakeLLM:
    def __init__(self, agendas, judge_agendas=None, bull_text=None):
        self.agendas, self.judge_agendas, self.bull_text = agendas, judge_agendas or agendas, bull_text
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kw):
        name = kw["response_format"]["json_schema"]["name"]
        self.calls.append(name)
        if name == "BullOutput":
            claims = _claims("B", 2)
            if self.bull_text:
                claims[0]["text"] = self.bull_text
            return _resp({"claims": claims, "confidence": "mid"})
        if name == "BearOutput":
            return _resp({"bull_claim_ref": "B1", "agreed_points": [], "claims": _claims("R", 1), "confidence": "mid"})
        return _resp({
            "agenda_verdicts": [{"agenda_id": a.value, "winner": "neutral", "reason": "근거가 엇갈림",
                                 "score": {"bull": 6, "bear": 5}} for a in self.judge_agendas],
            "overall_verdict": {"stance": "neutral", "confidence": "mid", "bull_score": 6, "bear_score": 5,
                                "final_brief": "요약", "caution": "", "points_to_check": ["재고"]},
        })


def _pre(agendas, verdict="full", **kw):
    return PrecheckResult(verdict=verdict, mode="single", allowed_agendas=agendas, dictionary_version="t", **kw)


def _fetcher(by_agenda):
    async def fetch(company, agenda, query):
        return by_agenda[agenda]
    return fetch


async def _run(agendas, llm=None, fetch=None, **kw):
    llm = llm or FakeLLM(agendas)
    fetch = fetch or _fetcher({a: [_doc("c1"), _doc(f"c-{a.value}")] for a in agendas})
    return await run_debate(query="삼성전자 어때", company=CO, precheck=_pre(agendas, **kw.pop("pre", {})),
                            fetch_evidence=fetch, trace_id="t-1", data_as_of="2026-11-10", llm_client=llm, **kw), llm


async def test_single_debate_builds_valid_result():
    agendas = [A.VALUATION, A.MACRO]
    run, llm = await _run(agendas)
    r = run.result
    assert r.meta.mode == "single" and r.meta.ticker == "005930" and r.meta.data_richness == "rich"
    assert r.meta.data_as_of == "2026-11-10" and r.meta.generated_at.endswith("+09:00")
    assert [a.id for a in r.agendas] == agendas and r.selected_agendas == agendas
    assert r.agendas[0].title and r.agendas[0].verdict.score.bull == 6
    assert r.judge.overall_verdict.stance == "neutral"
    assert run.l1.ok, run.l1.issues
    assert llm.calls.count("BullOutput") == 2 and llm.calls.count("BearOutput") == 2 and llm.calls[-1] == "JudgeSingleOutput"
    assert [u["node"] for u in run.usage].count("judge") == 1 and len(run.usage) == 5
    # 아젠다마다 B1부터 매긴 claim_id에 아젠다를 붙여 결과 전체에서 유일하게
    assert [c.claim_id for c in r.agendas[1].bull.claims] == ["macro-B1", "macro-B2"]
    assert r.agendas[1].bear.bull_claim_ref == "macro-B1"


async def test_shared_chunk_gets_one_evidence_id():
    run, _ = await _run([A.VALUATION, A.MACRO])
    ids = {e.chunk_id: e.evidence_id for e in run.result.evidence}
    assert ids == {"c1": "S1", "c-valuation": "S2", "c-macro": "S3"}


async def test_scope_and_flags_come_from_precheck():
    excluded = [ExcludedAgenda(agenda_id=A.RISK, reason="tier_limited")]
    run, _ = await _run([A.MACRO], pre={"verdict": "reduced", "excluded": excluded, "flags": ["stale_data"]})
    assert run.result.scope.verdict == "reduced" and run.result.scope.excluded == excluded
    assert run.result.flags == ["stale_data"]


async def test_events_are_node_and_claim_level():
    events = []
    run, _ = await _run([A.VALUATION], emit=lambda e, p: events.append((e, p.get("node"))))
    names = [e for e, _ in events]
    assert names[0] == "node_started" and names[-1] == "node_completed"
    assert names.count("claim_completed") == 3  # Bull 2 + Bear 1
    assert ("agenda_completed", None) in events and ("node_started", "judge") in events


async def test_async_emit_is_awaited():
    seen = []

    async def emit(e, p):
        seen.append(e)
    await _run([A.VALUATION], emit=emit)
    assert "agenda_completed" in seen


async def test_judge_missing_agenda_raises():
    with pytest.raises(LLMOutputInvalidError):
        await _run([A.VALUATION, A.MACRO], llm=FakeLLM([A.VALUATION, A.MACRO], judge_agendas=[A.VALUATION]))


async def test_l1_issues_are_returned_not_raised():
    run, _ = await _run([A.VALUATION], llm=FakeLLM([A.VALUATION], bull_text="지금 매수하세요"))
    assert not run.l1.ok
    assert "forbidden_phrase" in {i.code for i in run.l1.issues}


@pytest.mark.parametrize("pre", [
    {"verdict": "reject", "allowed_agendas": []},
    {"verdict": "full", "allowed_agendas": []},
])
async def test_rejects_unusable_precheck(pre):
    with pytest.raises(ValueError):
        await run_debate(query="q", company=CO, precheck=PrecheckResult(mode="single", dictionary_version="t", **pre),
                         fetch_evidence=_fetcher({}), trace_id="t", data_as_of=None, llm_client=FakeLLM([]))


def test_to_evidence_maps_fields_and_nulls():
    ev = to_evidence(_doc("c9", doc_type="macro_summary", author_org="", url=""), "S1")
    assert ev.document_type == "structured" and ev.author_org is None and ev.url is None
    assert ev.date == "2026-10-29" and len(ev.content_preview) == 600


def test_pool_skips_rows_without_chunk_id():
    assert EvidencePool().add([{"chunk_id": None}, _doc("c1")])[0].evidence_id == "S1"
