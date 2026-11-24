"""기준선 출력 생성기 (기획서 D10): 문항마다 (a) 토론 (b) 단일 LLM 출력을 같은 근거로 만든다.

    cd backend
    python -m agents.debate_renewal.eval.baseline.run --out <폴더> [--ids q-val-01,q-mac-01] [--limit 2]
    python -m agents.debate_renewal.eval.baseline.run --out <폴더> --pack-seed 20261126   # 끝나면 채점 pack

- 같은 근거: 문항마다 `get_agent_context(as_of=문항 as_of)`를 한 번 불러 그 조각을 두 시스템에 똑같이 준다.
  쓴 chunk_id는 evidence_records.jsonl에 snapshot_tag와 함께 남긴다(본문은 남기지 않음, 수경 #28 제안).
- 출력 폴더는 git에 올리지 않는다. outputs.jsonl에는 근거 본문 일부가 들어간 채점용 텍스트가 있다.
- 이어서 돌리기: 두 시스템 출력이 이미 있는 문항은 건너뛴다. 한 문항 실패는 failures.jsonl에 남기고 다음으로 간다.
- 데이터 함수는 기본 로더 안에서만 import한다(테스트는 가짜 로더를 넣는다).
- 알고 쓸 것(수경 #77 리뷰): `data_tier`는 오늘 기준 건수로 계산된다(과거 시점 계산은 #84 이후). 뉴스는 11/10 하루치가 비어 있다.
  리포트는 11/10까지 적재 완료(11/24), 11/9 LIG디펜스앤에어로스페이스 1건은 PDF 처리 실패로 빠진 채 고정.
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from agents.debate_renewal.contracts import AgendaId, PrecheckResult
from agents.debate_renewal.eval.baseline.render import render_debate, render_single
from agents.debate_renewal.eval.baseline.scoring import load_questions, make_blind_pack
from agents.debate_renewal.eval.baseline.single import SINGLE_PROMPT_VERSION, SingleOutput, single_messages
from agents.debate_renewal.evidence import EvidencePool
from agents.debate_renewal.llm import complete_structured
from agents.debate_renewal.prompts import PROMPT_VERSION
from agents.debate_renewal.schemas import CompanyMeta
from agents.debate_renewal.service import run_debate

logger = logging.getLogger(__name__)

TOP_K = 5  # get_agent_context(agent_type="debate")의 문서 검색 개수
MAX_FAILURE_RATE = 0.1


@dataclass
class CaseContext:
    company: CompanyMeta
    rows: list[dict]
    search: dict  # query·mode·top_k


ContextLoader = Callable[[dict, Optional[str]], Awaitable[CaseContext]]


def _tokens(usages: list[dict]) -> int:
    return sum((u.get("prompt_tokens") or 0) + (u.get("completion_tokens") or 0) for u in usages)


async def run_case(case: dict, ctx: CaseContext, snapshot_tag: str, *, llm_client: Any = None) -> tuple[dict, list[dict]]:
    agenda = AgendaId(case["agenda_id"])
    query = case["query"]
    evidence = EvidencePool().add(ctx.rows)
    record = {"question_id": case["id"], "snapshot_tag": snapshot_tag, "ticker": case["ticker"],
              "as_of": ctx.search.get("as_of"), "search": {k: ctx.search.get(k) for k in ("query", "mode", "top_k")},
              "evidence_chunk_ids": [e.chunk_id for e in evidence]}

    async def same_rows(*_):
        return ctx.rows

    started = time.perf_counter()
    run = await run_debate(
        query=query, company=ctx.company, fetch_evidence=same_rows, trace_id=f"baseline-{case['id']}",
        precheck=PrecheckResult(verdict="full", mode="single", allowed_agendas=[agenda], dictionary_version="baseline"),
        data_as_of=ctx.search.get("as_of"), llm_client=llm_client)
    debate_s = time.perf_counter() - started
    if [e.chunk_id for e in run.result.evidence] != record["evidence_chunk_ids"]:
        raise RuntimeError("토론과 단일 LLM의 근거가 다르다")  # 같은 근거가 실험의 전제

    single = await complete_structured(single_messages(ctx.company, agenda, query, evidence), SingleOutput,
                                       client=llm_client)
    outputs = [
        {"question_id": case["id"], "system": "debate", "text": render_debate(query, run.result),
         "tokens": _tokens(run.usage), "latency_s": round(debate_s, 2), "model": run.result.meta.model,
         "prompt_version": PROMPT_VERSION, "l1_ok": run.l1.ok, "l1_codes": sorted({i.code for i in run.l1.issues})},
        {"question_id": case["id"], "system": "single", "text": render_single(query, single.output, evidence),
         "tokens": (single.prompt_tokens or 0) + (single.completion_tokens or 0),
         "latency_s": round(single.latency_ms / 1000, 2), "model": single.model, "prompt_version": SINGLE_PROMPT_VERSION},
    ]
    return record, outputs


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append(path: Path, rows: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


async def run_all(cases: list[dict], out: Path, loader: ContextLoader, snapshot_tag: str, *,
                  freeze_as_of: bool = True, llm_client: Any = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    done = {}
    for o in _read_jsonl(out / "outputs.jsonl"):
        done.setdefault(o["question_id"], set()).add(o["system"])
    todo = [c for c in cases if done.get(c["id"]) != {"debate", "single"}]
    failed = 0
    for n, case in enumerate(todo, 1):
        try:
            ctx = await loader(case, case["as_of"] if freeze_as_of else None)
            record, outputs = await run_case(case, ctx, snapshot_tag, llm_client=llm_client)
        except Exception as exc:  # 한 문항 실패는 격리한다(AGENTS.md 8)
            failed += 1
            logger.warning("baseline case failed id=%s err=%s", case["id"], type(exc).__name__)
            _append(out / "failures.jsonl", [{"question_id": case["id"], "error": type(exc).__name__, "detail": str(exc)[:300]}])
            continue
        _append(out / "evidence_records.jsonl", [record])
        _append(out / "outputs.jsonl", outputs)
        print(f"[{n}/{len(todo)}] {case['id']} debate {outputs[0]['latency_s']}s / single {outputs[1]['latency_s']}s")
    return {"attempted": len(todo), "failed": failed, "skipped": len(cases) - len(todo)}


async def default_loader(case: dict, as_of: Optional[str]) -> CaseContext:
    import core.config  # noqa: F401  backend/.env
    import crawling.config.settings  # noqa: F401  data-pipeline/.env
    from processing.functions.get_agent_context import get_agent_context
    from processing.functions.resolve_company import resolve_company

    # 종목코드 정확 일치로 찾는다. 회사 이름이 다른 종목으로 잡히면 data_status가 어긋나 ValueError(#77 리뷰)
    resolved = await asyncio.to_thread(resolve_company, case["ticker"])
    kwargs = {"as_of": as_of} if as_of else {}
    ctx = await asyncio.to_thread(get_agent_context, ticker=case["ticker"], agent_type="debate", query=case["query"],
                                  intent=case["agenda_id"], data_status=resolved.get("data_status"), **kwargs)
    docs = ctx.get("documents") or {}
    company = CompanyMeta(ticker=case["ticker"], company=case["company"], sector=resolved.get("sector") or "알 수 없음",
                          data_tier=ctx["data_tier"])
    return CaseContext(company=company, rows=list(docs.get("results") or []),
                       search={"query": case["query"], "mode": docs.get("mode"), "top_k": TOP_K, "as_of": ctx.get("as_of", as_of)})


def _as_of_supported() -> bool:
    from processing.functions.get_agent_context import get_agent_context
    return "as_of" in inspect.signature(get_agent_context).parameters


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="기준선 출력 생성 (토론 vs 단일 LLM)")
    p.add_argument("--out", required=True, type=Path, help="출력 폴더 (git 밖에 둘 것)")
    p.add_argument("--ids", help="쉼표로 구분한 문항 id")
    p.add_argument("--limit", type=int)
    p.add_argument("--ignore-as-of", action="store_true", help="as_of 없이 오늘 기준으로 (스모크용, 기준선 수치에 쓰지 않음)")
    p.add_argument("--pack-seed", type=int, help="모든 문항이 끝났으면 채점 pack·key를 만든다")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    questions = load_questions()
    cases = questions["cases"]
    if args.ids:
        wanted = set(args.ids.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    if args.limit:
        cases = cases[: args.limit]
    if not args.ignore_as_of and not _as_of_supported():
        print("get_agent_context에 as_of 인자가 없습니다(#75 머지 필요). 스모크는 --ignore-as-of", file=sys.stderr)
        return 2
    tag = questions["snapshot_tag"] if not args.ignore_as_of else f"{questions['snapshot_tag']}-unfrozen"
    summary = asyncio.run(run_all(cases, args.out, default_loader, tag, freeze_as_of=not args.ignore_as_of))
    print(json.dumps(summary, ensure_ascii=False))

    if args.pack_seed is not None:
        pack, key = make_blind_pack(_read_jsonl(args.out / "outputs.jsonl"), args.pack_seed)
        (args.out / "pack.json").write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
        (args.out / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"pack.json {len(pack)}개 (채점자에게), key.json은 채점 끝날 때까지 공유 금지")
    attempted = summary["attempted"]
    return 1 if attempted and summary["failed"] / attempted > MAX_FAILURE_RATE else 0


if __name__ == "__main__":
    raise SystemExit(main())
