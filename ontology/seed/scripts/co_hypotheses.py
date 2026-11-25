"""종목 → 매크로 SENSITIVE_TO 가설 목록 (ADR 0011 3번: 가설은 값을 보기 전에 적는다).

build_seed.py(판정)와 export_sensitivity_inputs.py(입력값 내보내기)가 같이 쓴다.
처음 10개는 값을 본 뒤 붙였다(hypothesis_preregistered False, 2026-11-23 고정). 새 가설은 preregistered True로 먼저 적는다.
"""
# (ticker, macro, 가설 부호, 가설, preregistered, fixed_on)
CO_HYPOTHESES = [
    ("003490", "KTB_3Y_KR", "-", "부채·항공기 리스 부담이 커서 금리가 오르면 이자 비용이 늘 수 있음", False, "2026-11-23"),
    ("003490", "KTB_10Y_KR", "-", "부채·항공기 리스 부담이 커서 금리가 오르면 이자 비용이 늘 수 있음", False, "2026-11-23"),
    ("015760", "KTB_3Y_KR", "-", "부채가 큰 규제 유틸리티라 금리가 오르면 이자 비용이 늘 수 있음", False, "2026-11-23"),
    ("015760", "KTB_10Y_KR", "-", "부채가 큰 규제 유틸리티라 금리가 오르면 이자 비용이 늘 수 있음", False, "2026-11-23"),
    ("180640", "KTB_3Y_KR", "-", "대한항공 지주라 대한항공의 금리 부담을 따라갈 수 있음", False, "2026-11-23"),
    ("035720", "KTB_10Y_KR", "-", "먼 미래 이익 비중이 큰 성장주라 장기 할인율에 민감할 수 있음", False, "2026-11-23"),
    ("010950", "BRENT", "+", "유가가 오르면 정유 재고 평가이익·마진이 좋아질 수 있음", False, "2026-11-23"),
    ("096770", "BRENT", "+", "유가가 오르면 정유 재고 평가이익·마진이 좋아질 수 있음", False, "2026-11-23"),
    ("005930", "DRAM_EXPORT_PRICE", "+", "메모리 매출 비중이 커서 D램 가격이 이익에 크게 영향을 줄 수 있음", False, "2026-11-23"),
    ("000660", "DRAM_EXPORT_PRICE", "+", "메모리 매출 비중이 커서 D램 가격이 이익에 크게 영향을 줄 수 있음", False, "2026-11-23"),
]


def co_failed_criteria(row, sign, q_hyp, min_size=0.10, q_max=0.05):
    """ADR 0011 노출 기준 4개 중 못 넘은 것(빈 목록이면 노출). row는 sensitivity_inputs CSV 한 줄."""
    adj, lo, hi = float(row["adjusted"]), float(row["ci_low"]), float(row["ci_high"])
    failed = []
    if not (lo > 0 or hi < 0):
        failed.append("ci_includes_zero")
    if abs(adj) < min_size:
        failed.append("below_min_size")
    if not ((sign == "+" and adj > 0) or (sign == "-" and adj < 0)):
        failed.append("sign_mismatch")
    if q_hyp is None or q_hyp >= q_max:
        failed.append("q_not_significant")
    return failed


def co_status(failed, prev_failed):
    """ADR 0011 4번: 통과 → active, 이번에만 탈락 → needs_review, 직전 기준일에도 탈락 → rejected."""
    if not failed:
        return "active"
    return "rejected" if prev_failed else "needs_review"
