import json
from collections import Counter

import pytest

from agents.debate_renewal.eval.refusal import DEFAULT_PATH, evaluate, load_cases

# rs-0.1.1 기준선 (사전 kw-0.1.1). 사전을 고쳐 수치가 좋아지면 이 값도 같은 PR에서 낮춘다.
# rs-0.1.0(35% = 7/20, 6/27)에서 flow 2문항을 정상 질의로 옮겨 분모만 바뀌었다 (실패 문항은 같은 7건·6건).
BASELINE_WRONG_ANSWER = 7 / 18
BASELINE_OVER_REFUSAL = 6 / 29


def test_set_loads_and_has_enough_cases_per_reason():
    _, cases = load_cases()
    per_reason = Counter(c["reason"] for c in cases if c["expect"] == "reject")
    assert per_reason and all(10 <= n <= 20 for n in per_reason.values()), per_reason  # 기획서 D10: 사유별 10~20건
    assert any(c["expect"] == "answer" for c in cases)  # 과잉 거절 확인용 경계 질의


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
    m = evaluate(cases)
    for cat in ("off_topic", "agenda", "generic", "advice", "button_path"):
        ok, total = m["by_category"][cat]
        assert ok == total, cat


def test_metrics_do_not_regress_from_baseline():
    _, cases = load_cases()
    m = evaluate(cases)
    assert m["wrong_answer_rate"] <= BASELINE_WRONG_ANSWER + 1e-9
    assert m["over_refusal_rate"] <= BASELINE_OVER_REFUSAL + 1e-9


def test_set_file_is_utf8_json():
    assert json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))["version"] == "rs-0.1.1"


def test_report_carries_dictionary_version_and_per_reason_accuracy():
    version, cases = load_cases()
    m = evaluate(cases)
    assert m["dictionary_version"].startswith("kw-")
    assert set(m["by_reason"]) == {"out_of_scope_topic"}
    assert m["wrong_reason_rate"] == 0.0
