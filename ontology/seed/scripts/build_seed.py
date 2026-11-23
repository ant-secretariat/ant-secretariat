"""온톨로지 관계사전 시드 v0.9 생성 — 기획서 v1.2 엣지 7종 정의 기준

사용법: python build_seed.py <core_companies.csv> <출력 폴더>
  - core_companies.csv 는 수경 파이프라인 companies.is_core 내보내기 (extract_t1.py 로 형식 검증)
  - 출력 폴더의 ontology_seed.json 하나만 덮어쓴다 (원본은 이 파일 하나. 읽기는 ontology_seed.py 로더)

v0.9 변경 (#56 종목 단위 값, 유민 제안 기준 — 이 PR 리뷰가 팀 합의)
  - 종목 → 매크로 SENSITIVE_TO 10개 추가(src_type COMPANY). 기준: 시장 효과 뺀 값의 95% 구간이 0 미포함,
    |값| ≥ 0.10, 경제적 가설이 있고 부호가 같음, 가설 엣지끼리 BH 보정 q < 0.05(수경 제안). weight 는 시장 효과를 뺀 값(market_adjusted True)
  - 로더 company_context 에 company_sensitivities 추가

v0.8 변경 (수경 #61 온톨로지 입력값 2026-11-23, 유민 결정 #61 코멘트)
  - MACRO direction: 데이터(시장과 지표 변화 상관, Fisher 95%)와 초안이 같은 4개(KTB_3Y_KR·KTB_10Y_KR up_negative,
    USD_KRW·BRENT mixed)만 direction_evidence 를 붙이고 draft_fields 에서 뺀다. 나머지는 초안 유지
  - IMPACTS: CPI_KR → BASE_RATE_KR(same) 하나만 데이터로 확인돼 active. 나머지는 unclear 라 draft 유지
  - COMPANY: is_holding 을 KRX KIND(법적 지주) + 사업형 지주로 확정(holding_type), sub_industry 는 KIND 후보를
    고쳐 확정한 34개만 노출. 섹터 rate·fx 등급은 계속 초안(시장 효과를 빼면 섹터 단위 신호가 없음)

v0.7 변경 (수경 PR #29 검증 코멘트 2026-11-23, 유민 결정)
  - needs_review 였던 SENSITIVE_TO 9개 → status "rejected" (시장 효과를 빼면 관계가 남지 않음, REJECTED 표에 근거)
  - 시장 효과를 빼지 않은 상관은 노출하지 않는다: KOSPI(시장 자체)가 아닌 엣지는 market_adjusted 값이 올 때까지
    status "needs_review", review_reason "market_unadjusted"
  - 섹터 → KOSPI(시장 동조) 엣지를 모든 섹터에 추가(수경 corr_daily 중앙값). 종목 3개 미만 섹터는 needs_review(low_n).
    노출되는 SENSITIVE_TO 는 KOSPI 엣지 8개
  - (#56 반영) market_unadjusted 보류 10개도 시장 효과를 뺀 값이 기준 미달 → rejected (REJECTED_56). 기각 19개
  - 엣지에 market_adjusted 필드 (지금은 모두 False — 수경 값은 시장 효과를 빼지 않은 상관)

v0.6 변경 (태은 PR #29 리뷰, ADR 0008 · 헌법 원칙 III·IV)
  - 모든 노드·엣지에 status·reviewed. 노출 = status "active" 이고 reviewed True 인 것만 (로더 is_exposed)
  - 엣지 공통 필드: relation·src·src_type·dst·dst_type·source·method·as_of·valid_from·valid_to·evidence_ids
    (계약 draft.5 Relation 이름. IMPACTS 의 방향 값은 relation → direction 으로 옮김)
  - Claude 초안(ISSUE·BENEFITS/HURTS·EXPOSED_TO·IMPACTS)은 status "draft", reviewed False → 노출 안 됨
  - SENSITIVE_TO 중 가설과 부호가 반대(mismatch)이거나 0 근처(near_zero)인 엣지 → status "needs_review"
  - 노드의 Claude 초안 속성은 draft_fields 에 이름을 적고, 로더가 기본값에서 뺀다
  - 섹터 name = WICS 대분류 명칭. ISSUE valid_until → valid_to. weight_low_n 은 True/False (weight 없으면 null)
  - W_N(섹터 종목 수)을 core 소속 종목 수(상장 이력이 짧은 0126Z0 제외)와 대조

v0.3 변경 (수경 파이프라인 실제 코드·답변 2026-11-10 대조, 근거는 SOURCES.md)
  - T1 = 파이프라인 core 100 (KOSPI 90 + KOSDAQ 10), 섹터 = companies.sector_l1(WICS)
  - 매크로 ID = 파이프라인 이름 (OIL_BRENT→BRENT, KOSPI_INDEX→KOSPI), 수집 상태 필드 추가
  - SEC_REAL_ESTATE 삭제 (WICS 대분류에 없음, 소속 종목 0개)

v0.4 변경 (유민 결정: 수집 계획 없는 매크로는 삭제하지 않고 비활성 보관)
  - 수집 계획 없는 매크로 7개와 거기 걸린 SENSITIVE_TO·IMPACTS 엣지 → status "inactive", inactive_reason "no_data_source"
  - BASE_RATE_KR 대상 SENSITIVE_TO 3개 → KTB_3Y_KR로 합침 (계단식이라 일별 상관 무의미)
  - 수집 중이나 회귀 요인이 아닌 KTB_10Y_KR·CPI_KR·BRENT 엣지 → weight_status "factor_requested"
  - SENSITIVE_TO의 weight_coverage 필드를 weight_status·weight_frequency로 대체

v0.5 변경 (수경 PR #29 코멘트 2026-11-10, 값은 PR #34 기준)
  - SENSITIVE_TO weight 채움: 활성 엣지 전부 수경 섹터 중앙값(일별 corr_daily / 월별 corr_monthly) + 출처·기간·as_of·종목 수
  - DRAM_PRICE(비활성) → DRAM_EXPORT_PRICE(ECOS 402Y016 수출물가지수 D램 달러기준, 월별)로 교체·활성화
  - 금리 엣지는 섹터당 하나만 둔다 (KTB_3Y_KR / KTB_10Y_KR 동시 금지 — 상관 0.9라 같은 효과가 두 번 들어감)
  - expected_sign 부호 검증 결과를 sign_check(match / mismatch / near_zero)로 기록. 가설을 회귀 값으로 덮어쓰지 않는다
  - 종목 수 3개 미만 섹터는 weight_low_n
"""
import csv, json, os, sys

RAW, OUT = sys.argv[1], sys.argv[2]
CORE_EXPORT = "2026-11-09"      # core_companies.csv 내보낸 날 (수경)
TIER_ASSIGNED = "2026-10-22"    # 파이프라인이 시총 순위로 T1을 지정한 날. 이후 고정
SENS_AS_OF = "2026-11-06"       # sensitivities 최신 as_of (수경)
GENERATED = "2026-11-23"        # 이 시드를 만든 날 (Claude 초안 엣지의 as_of)
os.makedirs(OUT, exist_ok=True)


def edge(relation, src, src_type, dst, dst_type, *, status, reviewed, source, method, as_of,
         valid_from=None, valid_to=None, evidence_ids=None, **extra):
    """엣지 공통 필드 (Design Doc 4.8 · 계약 draft.5 Relation). 노출 = status "active" and reviewed."""
    return dict(relation=relation, src=src, src_type=src_type, dst=dst, dst_type=dst_type,
                status=status, reviewed=reviewed, source=source, method=method, as_of=as_of,
                valid_from=valid_from, valid_to=valid_to, evidence_ids=evidence_ids or [], **extra)


# ───────────────────────── 1. SECTOR ─────────────────────────
# 섹터 식별(id·WICS 명칭·코드)은 파이프라인 값이라 검수된 것으로 본다. 경기·금리·환율 성격은 Claude 초안.
S = lambda i, n, en, g, cyc, rate, fx, note: dict(
    sector_id=i, name=n, name_en=en, gics_code=g, cycle_type=cyc,
    rate_sensitivity=rate, fx_sensitivity=fx, notes=note, source="pipeline:companies.sector_l1(WICS)",
    status="active", reviewed=True, draft_fields=["cycle_type", "rate_sensitivity", "fx_sensitivity", "notes"])
