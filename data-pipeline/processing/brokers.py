"""증권사 이름을 하나로 맞춘다 (broker_key).

KIS 목표주가(broker_opinions.broker)와 증권사 리포트(report_metadata.broker, document_chunks.broker)는 같은
증권사를 다르게 적는다. 예: KIS "키움"·"NH투자"·"IM증권", 리포트 "키움증권"·"iM증권"·"신한투자증권".
트렌드 리포트의 증권사 시각차 카드처럼 두 출처를 증권사로 이어야 할 때 이 키로 맞춘다(#69 리뷰).

규칙: 공백과 회사 형태 표기("(주)", "㈜", "주식회사")를 없애고 영문은 대문자로, 끝의 "투자증권"·"증권"·"투자"를 뗀 뒤
옛 이름은 지금 이름으로 바꾼다.

이름이 바뀐 증권사는 바뀐 시점과 상관없이 늘 지금 이름의 키로 맞춘다. 같은 회사의 의견·리포트를 사명 변경 전후로
나눠 세면 컨센서스·개정 수에서 한 증권사가 둘로 잡히기 때문이다(#50). 바뀐 시점(RENAMED_SINCE)은 "당시 이름"을
보여 주거나 검토할 때 쓰는 기록이다.
"""

from __future__ import annotations

import re

# 끝에서 떼는 말. 긴 것부터 본다("투자증권"을 "증권"보다 먼저)
_SUFFIXES = ("금융투자", "투자증권", "증권", "투자")
# 이름이 바뀐 증권사: 옛 이름(접미어 뗀 뒤) → (지금 이름, 바뀐 해)
RENAMED_SINCE = {
    "하나금융": ("하나", "2022"),     # 하나금융투자 → 하나증권
    "KTB": ("다올", "2022"),          # KTB투자증권 → 다올투자증권
    "이베스트": ("LS", "2024"),       # 이베스트투자증권 → LS증권
    "하이": ("IM", "2024"),           # 하이투자증권 → iM증권
    "DGB": ("IM", "2024"),
}
_RENAMED = {old: new for old, (new, _since) in RENAMED_SINCE.items()}
# 회사 형태 표기. 앞이나 뒤에 붙는다("(주)키움증권", "키움증권(주)")
_COMPANY_FORMS = ("(주)", "㈜", "주식회사")
# 증권사가 아닌 발행 기관은 그대로 둔다(접미어를 떼지 않음)
_KEEP_AS_IS = {"한국IR협의회"}


def broker_key(name: str | None) -> str | None:
    """증권사 이름 → 비교용 키. 비어 있으면 None."""
    if not name:
        return None
    text = re.sub(r"\s+", "", str(name))
    for form in _COMPANY_FORMS:
        text = text.replace(form, "")
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
