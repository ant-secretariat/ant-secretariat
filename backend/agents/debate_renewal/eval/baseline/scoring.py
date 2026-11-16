"""기준선 비교 실험 도구 (기획서 D10).

같은 질문·같은 근거·같은 모델로 만든 (a) 토론 (b) 단일 LLM 장단점 요약을 블라인드로 채점하고,
루브릭 점수 이득을 토큰·지연 배수로 나눠 "왜 멀티에이전트 토론인가"에 숫자로 답한다.

흐름
  1. outputs  : 문항 × 시스템("debate"|"single") 출력 + 토큰·지연   → make_blind_pack()
  2. pack     : 시스템 이름을 지우고 순서를 섞은 채점용 목록 (채점자에게 줌)
  3. grades   : 채점자 2명이 항목마다 0/1로 채점                    → score_results()
이 모듈은 LLM을 호출하지 않는다. 출력 생성은 토론 파이프라인·단일 LLM 쪽 몫이다.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).parent
SYSTEMS = ("debate", "single")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rubric(path: Path = HERE / "rubric.json") -> dict:
    doc = _load(path)
    ids = [i["id"] for i in doc["items"]]
    if not 5 <= len(ids) <= 6 or len(ids) != len(set(ids)):
        raise ValueError("루브릭은 중복 없는 5~6항목이어야 한다 (기획서 D10)")
    return doc


def load_questions(path: Path = HERE / "questions.json") -> dict:
    doc = _load(path)
    cases = doc["cases"]
    if not 30 <= len(cases) <= 50:
        raise ValueError("문항은 30~50개여야 한다 (기획서 D10)")
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("문항 id가 중복됐다")
    per_agenda: dict[str, int] = defaultdict(int)
    for c in cases:
        per_agenda[c["agenda_id"]] += 1
    if max(per_agenda.values()) - min(per_agenda.values()) > 1:
        raise ValueError(f"아젠다별 문항 수가 고르지 않다: {dict(per_agenda)}")
    return doc


def make_blind_pack(outputs: list[dict[str, Any]], seed: int) -> tuple[list[dict], dict[str, dict]]:
    """시스템 이름을 지우고 순서를 섞는다. 반환: (채점자에게 줄 pack, 정답 key). key는 채점 전에 보여주지 않는다."""
    seen = {(o["question_id"], o["system"]) for o in outputs}
    if len(seen) != len(outputs):
        raise ValueError("같은 문항·시스템 출력이 중복됐다")
    for q in {o["question_id"] for o in outputs}:
        if {s for (qq, s) in seen if qq == q} != set(SYSTEMS):
            raise ValueError(f"{q}: debate와 single 출력이 둘 다 있어야 한다")
    shuffled = list(outputs)
    random.Random(seed).shuffle(shuffled)
    pack, key = [], {}
    for n, o in enumerate(shuffled, 1):
        bid = f"B-{n:03d}"
        pack.append({"blind_id": bid, "question_id": o["question_id"], "text": o["text"]})
        key[bid] = {"question_id": o["question_id"], "system": o["system"]}
    return pack, key


def _validate_grades(grades: list[dict], key: dict, rubric_ids: list[str]) -> dict[str, list[str]]:
    graders: dict[str, list[str]] = defaultdict(list)
    for g in grades:
        if g["blind_id"] not in key:
            raise ValueError(f"알 수 없는 blind_id: {g['blind_id']}")
        if set(g["scores"]) != set(rubric_ids) or any(v not in (0, 1) for v in g["scores"].values()):
            raise ValueError(f"{g['blind_id']}/{g['grader']}: 루브릭 항목 전부에 0/1을 줘야 한다")
        graders[g["blind_id"]].append(g["grader"])
    names = {tuple(sorted(v)) for v in graders.values()}
    if len(names) != 1 or len(next(iter(names))) < 2:
        raise ValueError("모든 항목을 같은 채점자 2명 이상이 채점해야 한다")
    if set(graders) != set(key):
        raise ValueError("채점되지 않은 항목이 있다")
    return graders


def cohens_kappa(a: list[int], b: list[int]) -> Optional[float]:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else (po - pe) / (1 - pe)


def _ratio(num: float, den: float) -> Optional[float]:
    return num / den if den else None


def score_results(outputs: list[dict], grades: list[dict], key: dict, questions: dict, rubric: dict) -> dict[str, Any]:
    ids = [i["id"] for i in rubric["items"]]
    _validate_grades(grades, key, ids)
    agenda_of = {c["id"]: c["agenda_id"] for c in questions["cases"]}

    cells: dict[str, list[float]] = defaultdict(list)  # system → 채점(항목 통과 비율)
    per_item: dict[str, dict[str, list[int]]] = {s: defaultdict(list) for s in SYSTEMS}
    per_agenda: dict[str, dict[str, list[float]]] = defaultdict(lambda: {s: [] for s in SYSTEMS})
    by_grader: dict[str, dict[tuple[str, str], int]] = defaultdict(dict)
    for g in grades:
        k = key[g["blind_id"]]
        frac = sum(g["scores"].values()) / len(ids)
        cells[k["system"]].append(frac)
        per_agenda[agenda_of[k["question_id"]]][k["system"]].append(frac)
        for rid, v in g["scores"].items():
            per_item[k["system"]][rid].append(v)
            by_grader[g["grader"]][(g["blind_id"], rid)] = v

    mean = lambda xs: sum(xs) / len(xs)
    score = {s: mean(cells[s]) for s in SYSTEMS}
    gain = score["debate"] - score["single"]

    use = {s: [o for o in outputs if o["system"] == s] for s in SYSTEMS}
    token_x = _ratio(mean([o["tokens"] for o in use["debate"]]), mean([o["tokens"] for o in use["single"]]))
    latency_x = _ratio(mean([o["latency_s"] for o in use["debate"]]), mean([o["latency_s"] for o in use["single"]]))

    pairs = []
    for g1, g2 in combinations(sorted(by_grader), 2):
        keys = sorted(by_grader[g1])
        a, b = [by_grader[g1][k] for k in keys], [by_grader[g2][k] for k in keys]
        pairs.append({"graders": (g1, g2), "agreement": sum(x == y for x, y in zip(a, b)) / len(a), "kappa": cohens_kappa(a, b)})

    return {
        "score": score,
        "gain": gain,  # 루브릭 통과 비율 차이 (debate − single)
        "token_x": token_x,
        "latency_x": latency_x,
        "gain_per_token_x": _ratio(gain, token_x) if token_x else None,
        "gain_per_latency_x": _ratio(gain, latency_x) if latency_x else None,
        "per_item_pass_rate": {s: {r: mean(per_item[s][r]) for r in ids} for s in SYSTEMS},
        "per_agenda_gain": {a: mean(v["debate"]) - mean(v["single"]) for a, v in sorted(per_agenda.items())},
        "grader_agreement": pairs,
    }