SECTORS = [
    S("SEC_IT", "정보기술", "Information Technology", "45", "growth", "high", "positive", "반도체·전자부품·IT서비스. 수출 비중 최대."),
    S("SEC_COMM", "커뮤니케이션서비스", "Communication Services", "50", "growth", "medium", "neutral", "통신·인터넷 플랫폼·게임·엔터."),
    S("SEC_CONS_DISC", "경기소비재", "Consumer Discretionary", "25", "cyclical", "high", "positive", "자동차·부품·가전·타이어. 완성차 수출 비중 큼."),
    S("SEC_CONS_STAP", "필수소비재", "Consumer Staples", "30", "defensive", "low", "negative", "식품·담배·화장품. 원재료 수입 비중 높음(화장품 수출주는 예외적으로 환율 수혜)."),
    S("SEC_HEALTH", "헬스케어", "Health Care", "35", "defensive", "medium", "positive", "제약·바이오·CDMO. 대형 바이오는 성장주 성격."),
    S("SEC_FIN", "금융", "Financials", "40", "cyclical", "medium", "neutral", "은행·보험·증권·카드. 금리↑ NIM 개선 vs 건전성 악화."),
    S("SEC_INDUS", "산업재", "Industrials", "20", "cyclical", "medium", "positive", "조선·방산·전력기기·기계·건설·운송·지주사."),
    S("SEC_MATERIAL", "소재", "Materials", "15", "cyclical", "medium", "neutral", "철강·비철·화학·양극재. 중국 경기 연동."),
    S("SEC_ENERGY", "에너지", "Energy", "10", "cyclical", "low", "negative", "정유. 원유 순수입 구조."),
    S("SEC_UTIL", "유틸리티", "Utilities", "55", "defensive", "high", "negative", "전력·가스. 규제 요금 + 연료 수입."),
]
# WICS 대분류(companies.sector_l1) → sector_id. 번호 체계가 GICS 코드와 같아 wics_code = "G" + gics_code
WICS_L1 = {"에너지": "SEC_ENERGY", "소재": "SEC_MATERIAL", "산업재": "SEC_INDUS", "경기관련소비재": "SEC_CONS_DISC",
           "필수소비재": "SEC_CONS_STAP", "건강관리": "SEC_HEALTH", "금융": "SEC_FIN", "IT": "SEC_IT",
           "커뮤니케이션서비스": "SEC_COMM", "유틸리티": "SEC_UTIL"}
_NAME_OF = {v: k for k, v in WICS_L1.items()}
for _s in SECTORS:
    _s["wics_code"] = "G" + _s["gics_code"]
    _s["wics_name"] = _NAME_OF[_s["sector_id"]]
    _s["name"] = _s["wics_name"]  # 파이프라인과 같은 이름을 쓴다 (헬스케어 → 건강관리 등)

# ───────────────────────── 2. MACRO ─────────────────────────
# in_pipeline: 수경 DB(1차 기준)에 이미 수집 중인 지표인지
M = lambda i, n, cat, dirn, unit, src, code, freq, inp, note: dict(
    indicator_id=i, name=n, category=cat, direction=dirn, unit=unit, source=src,
    source_code=code, update_freq=freq, in_pipeline=inp, notes=note)
MACROS = [
    M("BASE_RATE_KR", "한국 기준금리", "rate", "up_negative", "%", "ECOS", "722Y001", "daily", True, "통화정책 결정 시 변경. 파이프라인은 일별로 저장."),
    M("KTB_3Y_KR", "국고채 3년", "rate", "up_negative", "%", "ECOS", "817Y002", "daily", True, "단기 금리 기대 반영."),
    M("KTB_10Y_KR", "국고채 10년", "rate", "up_negative", "%", "ECOS", "817Y002", "daily", True, "장기 할인율."),
    M("US_FFR", "미국 연방기금금리", "rate", "up_negative", "%", "FRED", "FEDFUNDS", "monthly", False, "글로벌 유동성."),
    M("US_10Y_YIELD", "미국채 10년", "rate", "up_negative", "%", "FRED", "DGS10", "daily", False, "글로벌 성장주 할인율."),
    M("USD_KRW", "원/달러 환율", "fx", "mixed", "KRW", "ECOS", "731Y001", "daily", True, "상승=원화약세. 수출주↑ 수입원가↑ 외국인 수급↓."),
    M("USD_CNY", "달러/위안 환율", "fx", "mixed", "CNY", "FRED", "DEXCHUS", "daily", False, "위안 약세 시 중국산 가격경쟁력↑."),
    M("CPI_KR", "한국 CPI", "inflation", "up_negative", "YoY%", "ECOS", "901Y009", "monthly", True, "금리 경로 기대에 영향."),
    M("PPI_KR", "한국 PPI", "inflation", "up_negative", "YoY%", "ECOS", None, "monthly", False, "source_code 확인 필요."),
    M("BRENT", "브렌트유", "commodity", "mixed", "USD/bbl", "ECOS", "902Y003", "monthly", True, "ECOS 월평균(일별 아님). 정유 마진·운송 원가."),
    M("DRAM_EXPORT_PRICE", "D램 수출물가지수(달러기준)", "commodity", "up_positive", "2020=100", "ECOS", "402Y016", "monthly", True, "v0.4의 DRAM_PRICE(TrendForce, 유료)를 대체. 한국은행 수출물가지수 품목별 D램, 달러기준(원화기준은 환율이 섞여 제외). 월별."),
    M("CHINA_PMI_MFG", "중국 제조업 PMI", "sentiment", "up_positive", "index", "NBS", None, "monthly", False, "50 기준. 소재·산업재 수요."),
    M("VIX", "VIX", "sentiment", "up_negative", "index", "FRED", "VIXCLS", "daily", False, "위험회피 심리."),
    M("KOSPI", "KOSPI", "market", "up_positive", "pt", "KRX(pykrx)", "1001", "daily", True, "시장 베타 기준. macro_data가 아니라 index_daily(index_code 1001). 민감도 요인명도 KOSPI."),
]
# 수경 파이프라인 수집 현황 (macro_data_collector.DEFAULT_ECOS_INDICATORS + 수경 답변 2026-11-10)
# 값: (테이블, 키, ECOS 항목코드). 여기 없는 지표는 FRED·NBS·유료 소스로 수집 계획이 없다.
PIPE = {
    "BASE_RATE_KR": ("macro_data", "BASE_RATE_KR", "0101000"),
    "KTB_3Y_KR": ("macro_data", "KTB_3Y_KR", "010200000"),
    "KTB_10Y_KR": ("macro_data", "KTB_10Y_KR", "010210000"),
    "USD_KRW": ("macro_data", "USD_KRW", "0000001"),
    "CPI_KR": ("macro_data", "CPI_KR", "0"),
    "BRENT": ("macro_data", "BRENT", "010103"),
    "DRAM_EXPORT_PRICE": ("macro_data", "DRAM_EXPORT_PRICE", "30911201AA/D"),
    "KOSPI": ("index_daily", "1001", None),
}
for _m in MACROS:
    _p = PIPE.get(_m["indicator_id"])
    _m["in_pipeline"] = bool(_p)
    _m["pipeline_status"] = "collecting" if _p else "not_planned"
    _m["pipeline_table"], _m["pipeline_key"], _m["pipeline_item_code"] = _p or (None, None, None)
    # v0.4: 수집 계획 없는 지표는 삭제하지 않고 비활성으로 보관 (데이터가 생기면 status만 active로 바꾼다)
    _m["status"] = "active" if _p else "inactive"
    _m["reviewed"] = bool(_p)  # 수집 중인 지표는 수경이 ID·출처를 확인했다
    _m["draft_fields"] = ["direction", "notes"]  # 방향 가설·메모는 Claude 초안
    _m["inactive_reason"] = None if _p else "no_data_source"
    if not _p:
        _m["notes"] += " 수집 계획 없음(수경 2026-11-10) — 필요하면 추가 요청."
