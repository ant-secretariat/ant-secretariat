"""단일 모드 run_debate 테스트. LLM·데이터는 가짜로 주입한다."""
from __future__ import annotations

import asyncio
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
    def __init__(self, agendas, judge_agendas=None, bull_text=None, bull_ev=None, fix_ev=None):
        self.agendas, self.judge_agendas, self.bull_text = agendas, judge_agendas or agendas, bull_text
        self.bull_ev, self.fix_ev = bull_ev, fix_ev  # 처음 Bull B1의 근거 id, 수정 요청 때 바꿀 근거 id
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kw):
        name = kw["response_format"]["json_schema"]["name"]
        self.calls.append(name)
        if name == "BullOutput":
            claims = _claims("B", 2)
            retry = "직전 출력에" in kw["messages"][-1]["content"]
            if self.bull_ev:
                claims[0]["evidence_ids"] = [self.fix_ev if retry and self.fix_ev else self.bull_ev]
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
    async def fetch(company, agenda, query, as_of):
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


async def test_events_follow_contract_names_and_payloads():
    # ADR 0009·계약 JobEvent: data_collected → claim_completed·bull_completed·bear_completed → judge_completed → verifying
    events = []
    await _run([A.VALUATION], emit=lambda e, p: events.append((e, p)))
    names = [e for e, _ in events]
    assert names == ["data_collected", "claim_completed", "claim_completed", "bull_completed",
                     "claim_completed", "bear_completed", "judge_completed", "verifying"]
    assert set(events[0][1]) == {"report_count", "news_count", "disclosure_count"}
    bull_claim = events[1][1]
    assert bull_claim["role"] == "bull" and bull_claim["agenda_id"] == "valuation"
    assert bull_claim["claim"]["claim_id"].startswith("valuation-") and bull_claim["claim"]["text"]  # 카드에 쓸 주장 내용
    assert events[4][1]["role"] == "bear" and events[4][1]["claim"]["claim_id"].startswith("valuation-")
    assert events[3][1] == {"agenda_id": "valuation", "claim_count": 2}


async def test_async_emit_is_awaited():
    seen = []

    async def emit(e, p):
        seen.append(e)
    await _run([A.VALUATION], emit=emit)
    assert "judge_completed" in seen and "verifying" in seen


async def test_fetch_evidence_gets_the_same_as_of_as_result():
    # 결과 기준일과 실제 조회 기준일이 한 값에서 나온다(#76 리뷰)
    seen = []

    async def fetch(company, agenda, query, as_of):
        seen.append(as_of)
        return [_doc("c1")]
    run, _ = await _run([A.VALUATION, A.MACRO], fetch=fetch)
    assert seen == ["2026-11-10", "2026-11-10"] == [run.result.meta.data_as_of] * 2


async def test_bundle_metrics_become_placeholders_and_are_filled():
    # 묶음의 지표는 근거 + [지표 자리표시자]가 되고, 출력의 {{per}}는 display로 바뀐다(이벤트·결과 모두)
    bundle = {"documents": {"results": [_doc("c1")]},
              "metrics": [{"metric_id": "per", "name": "PER", "value": 12.3, "display": "12.3배", "as_of": "2026-11-07",
                           "source": "derived", "reason": None, "chunk_id": "metric:005930:per:2026-11-07"}]}
    seen_prompts, events = [], []

    class Recording(FakeLLM):
        async def _create(self, **kw):
            seen_prompts.append(kw["messages"][-1]["content"])
            return await super()._create(**kw)

    async def emit(event, payload):
        events.append((event, payload))

    run, _ = await _run([A.VALUATION], llm=Recording([A.VALUATION], bull_text="PER {{per}}로 낮다"),
                        fetch=_fetcher({A.VALUATION: bundle}), emit=emit)
    assert "{{per}}" in seen_prompts[0]  # Bull 프롬프트의 자리표시자 목록
    assert [e.chunk_id for e in run.result.evidence] == ["c1", "metric:005930:per:2026-11-07"]
    assert run.result.agendas[0].bull.claims[0].text == "PER 12.3배로 낮다"
    first_claim = next(p for e, p in events if e == "claim_completed")
    assert first_claim["claim"]["text"] == "PER 12.3배로 낮다"
    assert run.l1.ok, run.l1.issues


