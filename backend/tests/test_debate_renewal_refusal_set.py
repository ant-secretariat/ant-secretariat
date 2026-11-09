import json

import pytest

from agents.debate_renewal.eval.refusal import DEFAULT_PATH, evaluate, load_cases, split_of

# rs-0.2.0 기준선 (사전 kw-0.2.0). 사전을 고쳐 수치가 좋아지면 이 값도 같은 PR에서 낮춘다.
# 직전(kw-0.1.0)은 dev 35%/22.2%, holdout 60%/8.3%였다.
DEV_WRONG_ANSWER, DEV_OVER_REFUSAL = 0.05, 0.0
HOLDOUT_WRONG_ANSWER, HOLDOUT_OVER_REFUSAL = 0.40, 1 / 12


def test_set_loads_and_has_enough_cases_per_reason():
    _, cases = load_cases()
    for split in ("dev", "holdout"):
        sub = split_of(cases, split)
        reject = [c for c in sub if c["expect"] == "reject"]
        assert 10 <= len(reject) <= 20  # 기획서 D10: 사유별 10~20건
        assert any(c["expect"] == "answer" for c in sub)  # 과잉 거절 확인용 경계 질의


def test_bad_reason_code_is_rejected(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"version": "x", "cases": [
        {"id": "a", "category": "c", "query": "q", "expect": "reject", "reason": "not_a_code"}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(p)


def test_duplicate_ids_are_rejected(tmp_path):
    case = {"id": "a", "category": "c", "query": "q", "expect": "answer", "expect_flags": []}
    p = tmp_path / "dup.json"
    p.write_text(json.dumps({"version": "x", "cases": [case, case]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(p)


def test_plain_off_topic_and_agenda_queries_are_classified_correctly():
    _, cases = load_cases()
    m = evaluate(split_of(cases, "dev"))
    for cat in ("off_topic", "agenda", "generic", "advice", "flow_inactive", "button_path"):
        ok, total = m["by_category"][cat]
        assert ok == total, cat


def test_metrics_do_not_regress_from_baseline():
    _, cases = load_cases()
    for split, wrong, over in (
        ("dev", DEV_WRONG_ANSWER, DEV_OVER_REFUSAL),
        ("holdout", HOLDOUT_WRONG_ANSWER, HOLDOUT_OVER_REFUSAL),
    ):
        m = evaluate(split_of(cases, split))
        assert m["wrong_answer_rate"] <= wrong + 1e-9, split
        assert m["over_refusal_rate"] <= over + 1e-9, split


def test_set_file_is_utf8_json():
    assert json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))["version"] == "rs-0.2.0"