# v0.8: 방향 근거 (수경 #61, crawling.ontology_inputs #62, as_of 2026-11-23). 시장(일별 코스피 수익률, 월별 핵심 종목
# 동일가중 평균)과 지표 변화의 상관. 신뢰구간이 0을 포함하지 않으면 up_positive/up_negative, 아니면 mixed.
# 데이터 판정이 초안과 같은 것만 확정한다. BASE_RATE_KR·CPI_KR(초안 up_negative)·DRAM_EXPORT_PRICE(초안 up_positive)는
# 데이터가 mixed 라 초안 유지. KOSPI 는 시장 자체라 계산 대상이 아니다.
_DIR_SRC = "수경 #61 2026-11-23 (crawling.ontology_inputs, PR #62)"
DIRECTION_EVIDENCE = {  # indicator_id: (method, corr, ci_low, ci_high, n)
    "KTB_3Y_KR": ("corr_daily_with_kospi", -0.164, -0.23, -0.09, 727),
    "KTB_10Y_KR": ("corr_daily_with_kospi", -0.132, -0.20, -0.06, 727),
    "USD_KRW": ("corr_daily_with_kospi", -0.005, -0.08, 0.07, 727),
    "BRENT": ("corr_monthly_with_core_market", 0.131, -0.05, 0.30, 120),
}


def _dir_from_ci(lo, hi):
    return "up_positive" if lo > 0 else "up_negative" if hi < 0 else "mixed"


for _m in MACROS:
    _ev = DIRECTION_EVIDENCE.get(_m["indicator_id"])
    _m["direction_evidence"] = None
    if _ev:
        method, corr, lo, hi, n = _ev
        assert _dir_from_ci(lo, hi) == _m["direction"], ("데이터 판정과 초안이 다르면 확정하지 않는다", _m["indicator_id"])
        _m["direction_evidence"] = dict(source=_DIR_SRC, method=method, as_of="2026-11-23", corr=corr,
                                        ci95=[lo, hi], n=n, decided_by="유민", decided_on="2026-11-23")
        _m["draft_fields"] = ["notes"]
INACTIVE_MACROS = {m["indicator_id"] for m in MACROS if m["status"] == "inactive"}

