import json

import pytest

from agents.debate_renewal.eval.baseline.scoring import (
    cohens_kappa, load_questions, load_rubric, make_blind_pack, score_results,
)

RUBRIC = load_rubric()
IDS = [i["id"] for i in RUBRIC["items"]]


def mini_questions():
    return {"cases": [{"id": "q1", "agenda_id": "valuation"}, {"id": "q2", "agenda_id": "risk"}]}


def outputs():
    out = []
    for q in ("q1", "q2"):
        out.append({"question_id": q, "system": "debate", "text": f"{q} 토론", "tokens": 3000, "latency_s": 60})
        out.append({"question_id": q, "system": "single", "text": f"{q} 단일", "tokens": 1000, "latency_s": 20})
    return out


def grade(pack, key, passes):
    """passes: system → 통과시킬 항목 수. 두 채점자가 같게 채점."""
    gs = []
    for p in pack:
        n = passes[key[p["blind_id"]]["system"]]
        scores = {r: int(i < n) for i, r in enumerate(IDS)}
        gs += [{"blind_id": p["blind_id"], "grader": g, "scores": dict(scores)} for g in ("a", "b")]
    return gs


def test_shipped_files_satisfy_the_spec():
    q = load_questions()
    assert 30 <= len(q["cases"]) <= 50
    assert 5 <= len(RUBRIC["items"]) <= 6
    assert "flow" not in {c["agenda_id"] for c in q["cases"]}  # 비활성 아젠다는 제외


def test_blind_pack_hides_system_and_is_reproducible():
    pack, key = make_blind_pack(outputs(), seed=7)
    assert len(pack) == 4 and all(set(p) == {"blind_id", "question_id", "text"} for p in pack)
    assert {v["system"] for v in key.values()} == {"debate", "single"}
    assert make_blind_pack(outputs(), seed=7) == (pack, key)


def test_blind_pack_requires_both_systems_per_question():
    with pytest.raises(ValueError):
        make_blind_pack([o for o in outputs() if not (o["question_id"] == "q2" and o["system"] == "single")], seed=1)


def test_gain_and_cost_ratios():
    pack, key = make_blind_pack(outputs(), seed=1)
    r = score_results(outputs(), grade(pack, key, {"debate": 6, "single": 3}), key, mini_questions(), RUBRIC)
    assert r["score"] == {"debate": 1.0, "single": 0.5} and r["gain"] == 0.5
    assert r["token_x"] == 3.0 and r["latency_x"] == 3.0
    assert r["gain_per_token_x"] == pytest.approx(0.5 / 3)
    assert r["per_agenda_gain"] == {"risk": 0.5, "valuation": 0.5}
    assert r["per_item_pass_rate"]["single"]["R1"] == 1.0 and r["per_item_pass_rate"]["single"]["R6"] == 0.0


def test_grader_agreement_is_perfect_when_graders_match():
    pack, key = make_blind_pack(outputs(), seed=1)
    r = score_results(outputs(), grade(pack, key, {"debate": 5, "single": 2}), key, mini_questions(), RUBRIC)
    assert r["grader_agreement"][0]["agreement"] == 1.0 and r["grader_agreement"][0]["kappa"] == 1.0


def test_kappa_is_zero_for_chance_level_and_none_when_undefined():
    assert cohens_kappa([1, 1, 0, 0], [1, 0, 1, 0]) == 0
    assert cohens_kappa([1, 1], [1, 1]) is None


def test_grades_must_cover_every_item_with_binary_scores():
    pack, key = make_blind_pack(outputs(), seed=1)
    gs = grade(pack, key, {"debate": 6, "single": 3})
    bad = [dict(g) for g in gs]
    bad[0]["scores"] = {**bad[0]["scores"], "R1": 2}
    with pytest.raises(ValueError):
        score_results(outputs(), bad, key, mini_questions(), RUBRIC)
    with pytest.raises(ValueError):  # 한 항목이 채점되지 않음
        score_results(outputs(), gs[:-2], key, mini_questions(), RUBRIC)


def test_unbalanced_agendas_are_rejected(tmp_path):
    cases = [{"id": f"q{i}", "agenda_id": "valuation"} for i in range(35)] + [{"id": "z", "agenda_id": "risk"}]
    p = tmp_path / "q.json"
    p.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_questions(p)
