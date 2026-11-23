import json

import pytest

from agents.debate_renewal.eval.baseline.scoring import (
    AGENDAS, cohens_kappa, load_questions, load_rubric, make_blind_pack, score_results,
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
    assert {c["agenda_id"] for c in q["cases"]} <= set(AGENDAS)
    assert all(c["as_of"] and c["ticker"].isdigit() and len(c["ticker"]) == 6 for c in q["cases"])


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


# ── 태은 #28 리뷰 반영 ─────────────────────────────────────
def test_every_question_passes_precheck_with_its_agenda():
    # 실험 때 토론 결과가 비지 않도록, 문항마다 라벨 아젠다가 precheck 허용 목록에 들어가야 한다
    from agents.debate_renewal.contracts import CompanyContext
    from agents.debate_renewal.eval.refusal import _TODAY, _fresh_status
    from agents.debate_renewal.precheck import precheck

    bad = []
    for c in load_questions()["cases"]:
        r = precheck(c["query"], [CompanyContext(ticker=c["ticker"], company=c["company"])],
                     data_status=_fresh_status, today=_TODAY)
        if c["agenda_id"] not in {a.value for a in r.allowed_agendas}:
            bad.append((c["id"], r.verdict, [a.value for a in r.allowed_agendas]))
    assert not bad, bad


def test_win_rate_counts_ties_as_non_wins():
    pack, key = make_blind_pack(outputs(), seed=3)
    gs = grade(pack, key, {"debate": 4, "single": 4})
    for g in gs:  # q1만 토론이 이기게
        k = key[g["blind_id"]]
        if k["question_id"] == "q1" and k["system"] == "debate":
            g["scores"] = {r: 1 for r in IDS}
    r = score_results(outputs(), gs, key, mini_questions(), RUBRIC, seed=3)
    assert (r["wins"], r["ties"], r["losses"]) == (1, 1, 0) and r["win_rate"] == 0.5


def test_result_carries_reproduction_info_and_per_item_agreement():
    pack, key = make_blind_pack(outputs(), seed=5)
    qs = {**mini_questions(), "version": "qs-test"}
    r = score_results(outputs(), grade(pack, key, {"debate": 5, "single": 2}), key, qs, RUBRIC, seed=5)
    assert (r["seed"], r["rubric_version"], r["questions_version"]) == (5, RUBRIC["version"], "qs-test")
    assert set(r["grader_agreement_per_item"]) == set(IDS)
    assert r["grader_agreement_per_item"]["R1"][0]["agreement"] == 1.0


def test_unknown_question_id_is_reported():
    pack, key = make_blind_pack(outputs(), seed=1)
    with pytest.raises(ValueError, match="question_id"):
        score_results(outputs(), grade(pack, key, {"debate": 5, "single": 2}), key,
                      {"cases": [{"id": "q1", "agenda_id": "valuation"}]}, RUBRIC)


def test_invalid_agenda_or_ticker_is_rejected(tmp_path):
    base = [{"id": f"q{i}", "agenda_id": a, "ticker": "005930"} for i, a in enumerate(AGENDAS * 6)]
    for bad in ({"agenda_id": "dividend"}, {"ticker": 5930}):
        cases = [dict(c) for c in base]
        cases[0].update(bad)
        p = tmp_path / "q.json"
        p.write_text(json.dumps({"cases": cases}), encoding="utf-8")
        with pytest.raises(ValueError):
            load_questions(p)