async def test_one_agenda_failure_cancels_the_others():
    cancelled = []

    async def fetch(company, agenda, query, as_of):
        if agenda == A.VALUATION:
            raise RuntimeError("검색 실패")
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled.append(agenda)
            raise
        return []
    with pytest.raises(RuntimeError, match="검색 실패"):  # ExceptionGroup이 아니라 원래 오류 그대로(워커 error_code용)
        await _run([A.VALUATION, A.MACRO], fetch=fetch)
    assert cancelled == [A.MACRO]


async def test_judge_missing_agenda_raises():
    with pytest.raises(LLMOutputInvalidError):
        await _run([A.VALUATION, A.MACRO], llm=FakeLLM([A.VALUATION, A.MACRO], judge_agendas=[A.VALUATION]))


async def test_persistent_failure_is_retried_once_then_claim_removed():
    run, llm = await _run([A.VALUATION], llm=FakeLLM([A.VALUATION], bull_text="지금 매수하세요"))
    # 1회 수정: Bull을 다시 쓰고, 그 Bull을 반박하는 Bear와 Judge도 다시
    assert llm.calls == ["BullOutput", "BearOutput", "JudgeSingleOutput", "BullOutput", "BearOutput", "JudgeSingleOutput"]
    assert run.repaired and run.partial and run.removed_claim_ids == ["valuation-B1"]
    assert [c.claim_id for c in run.result.agendas[0].bull.claims] == ["valuation-B2"]
    # Bear가 반박한 B1이 빠지면 반박 대상을 다른 Claim으로 바꾸지 않고 L1 문제로 남긴다(처리 방법 확정 필요)
    assert [i.code for i in run.l1.issues] == ["bad_bull_claim_ref"]


async def test_gap_loop_adds_gap_fill_evidence_and_fix_keeps_claim():
    queries = []

    async def fetch(company, agenda, query, as_of):
        assert as_of == "2026-11-10"  # 보완 검색도 토론 기준일로
        queries.append(query)
        if query == "주장 1":  # 근거 없는 Claim 문장으로 보완 검색
            return [_doc("gap-1"), _doc("c1")]
        return [_doc("c1")]
    run, llm = await _run([A.VALUATION], llm=FakeLLM([A.VALUATION], bull_ev="S9", fix_ev="S2"), fetch=fetch)
    assert queries == ["삼성전자 어때", "주장 1"]
    ev = {e.evidence_id: e for e in run.result.evidence}
    assert ev["S2"].chunk_id == "gap-1" and ev["S2"].evidence_source == "gap_fill"
    assert ev["S1"].evidence_source == "original"  # 이미 있던 조각은 원래 표기 유지
    assert run.result.agendas[0].bull.claims[0].evidence_ids == ["S2"]
    assert run.repaired and not run.partial and run.l1.ok


async def test_gap_loop_with_bundle_adds_only_documents():
    # 보완 검색이 묶음을 돌려줘도 문서만 gap_fill로 더한다. 지표·블록은 첫 조회에서 이미 근거에 있다(#120·#78)
    per = {"metric_id": "per", "name": "PER", "value": 12.3, "display": "12.3배", "as_of": "2026-11-07",
           "reason": None, "chunk_id": "metric:005930:per:2026-11-07"}

    async def fetch(company, agenda, query, as_of):
        docs = [_doc("gap-1"), _doc("c1")] if query == "주장 1" else [_doc("c1")]
        return {"documents": {"results": docs}, "metrics": [per]}
    run, _ = await _run([A.VALUATION], llm=FakeLLM([A.VALUATION], bull_ev="S9", fix_ev="S3"), fetch=fetch)
    ev = {e.chunk_id: e for e in run.result.evidence}
    assert list(ev) == ["c1", "metric:005930:per:2026-11-07", "gap-1"]
    assert ev["gap-1"].evidence_source == "gap_fill" and ev["metric:005930:per:2026-11-07"].evidence_source == "original"
    assert run.repaired and run.l1.ok


async def test_clean_result_skips_repair():
    run, llm = await _run([A.VALUATION])
    assert not run.repaired and llm.calls.count("BullOutput") == 1


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