# ───────────────────────── 5. COMPANY (T1 = 수경 파이프라인 core 100) ─────────────────────────
# 종목·시장·섹터는 파이프라인 값 그대로. 지주사 여부·세부 산업은 Claude 초안(섹터 상속 보정용).
# v0.8: 지주사 확정 (유민 2026-11-23, #61). KRX KIND 상장법인목록은 100종목 모두 있어 is_holding 은 전부 검토 끝(노출).
#   legal     = KIND 업종·주요제품·이름으로 확인한 지주회사
#   financial = 금융지주 (KB금융은 이름 규칙에 안 걸렸지만 금융지주회사라 넣음)
#   business  = 법적 지주는 아니지만 자회사 지분 가치가 큰 사업형·중간 지주 (v0.7 이전 시드 목록)
HOLDING_TYPE = {
    "003550": "legal", "005490": "legal", "0126Z0": "legal", "034730": "legal", "078930": "legal",
    "180640": "legal", "267250": "legal", "402340": "legal",
    "105560": "financial", "055550": "financial", "071050": "financial", "086790": "financial",
    "138040": "financial", "316140": "financial",
    "028260": "business", "009540": "business", "000150": "business", "006260": "business", "000880": "business",
}
HOLDINGS = set(HOLDING_TYPE)
# v0.8: 세부 산업 확정. KIND 후보(#61 SUB_INDUSTRY_RULES)를 유민이 검토해 고친 값만 노출한다.
#   고친 것: 한화솔루션 방산→화학·태양광, 한화시스템 전자부품·PCB→방산·ICT, 레인보우로보틱스 반도체 장비→로봇,
#   리노공업 전자부품·PCB→반도체 테스트 소켓, LG이노텍→카메라모듈·기판, 삼성전기→MLCC·패키지기판, 두산→전자소재(CCL),
#   포스코퓨처엠·에코프로비엠 2차전지→2차전지 소재(양극재), SK이노베이션 정유→정유·배터리
SUB_REVIEWED = {
    "000150": "전자소재(CCL)", "000500": "전선", "003490": "항공운송", "003670": "2차전지 소재(양극재·음극재)",
    "006400": "2차전지", "007660": "PCB", "009150": "MLCC·패키지기판", "009830": "화학·태양광",
    "010120": "전력기기", "010140": "조선", "010950": "정유", "011070": "카메라모듈·기판",
    "011200": "컨테이너 해운", "012450": "방산·항공엔진", "034020": "원전·발전설비", "036930": "반도체 장비",
    "039030": "반도체 장비(레이저)", "042660": "조선", "042700": "반도체 장비", "047810": "방산·항공",
    "058470": "반도체 테스트 소켓", "062040": "전력기기(변압기)", "079550": "방산", "086280": "자동차 물류",
    "096770": "정유·배터리", "240810": "반도체 장비", "247540": "2차전지 소재(양극재)", "267260": "전력기기",
    "272210": "방산·ICT", "277810": "로봇", "298040": "전력기기", "329180": "조선", "353200": "PCB",
    "373220": "2차전지",
}
SUB = {  # 세부 산업 메모 (탐색 시 섹터 상속 보정용)
 "373220":"2차전지","006400":"2차전지","003670":"양극재","402340":"SK하이닉스 지분 투자회사",
 "009540":"조선 중간지주","0126Z0":"삼성바이오에피스 지주","078930":"정유 중심 지주",
 "278470":"뷰티 디바이스·화장품","011200":"컨테이너 해운","086280":"자동차 물류","012450":"방산·항공엔진",
 "034020":"원전·발전설비","267260":"전력기기","298040":"전력기기","010120":"전력기기","000500":"전선",
 "062040":"전력기기(변압기)","007660":"PCB","353200":"PCB","042700":"반도체 장비",
}
SUB = {**SUB, **SUB_REVIEWED}
COMPANIES = []
with open(RAW, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        code = row["ticker"]
        COMPANIES.append(dict(
            ticker=code, name=row["name"], market=row["market"], sector_id=WICS_L1[row["sector_l1"]],
            sector_l1=row["sector_l1"], sector_l2=row["sector_l2"], sub_industry=SUB.get(code),
            is_holding=code in HOLDINGS, holding_type=HOLDING_TYPE.get(code), tier="T1", is_core=True,
            tier_assigned_on=TIER_ASSIGNED, sector_source="pipeline:companies.sector_l1(WICS)",
            sub_industry_source=("krx_kind+review(#61)" if code in SUB_REVIEWED else "claude_draft" if code in SUB else None),
            holding_source="krx_kind+review(#61)",
            status="active", reviewed=True, draft_fields=[] if code in SUB_REVIEWED else ["sub_industry"]))
TICKERS = {c["ticker"]: c["name"] for c in COMPANIES}
assert len(COMPANIES) == 100 and len(TICKERS) == 100, "core는 100종목·중복 없음이어야 한다"
assert HOLDINGS <= set(TICKERS) and set(SUB) <= set(TICKERS) and len(SUB_REVIEWED) == 34, "HOLDINGS/SUB에 core에 없는 종목이 있다"

# ───────────────────────── 3. ISSUE + BENEFITS/HURTS ─────────────────────────
# 필수 속성(v1.2): evidence_chunk_ids(근거 청크), valid_from/valid_to(유효기간). 채워지고 검수되기 전에는 노출 안 됨
REVIEW = {"persistent": 180, "cyclical": 90, "event_driven": 30}
ISSUES, IMPACT_EDGES, DROPPED = [], [], []  # DROPPED: core에 없어 버린 (이슈, 종목) 엣지
DRAFT = dict(status="draft", reviewed=False, source="claude_draft", method="claude_draft", as_of=GENERATED)
def I(iid, name, typ, pol, dur, agendas, note, targets):
    ISSUES.append(dict(
        issue_id=iid, name=name, type=typ, polarity=pol, duration=dur, agenda_ids=agendas,
        notes=note, evidence_chunk_ids=[], valid_from=None, valid_to=None,
        review_cycle_days=REVIEW[dur], status="draft", reviewed=False, labeled_by="claude_draft"))
    rel = "BENEFITS" if pol == "positive" else "HURTS"
    for tgt, strength in targets:
        ttype = "SECTOR" if tgt.startswith("SEC_") else "COMPANY"
        if ttype == "COMPANY" and tgt not in TICKERS:
            DROPPED.append([iid, tgt]); continue
        IMPACT_EDGES.append(edge(rel, iid, "ISSUE", tgt, ttype, **DRAFT, strength=strength))

I("ISS_AI_MEMORY_DEMAND","AI 서버용 HBM·고용량 메모리 수요 확대","industry","positive","persistent",["growth","valuation"],
  "AI 가속기 탑재 HBM 수요. 공급사 점유율 경쟁이 핵심 변수.",
  [("000660","high"),("005930","high"),("042700","mid"),("402340","mid"),("SEC_IT","mid")])
I("ISS_MEMORY_PRICE_CYCLE","메모리 가격 상승 사이클","industry","positive","cyclical",["valuation","growth"],
  "DRAM·NAND 가격 반등 국면. 사이클 피크 논쟁이 Bear 논거.",
  [("005930","high"),("000660","high"),("402340","mid")])
I("ISS_SEMI_EXPORT_CONTROL","미국 대중 반도체 수출 통제","policy","negative","persistent",["risk","macro"],
  "중국 공장 장비 반입·고성능 칩 판매 제한.",
  [("005930","mid"),("000660","mid")])
I("ISS_FOUNDRY_COMPETITION","파운드리 선단공정 경쟁 열위","company","negative","persistent",["risk","growth"],
  "선단공정 수율·고객 확보에서 경쟁사 대비 열위.",
  [("005930","mid")])
I("ISS_AI_POWER_INFRA","AI 데이터센터·전력망 투자 확대","industry","positive","persistent",["growth","valuation"],
  "변압기·전선·발전설비 수요. 수주잔고가 실적 가시성 근거.",
  [("267260","high"),("298040","high"),("010120","high"),("062040","high"),("000500","mid"),("034020","mid"),("006260","mid")])
I("ISS_AI_PCB_DEMAND","AI 서버용 고다층 기판·부품 수요","industry","positive","persistent",["growth"],
  "AI 가속기·네트워크 장비용 MLB·기판.",
  [("007660","high"),("353200","mid"),("009150","mid"),("011070","low")])
I("ISS_AUTO_US_TARIFF","미국 수입차 관세","policy","negative","persistent",["risk","macro"],
  "대미 수출 완성차·부품 마진 압박. 현지 생산 확대로 대응.",
  [("005380","high"),("000270","high"),("012330","mid"),("161390","low"),("086280","low")])
I("ISS_EV_DEMAND_SLOWDOWN","전기차 수요 둔화(캐즘)","industry","negative","cyclical",["risk","growth"],
  "보조금 축소·가격 부담으로 EV 판매 성장 둔화.",
  [("373220","high"),("006400","high"),("003670","high"),("005380","low")])
I("ISS_BATTERY_CHINA_COMPETITION","중국 배터리 저가 경쟁","industry","negative","persistent",["risk","valuation"],
  "LFP 중심 중국 업체의 가격 경쟁.",
  [("373220","mid"),("006400","mid"),("003670","mid")])
I("ISS_ESS_DEMAND","ESS(에너지저장장치) 수요 확대","industry","positive","persistent",["growth"],
  "데이터센터·재생에너지 연계 ESS. EV 둔화 상쇄 논거.",
  [("373220","mid"),("006400","mid")])
I("ISS_SHIPBUILDING_UPCYCLE","조선 수주 업사이클","industry","positive","cyclical",["growth","valuation"],
  "선가 상승·수주잔고 확대. 인도 시점부터 이익 반영.",
  [("329180","high"),("009540","high"),("042660","high"),("010140","high"),("443060","mid")])
I("ISS_US_SHIPBUILDING_COOP","한미 조선 협력(MRO·현지 투자)","policy","positive","persistent",["growth","macro"],
  "미 해군 MRO·현지 조선소 투자 협력.",
  [("042660","high"),("329180","mid"),("009540","mid")])
I("ISS_DEFENSE_EXPORT","K-방산 수출 확대","industry","positive","persistent",["growth","valuation"],
  "지상무기·항공·유도무기 수출 계약.",
  [("012450","high"),("064350","high"),("079550","high"),("047810","mid"),("272210","mid")])
I("ISS_NUCLEAR_EXPORT","원전 수주·수출","industry","positive","persistent",["growth"],
  "해외 원전·SMR 프로젝트.",
  [("034020","high"),("000720","mid"),("015760","mid")])
I("ISS_RATE_CUT_NIM","금리 인하에 따른 은행 NIM 축소","macro","negative","cyclical",["valuation","macro"],
  "예대마진 축소. 비이자이익·주주환원이 방어 논거.",
  [("SEC_FIN","mid"),("105560","mid"),("055550","mid"),("086790","mid"),("316140","mid"),("024110","mid")])
I("ISS_PF_CREDIT_RISK","부동산 PF 부실·건전성 리스크","macro","negative","cyclical",["risk"],
  "PF 연체·충당금 부담.",
  [("000720","mid"),("047040","mid"),("028050","low"),("SEC_FIN","low")])
I("ISS_TRADING_VOLUME_BOOM","증시 거래대금 증가","market","positive","cyclical",["growth","valuation"],
  "브로커리지 수수료·IB 실적 개선.",
  [("006800","high"),("039490","high"),("005940","mid"),("016360","mid"),("071050","mid")])
I("ISS_VALUEUP_POLICY","밸류업·주주환원 정책","policy","positive","persistent",["shareholder_return","valuation"],
  "자사주 소각·배당 확대 압력. 저PBR 업종 재평가.",
  [("SEC_FIN","high"),("105560","high"),("055550","high"),("086790","high"),("138040","mid"),("033780","mid"),("000810","mid")])
I("ISS_GOVERNANCE_REFORM","상법 개정·지배구조 개선","policy","positive","persistent",["shareholder_return","valuation"],
  "이사 충실의무 확대 등. 지주사 할인 축소 논거.",
  [("034730","mid"),("003550","mid"),("000880","mid"),("402340","mid"),("028260","mid"),("267250","mid")])
I("ISS_CHINA_CHEM_OVERCAPACITY","중국 석유화학 공급 과잉","industry","negative","persistent",["risk","valuation"],
  "범용 석화 스프레드 약세. 구조조정 여부가 변수.",
  [("051910","high"),("009830","mid"),("096770","mid"),("SEC_MATERIAL","mid")])
I("ISS_PLATFORM_REGULATION","플랫폼 규제","policy","negative","persistent",["risk"],
  "수수료·광고·결제 규제.",
  [("035420","mid"),("035720","mid"),("323410","low"),("377300","low")])
I("ISS_KBEAUTY_EXPORT","K-뷰티 수출 확대","industry","positive","persistent",["growth"],
  "미국·일본 등 채널 다변화.",
  [("278470","high"),("090430","mid")])
I("ISS_KFOOD_EXPORT","K-푸드 수출 확대","industry","positive","persistent",["growth"],
  "라면·스낵 해외 매출 비중 확대.",
  [("003230","high"),("271560","mid")])
I("ISS_BIO_CDMO_DEMAND","바이오시밀러·CDMO 수요 확대","industry","positive","persistent",["growth","valuation"],
  "특허 만료 사이클·위탁생산 수요.",
  [("207940","high"),("068270","high"),("0126Z0","mid")])
I("ISS_PHARMA_US_TARIFF","미국 의약품 관세","policy","negative","event_driven",["risk","macro"],
  "현지 생산 여부가 노출도 결정.",
  [("068270","mid"),("207940","low"),("326030","low")])
I("ISS_FREIGHT_NORMALIZATION","컨테이너 운임 하락","industry","negative","cyclical",["risk","valuation"],
  "선복 공급 증가로 운임 정상화.",
  [("011200","high"),("086280","low")])

# EXPOSED_TO: COMPANY → ISSUE (exposure 0~1). strength 기반 초안값
EXP = {"high": 0.9, "mid": 0.6, "low": 0.3}
EXPOSED = [edge("EXPOSED_TO", e["dst"], "COMPANY", e["src"], "ISSUE", **DRAFT, exposure=EXP[e["strength"]],
                exposure_rule="strength 매핑: high .9 / mid .6 / low .3")
           for e in IMPACT_EDGES if e["dst_type"] == "COMPANY"]

# ───────────────────────── 4. SENSITIVE_TO / IMPACTS ─────────────────────────
# SENSITIVE_TO: SECTOR → MACRO. weight는 수경 회귀(상관 기반 민감도)로만 채움.
# expected_sign = 회귀 결과 부호 검증용 사전 가설 (weight 아님)
SENS = [
 ("SEC_IT","BASE_RATE_KR","-","성장주 할인율"),("SEC_IT","US_10Y_YIELD","-","글로벌 성장주 할인율"),
 ("SEC_IT","USD_KRW","+","수출 환산 이익"),("SEC_IT","DRAM_EXPORT_PRICE","+","메모리 실적 직결"),("SEC_IT","VIX","-","고베타"),
 ("SEC_COMM","KTB_10Y_KR","-","플랫폼 성장주 할인율"),
 ("SEC_CONS_DISC","USD_KRW","+","완성차 수출"),("SEC_CONS_DISC","BASE_RATE_KR","-","할부·소비심리"),
 ("SEC_CONS_DISC","CHINA_PMI_MFG","+","중국 수요"),("SEC_CONS_DISC","CPI_KR","-","소비 여력"),
 ("SEC_CONS_STAP","USD_KRW","-","원재료 수입"),("SEC_CONS_STAP","PPI_KR","-","원가 상승"),
 ("SEC_HEALTH","KTB_10Y_KR","-","바이오 할인율"),("SEC_HEALTH","USD_KRW","+","수출 환산"),
 ("SEC_FIN","KTB_3Y_KR","+","NIM"),("SEC_FIN","BASE_RATE_KR","+","NIM(건전성 악화로 상쇄 가능)"),
 ("SEC_FIN","KOSPI","+","증권 브로커리지"),("SEC_FIN","VIX","-","위험회피"),
 ("SEC_INDUS","USD_KRW","+","조선·방산 달러 수주"),("SEC_INDUS","CHINA_PMI_MFG","+","산업재 수요"),
 ("SEC_INDUS","BRENT","-","운송 원가(해운·항공)"),
 ("SEC_MATERIAL","CHINA_PMI_MFG","+","소재 수요"),("SEC_MATERIAL","USD_CNY","-","중국산 가격경쟁"),
 ("SEC_MATERIAL","BRENT","±","화학 원료·제품가 동반"),
 ("SEC_ENERGY","BRENT","±","재고평가이익 vs 원가"),("SEC_ENERGY","USD_KRW","-","원유 수입"),
 ("SEC_UTIL","BRENT","-","연료비"),("SEC_UTIL","USD_KRW","-","연료 수입"),("SEC_UTIL","KTB_10Y_KR","-","채권 대체재"),
]
# weight_coverage: 수경 sensitivities의 회귀 요인은 KOSPI·USD_KRW·KTB_3Y_KR 3개뿐이다.
#   planned      = 수경이 섹터별 corr_daily 중앙값 + 종목 수를 집계해 줄 예정 (최신 as_of 2026-11-06)
#   none_planned = 회귀 요인에 없어 weight를 채울 수단이 없다 (요인 추가 또는 엣지 정리 필요)
SENS_FACTORS = {"KOSPI", "USD_KRW", "KTB_3Y_KR"}

# v0.4-① 기준금리는 계단식(정책 결정일에만 변함)이라 일별 수익률과의 상관이 의미 없다 → KTB_3Y_KR 엣지로 합친다.
#   같은 섹터에 KTB_3Y_KR 엣지가 이미 있으면 중복 제거, 없으면 대상 매크로만 교체.
_seen = {(s, m) for s, m, _, _ in SENS}
MERGED, _sens2, MERGED_FROM = [], [], {}
for s, m, sign, why in SENS:
    if m != "BASE_RATE_KR":
        _sens2.append((s, m, sign, why)); continue
    if (s, "KTB_3Y_KR") in _seen:
        MERGED.append(dict(sector=s, from_macro=m, into="KTB_3Y_KR", action="dedup", expected_sign_was=sign))
    else:
        _sens2.append((s, "KTB_3Y_KR", sign, f"{why} (기준금리→KTB_3Y_KR 합침)"))
        MERGED.append(dict(sector=s, from_macro=m, into="KTB_3Y_KR", action="renamed", expected_sign_was=sign))
    MERGED_FROM.setdefault((s, "KTB_3Y_KR"), []).append(m)
SENS = _sens2

# v0.7: 섹터 → KOSPI(시장 동조) 엣지를 모든 섹터에 둔다. 수경 표에 10개 섹터 값이 다 있고(corr_daily 중앙값),
#   KOSPI는 시장 자체라 시장 효과를 뺄 대상이 아니다. 금융은 위 가설("증권 브로커리지")을 그대로 둔다.
_has_kospi = {s for s, m, _, _ in SENS if m == "KOSPI"}
SENS += [(s["sector_id"], "KOSPI", "+", "시장 동조(섹터 주가가 코스피와 같이 움직이는 정도)")
         for s in SECTORS if s["sector_id"] not in _has_kospi]

# v0.5: 수경이 섹터 중앙값을 집계해 줬다 (2026-11-10, PR #29 코멘트 · 값은 PR #34 뷰 기준).
#   일별 = sector_sensitivities.corr_daily_median (KOSPI·USD_KRW·KTB_3Y_KR·KTB_10Y_KR, 최근 3년, as_of 2026-11-06)
#   월별 = sector_monthly_correlations.corr_monthly_median (CPI_KR·BRENT·DRAM_EXPORT_PRICE, 최근 최대 120개월, 1달 시차)
# 값은 수경이 준 그대로 옮겼고 추정·보정하지 않았다. 표에 없는 (섹터, 매크로) 쌍은 weight를 채우지 않는다.
WSRC = {
    "daily": dict(src="sector_sensitivities.corr_daily_median", window="일별 변화, 최근 3년"),
    "monthly": dict(src="sector_monthly_correlations.corr_monthly_median", window="월별 변화, 최근 최대 120개월, 1달 시차"),
}
W_AS_OF = {"KOSPI": "2026-11-06", "USD_KRW": "2026-11-06", "KTB_3Y_KR": "2026-11-06", "KTB_10Y_KR": "2026-11-06",
           "CPI_KR": "2026-10-01", "BRENT": "2026-09-01", "DRAM_EXPORT_PRICE": "2026-09-01"}
W_N = {"SEC_INDUS": 31, "SEC_IT": 19, "SEC_FIN": 15, "SEC_HEALTH": 7, "SEC_CONS_DISC": 7, "SEC_COMM": 7,
       "SEC_MATERIAL": 5, "SEC_ENERGY": 5, "SEC_CONS_STAP": 2, "SEC_UTIL": 1}   # 일별 종목 수
# 수경 값의 종목 수 = core 소속 종목 수 − 민감도 이력이 없는 종목. 0126Z0(삼성에피스홀딩스)은 신규 상장이라 빠졌다.
W_N_EXCLUDED = {"0126Z0"}
_members = {}
for _c in COMPANIES:
    if _c["ticker"] not in W_N_EXCLUDED:
        _members[_c["sector_id"]] = _members.get(_c["sector_id"], 0) + 1
assert W_N == _members, f"W_N이 core 소속 종목 수와 다르다: {W_N} vs {_members}"
W_N_MONTHLY_OVERRIDE = {("SEC_IT", m): 18 for m in ("CPI_KR", "BRENT", "DRAM_EXPORT_PRICE")}  # LG씨엔에스 상장 24개월 미만 제외
#            KOSPI   USD_KRW KTB_3Y  KTB_10Y CPI_KR  BRENT   DRAM_EXPORT_PRICE
_W_COLS = ["KOSPI", "USD_KRW", "KTB_3Y_KR", "KTB_10Y_KR", "CPI_KR", "BRENT", "DRAM_EXPORT_PRICE"]
_W_ROWS = {
    "SEC_INDUS":     [0.474, -0.002, -0.070, -0.043, 0.104, 0.224, 0.077],
    "SEC_IT":        [0.559, -0.001, -0.111, -0.086, 0.049, 0.132, 0.121],
    "SEC_FIN":       [0.398, -0.004, -0.087, -0.075, 0.059, 0.255, 0.155],
    "SEC_HEALTH":    [0.338, -0.012, -0.079, -0.081, 0.015, 0.099, 0.050],
    "SEC_CONS_DISC": [0.362,  0.001, -0.086, -0.092, 0.118, 0.263, 0.027],
    "SEC_COMM":      [0.299, -0.028, -0.082, -0.075, 0.070, 0.109, 0.111],
    "SEC_MATERIAL":  [0.515, -0.041, -0.118, -0.110, 0.084, 0.110, 0.021],
    "SEC_ENERGY":    [0.395, -0.055, -0.003,  0.005, 0.117, 0.274, 0.090],
    "SEC_CONS_STAP": [0.123, -0.004,  0.002, -0.013, 0.032, 0.182, 0.015],
    "SEC_UTIL":      [0.429, -0.032, -0.178, -0.155, 0.018, 0.144, -0.075],
}
WEIGHTS = {(s, m): v for s, row in _W_ROWS.items() for m, v in zip(_W_COLS, row)}
assert set(W_N) == set(_W_ROWS) == {s["sector_id"] for s in SECTORS}
WEIGHT_FREQ = {"USD_KRW": "daily", "KOSPI": "daily", "KTB_3Y_KR": "daily", "KTB_10Y_KR": "daily",
               "CPI_KR": "monthly", "BRENT": "monthly", "DRAM_EXPORT_PRICE": "monthly"}
NEAR_ZERO = 0.02  # |weight|가 이보다 작으면 부호 검증 대상에서 "약함"으로 분리
LOW_N = 3         # 종목 수가 이보다 적은 섹터는 중앙값이 불안정 (수경)

def _sign_check(sign, w):
    if w is None or sign == "±": return None
    if abs(w) < NEAR_ZERO: return "near_zero"
    return "match" if (w > 0) == (sign == "+") else "mismatch"

# v0.7: 수경 검증(#29 코멘트 2026-11-23)으로 기각한 엣지. 유민 결정 2026-11-23.
# 기준: 시장 효과(일별 코스피, 월별 핵심 98종목 평균)를 뺀 뒤에도 같은 부호가 남고, 섹터 종목의 70% 이상이 같은 부호,
# 방향이 확실한 종목이 과반, 종목 3개 이상. 9개 모두 미달.
_REJ = "수경 #29 코멘트 2026-11-23 (일별 as_of 2026-11-06, 월별 BRENT 2026-09-01·CPI 2026-10-01)"
REJECTED = {
    ("SEC_FIN", "KTB_3Y_KR"): "시장 제거 후 중앙값 은행 −0.007·증권 +0.010·보험 +0.047, 시장·환율 통제 30일 베타 방향 확실 0개",
    ("SEC_INDUS", "BRENT"): "시장 제거 후 중앙값 자본재 +0.001(27종목)·운송 +0.100(4종목, 유의하지 않음). 시장이 t+1월 유가를 앞서 움직인 결과",
    ("SEC_CONS_DISC", "CPI_KR"): "같은 부호 6/7이나 신뢰구간이 0을 포함하지 않는 종목 1/7",
    ("SEC_UTIL", "BRENT"): "종목 1개(한국전력)라 판단 불가",
    ("SEC_IT", "USD_KRW"): "같은 부호 10/19(53%), 방향 확실 3/19",
    ("SEC_CONS_DISC", "USD_KRW"): "같은 부호 4/7(57%), 방향 확실 2/7",
    ("SEC_CONS_STAP", "USD_KRW"): "종목 2개, 방향 확실 0/2",
    ("SEC_HEALTH", "USD_KRW"): "같은 부호 5/7(71%)이나 방향 확실 1/7",
    ("SEC_INDUS", "USD_KRW"): "같은 부호 18/31(58%), 방향 확실 5/31",
}
# #56: 시장 효과 보류(market_unadjusted) 10개. 수경이 시장 효과를 양쪽에서 뺀 편상관을 계산(#56 2026-11-23),
# 같은 기준으로 10개 모두 미달 → 기각. 유민 결정 2026-11-23. detail 앞의 값은 시장 효과 뺀 섹터 중앙값.
_REJ56 = "수경 #56 2026-11-23 (종목·요인 양쪽에서 시장 효과를 뺀 편상관. 일별 최근 3년 ~2026-11-06, 월별 최대 120개월)"
REJECTED_56 = {
    ("SEC_IT", "KTB_3Y_KR"): "0.000, 같은 부호 10/19(53%), 방향 확실 0/19. 원래 값(−0.111)은 거의 시장 효과",
    ("SEC_IT", "DRAM_EXPORT_PRICE"): "+0.037, 같은 부호 11/18(61%), 방향 확실 2/18. 종목 단위(삼성전자·SK하이닉스)는 뚜렷함",
    ("SEC_COMM", "KTB_10Y_KR"): "−0.050, 같은 부호 5/7(71%)이나 방향 확실 2/7",
    ("SEC_CONS_DISC", "KTB_3Y_KR"): "−0.010, 같은 부호 6/7(86%)이나 방향 확실 1/7",
    ("SEC_HEALTH", "KTB_10Y_KR"): "−0.036, 같은 부호 7/7(100%)이나 방향 확실 2/7",
    ("SEC_MATERIAL", "BRENT"): "−0.041(원래 +0.110에서 부호 바뀜), 같은 부호 4/5(80%), 방향 확실 0/5",
    ("SEC_ENERGY", "BRENT"): "+0.139, 같은 부호 4/5(80%)이나 방향 확실 2/5",
    ("SEC_ENERGY", "USD_KRW"): "−0.056, 같은 부호 5/5(100%)이나 방향 확실 0/5",
    ("SEC_UTIL", "USD_KRW"): "−0.036, 종목 1개(한국전력)라 판단 불가",
    ("SEC_UTIL", "KTB_10Y_KR"): "−0.101, 종목 1개(한국전력)라 판단 불가",
}
assert not set(REJECTED) & set(REJECTED_56)
REJECTED_BASIS = {**{k: _REJ for k in REJECTED}, **{k: _REJ56 for k in REJECTED_56}}
REJECTED.update(REJECTED_56)
MARKET_FACTORS = {"KOSPI"}  # 시장 자체라 시장 효과를 뺄 대상이 아님


def _sens_edge(s, m, sign, why):
    inactive = m in INACTIVE_MACROS
    w = None if inactive else WEIGHTS.get((s, m))
    freq = WEIGHT_FREQ.get(m)
    n = None if w is None else W_N_MONTHLY_OVERRIDE.get((s, m), W_N[s])
    check = _sign_check(sign, w)
    # status: inactive = 수집 계획 없는 매크로 / rejected = 검증으로 기각(REJECTED) /
    #   needs_review = 가설과 부호가 반대·0 근처, 또는 시장 효과를 빼지 않은 상관(market_unadjusted) / active
    # reviewed: 사람이 검토를 끝낸 것(active·rejected). 노출은 active 이면서 reviewed 일 때만
    market_adjusted = False  # 수경 섹터 중앙값은 시장 효과를 빼지 않은 상관이다 (#29 코멘트 2026-11-23)
    reason = None
    if inactive:
        status = "inactive"
    elif (s, m) in REJECTED:
        status = "rejected"
    elif w is None or check in ("mismatch", "near_zero"):
        status, reason = "needs_review", check
    elif m not in MARKET_FACTORS and not market_adjusted:
        status, reason = "needs_review", "market_unadjusted"
    elif n < LOW_N:  # 기각 기준과 같이 종목 3개 이상일 때만 노출 (필수소비재 2·유틸리티 1)
        status, reason = "needs_review", "low_n"
    else:
        status = "active"
    return edge("SENSITIVE_TO", s, "SECTOR", m, "MACRO", status=status, reviewed=status in ("active", "rejected"),
                source=WSRC[freq]["src"] if w is not None else None,
                method=f"corr_{freq}_sector_median" if w is not None else None,
                as_of=W_AS_OF[m] if w is not None else None,
                inactive_reason="no_data_source" if inactive else None,
                review_reason=reason,
                rejection=dict(decided_by="유민", decided_on="2026-11-23", basis=REJECTED_BASIS[(s, m)], detail=REJECTED[(s, m)])
                if status == "rejected" else None,
                market_adjusted=market_adjusted,
                weight=w, weight_window=WSRC[freq]["window"] if w is not None else None, weight_n_tickers=n,
                expected_sign=sign, sign_check=check,
                weight_low_n=None if w is None else n < LOW_N,
                weight_status=None if inactive else ("filled" if w is not None else "not_available"),
                weight_frequency=freq, merged_from=MERGED_FROM.get((s, m), []), rationale=why)
SENSITIVE = [_sens_edge(*t) for t in SENS]

# v0.9: 종목 → 매크로 SENSITIVE_TO (#56, 수경 종목 단위 값 2026-11-23). 섹터 중앙값은 관련 없는 종목이 섞여 작아지지만
# 핵심 종목은 시장 효과를 빼도 관계가 남는다. 노출 기준(유민 제안, PR 리뷰로 합의):
#   1) 시장 효과 뺀 값의 95% 구간이 0을 포함하지 않음  2) |값| ≥ 0.10  3) 경제적 가설이 있고 부호가 같음
#   4) 가설 엣지끼리 BH 보정한 q값 < 0.05 (수경 #56 제안 2026-11-23: 보정은 "몇 개를 봤는가"에 맞춘다.
#      가설 없이 데이터에서 찾는 관계는 지표별 99종목 q값으로 거른다 — 지금은 넣지 않음)
# 3)은 다중 비교 대비다(지표마다 99종목이라 5% 기준이면 우연히 ~5개가 확실로 나옴). 가설 없이 데이터에서만 나온 관계
# (레인보우로보틱스→D램, 크래프톤→CPI, 은행·보험→유가 등)와 가설과 부호가 반대인 관계(에이피알→원/달러)는 넣지 않는다.
CO_SENS_MIN = 0.10
# 운영 규칙 (수경 #64 리뷰 2026-11-23, ADR 0003 개정에서 확정):
#   - 이 10개는 방향 확실 68개를 본 뒤 가설을 붙였다(hypothesis_preregistered False). 목록·가설을 여기 고정하고,
#     다음 월간 계산부터 같은 목록을 새 값으로 다시 판정한다. 새 엣지는 가설을 먼저 적고 값을 본다
#   - 다시 판정해서 기준에서 한 번 떨어지면 needs_review(노출 멈춤), 두 달 연속이면 rejected
#   - 근거 칩은 chip_text(인과가 아닌 "경향")를 쓰고, rationale 은 "왜 그럴 수 있는지"로만 쓴다
CO_HYPOTHESIS_FIXED_ON = "2026-11-23"
# 값은 ontology_sensitivity_inputs(#67) 스냅샷을 내보낸 CSV에서 읽는다(ADR 0011 6번, 손으로 옮기지 않음).
# 다시 만들기: python ontology/seed/scripts/export_sensitivity_inputs.py <as_of>  → 아래 날짜를 바꾼다
CO_INPUTS_AS_OF = "2026-11-23"
CO_INPUTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", f"sensitivity_inputs_{CO_INPUTS_AS_OF}.csv")
CO_Q_MAX = 0.05
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from co_hypotheses import CO_HYPOTHESES, co_failed_criteria  # noqa: E402


def bh_q_values(ps):
    """Benjamini-Hochberg q값 (#62 crawling.analytics.ontology_inputs.bh_q_values 와 같은 계산)."""
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    q, running = [0.0] * m, 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, ps[i] * m / rank)
        q[i] = running
    return q


