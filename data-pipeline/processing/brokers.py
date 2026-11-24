"""증권사 이름을 하나로 맞춘다 (broker_key).

KIS 목표주가(broker_opinions.broker)와 증권사 리포트(report_metadata.broker, document_chunks.broker)는 같은
증권사를 다르게 적는다. 예: KIS "키움"·"NH투자"·"IM증권", 리포트 "키움증권"·"iM증권"·"신한투자증권".
트렌드 리포트의 증권사 시각차 카드처럼 두 출처를 증권사로 이어야 할 때 이 키로 맞춘다(#69 리뷰).

규칙: 공백을 없애고 영문은 대문자로, 끝의 "투자증권"·"증권"·"투자"를 뗀 뒤 옛 이름은 지금 이름으로 바꾼다.
"""

from __future__ import annotations

import re

# 끝에서 떼는 말. 긴 것부터 본다("투자증권"을 "증권"보다 먼저)
_SUFFIXES = ("금융투자", "투자증권", "증권", "투자")
# 이름이 바뀐 증권사: 옛 이름(접미어 뗀 뒤) → 지금 이름
_RENAMED = {
    "하나금융": "하나",      # 하나금융투자 → 하나증권 (2022)
    "KTB": "다올",           # KTB투자증권 → 다올투자증권 (2022)
    "이베스트": "LS",        # 이베스트투자증권 → LS증권 (2024)
    "하이": "IM",            # 하이투자증권 → iM증권 (2024)
    "DGB": "IM",
}
# 증권사가 아닌 발행 기관은 그대로 둔다(접미어를 떼지 않음)
_KEEP_AS_IS = {"한국IR협의회"}


def broker_key(name: str | None) -> str | None:
    """증권사 이름 → 비교용 키. 비어 있으면 None."""
    if not name:
        return None
    text = re.sub(r"\s+", "", str(name))
    if not text:
        return None
    if text in _KEEP_AS_IS:
        return text
    text = re.sub(r"[a-z]+", lambda m: m.group(0).upper(), text)
    for suffix in _SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
            break
    return _RENAMED.get(text, text)
