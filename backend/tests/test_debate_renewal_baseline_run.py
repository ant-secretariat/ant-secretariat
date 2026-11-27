"""기준선 출력 생성기 테스트. 데이터·LLM은 가짜로 넣는다."""
from __future__ import annotations

import json

import pytest
from types import SimpleNamespace

from agents.debate_renewal.contracts import AgendaId, DataTier
from agents.debate_renewal.eval.baseline.render import render_single
from agents.debate_renewal.eval.baseline.run import CaseContext, run_all
from agents.debate_renewal.eval.baseline.scoring import make_blind_pack
from agents.debate_renewal.eval.baseline.single import SingleOutput, single_messages
from agents.debate_renewal.schemas import CompanyMeta

CO = CompanyMeta(ticker="005930", company="삼성전자", sector="IT", data_tier=DataTier.REPORT)
CASES = [
    {"id": "q-val-01", "agenda_id": "valuation", "ticker": "005930", "company": "삼성전자", "query": "비싸?", "as_of": "2026-11-10"},
    {"id": "q-mac-01", "agenda_id": "macro", "ticker": "005930", "company": "삼성전자", "query": "업황은?", "as_of": "2026-11-10"},
]


def _claim(cid, text="주장"):
    return {"claim_id": cid, "text": text, "claim_type": "event", "evidence_ids": ["S1"]}


def _resp(payload):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False)))],
                           usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20))


class FakeLLM:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kw):
        name = kw["response_format"]["json_schema"]["name"]
        user = kw["messages"][-1]["content"]
        if self.fail_on and self.fail_on in user:
            raise RuntimeError("boom")
        if name == "BullOutput":
            return _resp({"claims": [_claim("B1")], "confidence": "mid"})
        if name == "BearOutput":
            return _resp({"bull_claim_ref": "B1", "agreed_points": ["실적 개선은 맞다"],
                          "claims": [_claim("R1", "Bull은 개선을 보지만 재고가 늘었다")], "confidence": "mid"})
        if name == "SingleOutput":
            return _resp({"positives": [_claim("P1")], "negatives": [_claim("N1")], "conflicts": [],
                          "summary": "요약", "confidence": "mid"})
        agenda = "valuation" if "valuation ·" in user else "macro"
        return _resp({"agenda_verdicts": [{"agenda_id": agenda, "winner": "neutral", "reason": "엇갈림",
                                           "score": {"bull": 5, "bear": 5}}],
                      "overall_verdict": {"stance": "neutral", "confidence": "mid", "bull_score": 5, "bear_score": 5,
                                          "final_brief": "종합", "caution": "", "points_to_check": []}})


def _loader(seen):
    async def load(case, as_of):
        seen.append((case["id"], as_of))
        rows = [{"chunk_id": f"{case['id']}-c1", "document_type": "report", "title": "t", "source": "s",
                 "date": "2026-11-01", "content": "본문"}]
        per = {"metric_id": "per", "name": "PER", "value": 12.3, "display": "12.3배", "as_of": "2026-11-07",
               "reason": None, "chunk_id": "metric:005930:per:2026-11-07"}
        bundle = {"documents": {"results": rows}, "metrics": [per]}  # get_agent_context 묶음 모양
        return CaseContext(company=CO, rows=bundle, search={"query": case["query"], "keyword_query": f"{case['query']} 키워드",
                                                       "document_types": ["report"], "mode": "hybrid", "top_k": 5, "as_of": as_of})
    return load