with open(CO_INPUTS, encoding="utf-8") as f:
    CO_ROWS = {(r["group_id"], r["factor"]): r for r in csv.DictReader(f)}
assert all(r["as_of"] == CO_INPUTS_AS_OF for r in CO_ROWS.values()), "CSV 기준일이 CO_INPUTS_AS_OF와 다름"
# 가설 엣지끼리 BH 보정(ADR 0011 2-4). 표에 행이 없는 가설은 보정 개수에서 빠진다
_HAS = [(tk, m) for tk, m, *_ in CO_HYPOTHESES if (tk, m) in CO_ROWS]
CO_Q_HYP = dict(zip(_HAS, bh_q_values([float(CO_ROWS[k]["p_value"]) for k in _HAS])))


_MACRO_NAME = {mm["indicator_id"]: mm["name"] + (" 금리" if mm["category"] == "rate" and "금리" not in mm["name"] else "")
               for mm in MACROS}


def _ga(word):
    """주격 조사 이/가 (마지막 글자 받침 여부)."""
    c = ord(word[-1]) - 0xAC00
    return "이" if 0 <= c < 11172 and c % 28 else "가"


def _chip_text(m, adj, freq):
    name = _MACRO_NAME[m]
    if freq == "daily":
        return f"시장 효과를 빼도 {name}{_ga(name)} 오르는 날 주가가 상대적으로 {'강한' if adj > 0 else '약한'} 경향 (일별, 최근 3년)"
    return f"시장 효과를 빼도 주가가 다음 달 {name} 변화와 {'같은' if adj > 0 else '반대'} 방향으로 움직이는 경향 (월별)"


