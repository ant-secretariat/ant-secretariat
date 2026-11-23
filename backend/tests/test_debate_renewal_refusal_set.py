import json
from collections import Counter

import pytest

from agents.debate_renewal.eval.refusal import DEFAULT_PATH, evaluate, load_cases, split_of

# rs-0.3.1 기준선 (사전 kw-0.3.1). 사전을 고쳐 수치가 좋아지면 이 값도 같은 PR에서 낮춘다.
# kw-0.3.1(리뷰 반영)에서 dev는 flow 2문항을 정상 질의로 옮겨 분모만 바뀌었다(1/20 → 1/18).
# holdout·holdout2는 kw-0.3.0과 같은 2/10이다 (hr-08 "이 노래 어때"는 약한 신호 규칙으로 계속 거절).
# 직전(kw-0.2.0)은 dev 5%/0%, holdout 40%/8.3%, holdout2 100%/0%였다.
# holdout은 kw-0.2.0 실패를 본 뒤 규칙을 만들었으니 더는 깨끗한 검증셋이 아니고, holdout2가 새 확인용이다.
LIMITS = {  # split → (오답변율 상한, 과잉거절률 상한)
    "dev": (1 / 18, 0.0),
    "holdout": (0.20, 1 / 12),
    "holdout2": (0.20, 0.0),
}


def test_set_loads_and_has_enough_cases_per_reason():
    _, cases = load_cases()
    for split in LIMITS:
        sub = split_of(cases, split)
        per_reason = Counter(c["reason"] for c in sub if c["expect"] == "reject")
        assert per_reason and all(10 <= n <= 20 for n in per_reason.values()), (split, per_reason)  # D10: 사유별 10~20건
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
    for cat in ("off_topic", "agenda", "generic", "advice", "button_path"):
        ok, total = m["by_category"][cat]
        assert ok == total, cat


def test_metrics_do_not_regress_from_baseline():
    _, cases = load_cases()
    for split, (wrong, over) in LIMITS.items():
        m = evaluate(split_of(cases, split))
        assert m["wrong_answer_rate"] <= wrong + 1e-9, split
        assert m["over_refusal_rate"] <= over + 1e-9, split


def test_set_file_is_utf8_json():
    assert json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))["version"] == "rs-0.3.1"


def test_report_carries_dictionary_version_and_per_reason_accuracy():
    _, cases = load_cases()
    m = evaluate(split_of(cases, "dev"))
    assert m["dictionary_version"].startswith("kw-0.3")
    assert set(m["by_reason"]) == {"out_of_scope_topic"}
    assert m["wrong_reason_rate"] == 0.0