def _jsonl(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


async def test_run_all_writes_both_systems_with_same_evidence(tmp_path):
    seen = []
    summary = await run_all(CASES, tmp_path, _loader(seen), "tag-v1", llm_client=FakeLLM())
    assert summary == {"attempted": 2, "failed": 0, "skipped": 0}
    assert seen == [("q-val-01", "2026-11-10"), ("q-mac-01", "2026-11-10")]  # 문항 as_of로 근거 고정
    outputs = _jsonl(tmp_path / "outputs.jsonl")
    assert [(o["question_id"], o["system"]) for o in outputs] == [
        ("q-val-01", "debate"), ("q-val-01", "single"), ("q-mac-01", "debate"), ("q-mac-01", "single")]
    assert outputs[0]["tokens"] == 360 and outputs[1]["tokens"] == 120  # 토론 3회 vs 단일 1회
    rec = _jsonl(tmp_path / "evidence_records.jsonl")[0]
    assert rec["snapshot_tag"] == "tag-v1"
    assert rec["evidence_chunk_ids"] == ["q-val-01-c1", "metric:005930:per:2026-11-07"]
    # 지표·블록 근거는 값까지 남긴다(#114)
    assert rec["metric_displays"] == {"per": "12.3배"} and "12.3배" in rec["structured"][0]["content"]
    assert rec["search"] == {"query": "비싸?", "keyword_query": "비싸? 키워드", "document_types": ["report"],
                             "mode": "hybrid", "top_k": 5}  # 검색 방식(#106)이 기록에 남는다
    pack, key = make_blind_pack(outputs, seed=1)  # 채점 pack까지 이어진다
    assert len(pack) == 4


async def test_blind_text_has_same_sections_and_no_role_names(tmp_path):
    await run_all(CASES[:1], tmp_path, _loader([]), "t", llm_client=FakeLLM())
    debate, single = (o["text"] for o in _jsonl(tmp_path / "outputs.jsonl"))
    heads = lambda t: [line for line in t.splitlines() if line.startswith("## ")]
    assert heads(debate) == heads(single) == ["## 긍정 요인", "## 부정 요인", "## 엇갈리는 점", "## 종합", "## 근거 목록"]
    assert "Bull" not in debate and "Bear" not in debate and "긍정론은" in debate


async def test_resume_skips_done_and_failures_are_isolated(tmp_path):
    await run_all(CASES[:1], tmp_path, _loader([]), "t", llm_client=FakeLLM())
    seen = []
    summary = await run_all(CASES, tmp_path, _loader(seen), "t", llm_client=FakeLLM(fail_on="업황은?"))
    assert summary == {"attempted": 1, "failed": 1, "skipped": 1}
    assert seen == [("q-mac-01", "2026-11-10")]
    assert _jsonl(tmp_path / "failures.jsonl")[0]["question_id"] == "q-mac-01"


async def test_unfrozen_run_passes_no_as_of(tmp_path):
    seen = []
    await run_all(CASES[:1], tmp_path, _loader(seen), "t", freeze_as_of=False, llm_client=FakeLLM())
    assert seen == [("q-val-01", None)]


def test_single_prompt_has_question_and_shared_rules():
    msgs = single_messages(CO, AgendaId.RISK, "위험은?", [])
    assert "[질문] 위험은?" in msgs[1]["content"] and "[공통 원칙]" in msgs[0]["content"]
    assert "근거 없음" in msgs[1]["content"]


def test_role_names_get_matching_particles():
    from agents.debate_renewal.eval.baseline.render import _neutral
    assert _neutral("Bear가 인용한 S1과 Bull은, Bear 측을 Bull와") == "부정론이 인용한 S1과 긍정론은, 부정론을 긍정론과"
    assert _neutral("Bulls Bearing") == "Bulls Bearing"  # 다른 영어 단어는 그대로


def test_render_single_marks_empty_sections():
    out = SingleOutput(positives=[], negatives=[], conflicts=[], summary="", confidence="low")
    text = render_single("q", out, [])
    assert text.count("(없음)") == 5


def test_case_context_keeps_search_mode_and_rejects_partial_search_failure():
    from agents.debate_renewal.eval.baseline.run import case_context
    case = CASES[0]
    docs = {"keyword_query": "비싸? 실적 밸류에이션 목표주가", "document_types": ["report"], "mode": "hybrid",
            "results": [{"chunk_id": "c1"}]}
    ctx = case_context(case, {"data_tier": "report", "as_of": "2026-11-10", "documents": docs}, "반도체", "2026-11-10")
    assert ctx.search["keyword_query"] == docs["keyword_query"] and ctx.search["document_types"] == ["report"]
    assert ctx.company.sector == "반도체" and ctx.rows["documents"]["results"] == [{"chunk_id": "c1"}]  # 묶음 그대로
    failed = {**docs, "reason": "search_unavailable", "failed_types": ["news"]}
    with pytest.raises(RuntimeError, match="문서 검색 실패"):
        case_context(case, {"data_tier": "report", "documents": failed}, None, "2026-11-10")