def _co_sens_edge(tk, m, sign, why, prereg, fixed_on):
    freq = WEIGHT_FREQ[m]
    row = CO_ROWS.get((tk, m))
    if row is None:  # 이번 기준일 표에 값이 없음 → 판정 못 함, 노출 멈춤
        status, review, adj, failed = "needs_review", "no_input", None, None
    else:
        adj = round(float(row["adjusted"]), 3)
        q_hyp = round(CO_Q_HYP[(tk, m)], 6)
        failed = co_failed_criteria(row, sign, q_hyp, CO_SENS_MIN, CO_Q_MAX)
        # 한 번 떨어지면 needs_review(노출 멈춤). 두 달 연속 rejected는 이전 판정이 필요해 월간 재판정 단계에서(ADR 0011 4번)
        status, review = ("needs_review", ",".join(failed)) if failed else ("active", None)
    f = (lambda k: float(row[k])) if row else (lambda k: None)
    r3 = (lambda k: round(float(row[k]), 3)) if row else (lambda k: None)
    # 칸 순서는 v0.9와 같게 둔다(시드 JSON diff를 줄이려고)
    return edge("SENSITIVE_TO", tk, "COMPANY", m, "MACRO", status=status, reviewed=True,
                source=f"ontology_sensitivity_inputs as_of {CO_INPUTS_AS_OF} (수경 #67, 계산 #62)",
                method=row["method"] if row else "partial_corr_market_adjusted", as_of=CO_INPUTS_AS_OF,
                inactive_reason=None, review_reason=review, rejection=None, market_adjusted=True,
                weight=adj, weight_raw=r3("raw"), weight_ci95=[r3("ci_low"), r3("ci_high")] if row else None,
                weight_n_obs=int(row["n_obs"]) if row else None, weight_p_value=f("p_value"),
                weight_q_value_hypothesis=q_hyp if row else None, weight_q_value_all=f("q_value"),
                weight_window=(f"{row['window_start']}~{row['window_end']}" + (" 일별" if freq == "daily" else " 월별, t+1월 지표 변화")) if row else None,
                weight_n_tickers=None, expected_sign=sign, sign_check=_sign_check(sign, adj) if row else None, weight_low_n=False,
                weight_status="filled" if row else "missing", weight_frequency=freq, merged_from=[], rationale=why,
                chip_text=_chip_text(m, adj, freq) if row else None, hypothesis_preregistered=prereg,
                hypothesis_fixed_on=fixed_on, decided_by="유민", decided_on="2026-11-23")


