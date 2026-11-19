"""기준 날짜는 한국 시간(KST)으로 구한다 (docs/CODE_CONVENTIONS.md 날짜와 시각).

date.today()는 실행하는 컴퓨터의 시간대를 따라, UTC 러너에서 한국 시간 오전 9시 전에 돌면 하루 전이 된다.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def today_kst() -> date:
    return datetime.now(KST).date()
