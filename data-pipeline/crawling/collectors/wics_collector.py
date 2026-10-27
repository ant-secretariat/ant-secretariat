"""WICS 섹터 분류(대분류·중분류) 수집.

wiseindex.com의 robots.txt는 일반 크롤러를 허용하지 않으므로 팀 내부 테스트 범위에서만 쓴다.
분류는 자주 바뀌지 않아 주 1회 정도면 충분하고, 요청 사이에 간격을 둔다.
중분류 26개를 조회하면 대분류 합계(전 종목)와 같아지는 것을 2026-10-26 기준으로 확인했다.
"""

from __future__ import annotations

import logging
import time
from datetime import date

import httpx

from crawling.config.settings import SETTINGS, Settings
from crawling.crawler.http import create_ssl_context

logger = logging.getLogger(__name__)


WICS_URL = "https://www.wiseindex.com/Index/GetIndexComponets"
WICS_SECTORS = {
    "G10": "에너지",
    "G15": "소재",
    "G20": "산업재",
    "G25": "경기관련소비재",
    "G30": "필수소비재",
    "G35": "건강관리",
    "G40": "금융",
    "G45": "IT",
    "G50": "커뮤니케이션서비스",
    "G55": "유틸리티",
}
WICS_INDUSTRIES = {
    "G1010": "에너지",
    "G1510": "소재",
    "G2010": "자본재",
    "G2020": "상업서비스와공급품",
    "G2030": "운송",
    "G2510": "자동차와부품",
    "G2520": "내구소비재와의류",
    "G2530": "호텔,레스토랑,레저등",
    "G2550": "소매(유통)",
    "G2560": "교육서비스",
    "G3010": "식품과기본식료품소매",
    "G3020": "식품,음료,담배",
    "G3030": "가정용품과개인용품",
    "G3510": "건강관리장비와서비스",
    "G3520": "제약과생물공학",
    "G4010": "은행",
    "G4020": "증권",
    "G4030": "다각화된금융",
    "G4040": "보험",
    "G4050": "부동산",
    "G4510": "소프트웨어와서비스",
    "G4520": "기술하드웨어와장비",
    "G4530": "반도체와반도체장비",
    "G4535": "전자와 전기제품",
    "G4540": "디스플레이",
    "G5010": "전기통신서비스",
    "G5020": "미디어와엔터테인먼트",
    "G5510": "유틸리티",
}


def fetch_wics_classification(day: date, settings: Settings | None = None) -> dict[str, tuple[str, str]]:
    """종목코드 → (대분류명, 중분류명). 그날 자료가 없으면 빈 dict."""
    settings = settings or SETTINGS
    classification: dict[str, tuple[str, str]] = {}
    with httpx.Client(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.request_timeout_seconds,
        follow_redirects=True,
        verify=create_ssl_context(),
    ) as client:
        for code, industry in WICS_INDUSTRIES.items():
            response = client.get(
                WICS_URL,
                params={"ceil_yn": 0, "dt": day.strftime("%Y%m%d"), "sec_cd": code},
            )
            response.raise_for_status()
            rows = response.json().get("list") or []
            if not rows and not classification:
                # 첫 업종부터 비어 있으면 그날 자료가 아직 없는 것이다 (장중·휴장일)
                return {}
            if not rows:
                logger.warning("WICS %s(%s) 구성종목이 비어 있습니다", code, industry)
            sector = WICS_SECTORS[code[:3]]
            for row in rows:
                classification[row["CMP_CD"]] = (sector, industry)
            time.sleep(settings.request_delay_seconds)
    return classification