COMPANY_SENSITIVE = [_co_sens_edge(*h) for h in CO_HYPOTHESES]

# IMPACTS: MACRO → MACRO (지표 간 전이). relation: same = 같은 방향, opposite = 반대 방향
IMP = [
 ("US_FFR","US_10Y_YIELD","same","정책금리→장기금리"),("US_FFR","USD_KRW","same","미 금리↑ 달러 강세"),
 ("US_10Y_YIELD","KTB_10Y_KR","same","장기금리 동조화"),("BASE_RATE_KR","KTB_3Y_KR","same","정책금리→단기 시장금리"),
 ("BASE_RATE_KR","KTB_10Y_KR","same","기간 구조"),("BASE_RATE_KR","USD_KRW","opposite","금리차 축소 시 원화 약세"),
 ("BRENT","PPI_KR","same","원자재 원가"),("PPI_KR","CPI_KR","same","생산자→소비자 물가 전가"),
 ("USD_KRW","CPI_KR","same","수입물가"),("CPI_KR","BASE_RATE_KR","same","물가 대응 통화정책"),
 ("VIX","USD_KRW","same","위험회피 시 원화 약세"),("VIX","KOSPI","opposite","위험회피 매도"),
 ("USD_CNY","USD_KRW","same","위안-원 동조화"),("CHINA_PMI_MFG","KOSPI","same","수출 경기"),
 ("DRAM_EXPORT_PRICE","KOSPI","same","반도체 지수 비중"),
]
# v0.8: 데이터로 방향을 확인한 IMPACTS (수경 #61). 판정 기준: 상관은 신뢰구간이 0을 포함하지 않을 때,
# 사건 분석(기준금리 변경 −1→+5거래일)은 같은 방향 65% 이상. 확인된 것은 CPI_KR → BASE_RATE_KR 하나.
# 나머지(기준금리 → 국고채·환율 52~57%, 환율 → CPI, D램 → KOSPI)는 unclear 라 초안 유지.
IMPACT_EVIDENCE = {
    ("CPI_KR", "BASE_RATE_KR"): dict(method="corr_monthly_lag1", corr=0.166, ci95=[0.04, 0.29], n=240,
                                     result="same", decided_by="유민", decided_on="2026-11-23"),
}


def _impact(a, b, rel, why):
    off = {a, b} & INACTIVE_MACROS
    ev = IMPACT_EVIDENCE.get((a, b))
    if ev:
        assert ev["result"] == rel, ("데이터 방향과 초안이 다르면 확정하지 않는다", a, b)
        base = dict(status="active", reviewed=True, source="pipeline:macro_data (" + _DIR_SRC + ")",
                    method=ev["method"], as_of="2026-11-23")
    else:
        base = {**DRAFT, "status": "inactive" if off else "draft"}
    return edge("IMPACTS", a, "MACRO", b, "MACRO", **base, inactive_reason="no_data_source" if off else None,
                inactive_macros=sorted(off), direction=rel, evidence=ev, rationale=why)


IMPACTS = [_impact(*x) for x in IMP]

BELONGS = [edge("BELONGS_TO", c["ticker"], "COMPANY", c["sector_id"], "SECTOR", status="active", reviewed=True,
                source="pipeline:companies.sector_l1(WICS)", method="pipeline", as_of=CORE_EXPORT)
           for c in COMPANIES]

# ───────────────────────── 검증 ─────────────────────────
sec_ids = {s["sector_id"] for s in SECTORS}; mac_ids = {m["indicator_id"] for m in MACROS}
iss_ids = {i["issue_id"] for i in ISSUES}
for e in SENSITIVE: assert e["src"] in sec_ids and e["dst"] in mac_ids, e
for e in IMPACTS: assert e["src"] in mac_ids and e["dst"] in mac_ids, e
for e in IMPACT_EDGES: assert e["dst"] in sec_ids or e["dst"] in TICKERS, e
for c in COMPANIES: assert c["sector_id"] in sec_ids, c
assert len(iss_ids) == len(ISSUES)
assert len(mac_ids) == len(MACROS), "macro indicator_id 중복"
_used = {c["sector_id"] for c in COMPANIES}
assert sec_ids == _used, f"소속 종목이 없는 섹터: {sorted(sec_ids - _used)}"
for e in SENSITIVE: assert e["weight"] is None or e["source"], e  # weight는 출처 없이 못 채운다
assert len(INACTIVE_MACROS) == 6, INACTIVE_MACROS
for e in SENSITIVE + IMPACTS:  # 비활성 매크로에 걸린 엣지는 반드시 비활성, 활성 엣지는 활성 매크로만 잇는다
    touch = {e["src"], e["dst"]} & INACTIVE_MACROS
    assert (e["status"] == "inactive") == bool(touch), e
for e in SENSITIVE:
    assert (e["weight_status"] is None) == (e["status"] == "inactive"), e
    if e["weight_status"] == "filled":
        assert all(e[k] is not None for k in ("weight", "source", "weight_window", "as_of", "weight_n_tickers")), e
        assert -1.0 <= e["weight"] <= 1.0, e
# 같은 섹터에 금리 엣지(국채 3년·10년)는 하나만 (상관 0.9라 같은 효과 이중 계상 방지)
_rate_cnt = {}
for e in SENSITIVE:
    if e["status"] != "inactive" and e["dst"] in ("KTB_3Y_KR", "KTB_10Y_KR"):
        _rate_cnt[e["src"]] = _rate_cnt.get(e["src"], 0) + 1
assert all(c == 1 for c in _rate_cnt.values()), _rate_cnt
assert len({(e["src"], e["dst"]) for e in SENSITIVE}) == len(SENSITIVE), "SENSITIVE_TO 쌍 중복"

nodes = dict(sectors=SECTORS, macros=MACROS, issues=ISSUES, companies_t1=COMPANIES)
for e in COMPANY_SENSITIVE: assert e["src"] in TICKERS and e["dst"] in mac_ids and e["dst"] not in INACTIVE_MACROS, e
assert len({(e["src"], e["dst"]) for e in COMPANY_SENSITIVE}) == len(COMPANY_SENSITIVE), "종목 SENSITIVE_TO 쌍 중복"
edges = dict(belongs_to=BELONGS, sensitive_to=SENSITIVE + COMPANY_SENSITIVE, impacts=IMPACTS,
             benefits_hurts=IMPACT_EDGES, exposed_to=EXPOSED)
# 노출 가능한 노드·엣지는 출처·방법·기준일이 반드시 있다 (헌법 원칙 IV)
for k, v in edges.items():
    for e in v:
        assert isinstance(e["reviewed"], bool) and e["status"] in ("active", "draft", "needs_review", "inactive", "rejected"), e
        if e["status"] == "active" and e["reviewed"]:
            assert e["source"] and e["method"] and e["as_of"], e
for k, v in nodes.items():
    for n in v:
        assert isinstance(n["reviewed"], bool) and n["status"] in ("active", "draft", "inactive"), n
assert set(REJECTED) <= {(e["src"], e["dst"]) for e in SENSITIVE}, "REJECTED에 없는 엣지가 있다"
meta = dict(version="seed-v0.10", generated=GENERATED, spec="온톨로지 기획서 v1.2",
            exposure_rule='status == "active" and reviewed == True (ADR 0008). draft_fields 는 include_draft 일 때만',
            merged_sensitive_edges=MERGED, inactive_macros=sorted(INACTIVE_MACROS),
            t1_definition="KOSPI+KOSDAQ 통합 시가총액 상위 100 보통주(우선주 제외). 수경 파이프라인 companies.is_core, 2026-10-22 지정 후 고정",
            core_export=CORE_EXPORT, tier_assigned_on=TIER_ASSIGNED, sensitivities_latest_as_of=SENS_AS_OF,
            dropped_issue_edges=DROPPED,
            not_included=["COMPETES_WITH (COMPETITOR→COMPANY 통합 여부 미결)"])
# 원본은 이 JSON 하나. 읽기·노출 판정은 손으로 쓴 ontology_seed.py 로더가 한다 (v0.6: nodes/·edges/·생성 .py 삭제)
with open(f"{OUT}/ontology_seed.json", "w", encoding="utf-8", newline="\n") as f:
    json.dump(dict(meta=meta, nodes=nodes, edges=edges), f, ensure_ascii=False, indent=2)
    f.write("\n")

print("nodes:", {k: len(v) for k, v in nodes.items()})
print("edges:", {k: len(v) for k, v in edges.items()})
print("markets:", {m: sum(c["market"] == m for c in COMPANIES) for m in ("KOSPI", "KOSDAQ")})
print("macros collecting:", sum(m["in_pipeline"] for m in MACROS), "/", len(MACROS))
print("sensitive_to status:", {k: sum(e["status"] == k for e in SENSITIVE) for k in ("active", "needs_review", "rejected", "inactive")},
      "| weight_status:", {k: sum(e["weight_status"] == k for e in SENSITIVE) for k in ("filled", "not_available")},
      "| sign_check:", {k: sum(e["sign_check"] == k for e in SENSITIVE) for k in ("match", "mismatch", "near_zero")})
print("company sensitive_to:", len(COMPANY_SENSITIVE))
print("impacts status:", {k: sum(e["status"] == k for e in IMPACTS) for k in ("active", "draft", "inactive")})
print("exposed edges:", {k: sum(e["status"] == "active" and e["reviewed"] for e in v) for k, v in edges.items()})
print("macros inactive:", sorted(INACTIVE_MACROS))
print("BASE_RATE_KR 합침:", [(m["sector"], m["action"]) for m in MERGED])
print("dropped issue edges (core에 없는 종목):", DROPPED)
print("무결성 검사 통과")
