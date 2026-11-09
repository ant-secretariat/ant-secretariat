"""온톨로지 관계사전 시드 v0.3 생성 — 기획서 v1.2 엣지 7종 정의 기준

사용법: python build_seed.py <core_companies.csv> <출력 폴더>
  - core_companies.csv 는 수경 파이프라인 companies.is_core 내보내기 (extract_t1.py 로 형식 검증)
  - 출력 폴더 아래 nodes/, edges/, ontology_seed_all.json, ontology_seed.py 를 덮어씀

v0.3 변경 (수경 파이프라인 실제 코드·답변 2026-11-10 대조, 근거는 SOURCES.md)
  - T1 = 파이프라인 core 100 (KOSPI 90 + KOSDAQ 10), 섹터 = companies.sector_l1(WICS)
  - 매크로 ID = 파이프라인 이름 (OIL_BRENT→BRENT, KOSPI_INDEX→KOSPI), 수집 상태 필드 추가
  - SEC_REAL_ESTATE 삭제 (WICS 대분류에 없음, 소속 종목 0개)

v0.4 변경 (유민 결정: 수집 계획 없는 매크로는 삭제하지 않고 비활성 보관)
  - 수집 계획 없는 매크로 7개와 거기 걸린 SENSITIVE_TO·IMPACTS 엣지 → status "inactive", inactive_reason "no_data_source"
  - BASE_RATE_KR 대상 SENSITIVE_TO 3개 → KTB_3Y_KR로 합침 (계단식이라 일별 상관 무의미)
  - 수집 중이나 회귀 요인이 아닌 KTB_10Y_KR·CPI_KR·BRENT 엣지 → weight_status "factor_requested"
  - SENSITIVE_TO의 weight_coverage 필드를 weight_status·weight_frequency로 대체
"""
import csv, json, os, sys

RAW, OUT = sys.argv[1], sys.argv[2]
CORE_EXPORT = "2026-11-09"      # core_companies.csv 내보낸 날 (수경)
TIER_ASSIGNED = "2026-10-22"    # 파이프라인이 시총 순위로 T1을 지정한 날. 이후 고정
SENS_AS_OF = "2026-11-06"       # sensitivities 최신 as_of (수경)
os.makedirs(OUT, exist_ok=True)

# ───────────────────────── 1. SECTOR ─────────────────────────
S = lambda i, n, en, g, cyc, rate, fx, note: dict(
    sector_id=i, name=n, name_en=en, gics_code=g, cycle_type=cyc,
    rate_sensitivity=rate, fx_sensitivity=fx, notes=note, source="claude_draft")
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
    M("DRAM_PRICE", "DRAM 가격", "commodity", "up_positive", "USD", "TrendForce", None, "weekly/monthly", False, "유료 소스. 대체 지표 협의 필요."),
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
    "KOSPI": ("index_daily", "1001", None),
}
for _m in MACROS:
    _p = PIPE.get(_m["indicator_id"])
    _m["in_pipeline"] = bool(_p)
    _m["pipeline_status"] = "collecting" if _p else "not_planned"
    _m["pipeline_table"], _m["pipeline_key"], _m["pipeline_item_code"] = _p or (None, None, None)
    # v0.4: 수집 계획 없는 지표는 삭제하지 않고 비활성으로 보관 (데이터가 생기면 status만 active로 바꾼다)
    _m["status"] = "active" if _p else "inactive"
    _m["inactive_reason"] = None if _p else "no_data_source"
    if not _p:
        _m["notes"] += " 수집 계획 없음(수경 2026-11-10) — 필요하면 추가 요청."
INACTIVE_MACROS = {m["indicator_id"] for m in MACROS if m["status"] == "inactive"}

# ───────────────────────── 5. COMPANY (T1 = 수경 파이프라인 core 100) ─────────────────────────
# 종목·시장·섹터는 파이프라인 값 그대로. 지주사 여부·세부 산업은 Claude 초안(섹터 상속 보정용).
HOLDINGS = {"402340", "028260", "034730", "009540", "003550", "180640", "267250", "000150", "0126Z0", "078930", "006260", "000880"}
SUB = {  # 세부 산업 메모 (탐색 시 섹터 상속 보정용)
 "373220":"2차전지","006400":"2차전지","003670":"양극재","402340":"SK하이닉스 지분 투자회사",
 "009540":"조선 중간지주","0126Z0":"삼성바이오에피스 지주","078930":"정유 중심 지주",
 "278470":"뷰티 디바이스·화장품","011200":"컨테이너 해운","086280":"자동차 물류","012450":"방산·항공엔진",
 "034020":"원전·발전설비","267260":"전력기기","298040":"전력기기","010120":"전력기기","000500":"전선",
 "062040":"전력기기(변압기)","007660":"PCB","353200":"PCB","042700":"반도체 장비",
}
COMPANIES = []
with open(RAW, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        code = row["ticker"]
        COMPANIES.append(dict(
            ticker=code, name=row["name"], market=row["market"], sector_id=WICS_L1[row["sector_l1"]],
            sector_l1=row["sector_l1"], sector_l2=row["sector_l2"], sub_industry=SUB.get(code),
            is_holding=code in HOLDINGS, tier="T1", is_core=True, tier_assigned_on=TIER_ASSIGNED,
            sector_source="pipeline:companies.sector_l1(WICS)", sub_industry_source="claude_draft"))
TICKERS = {c["ticker"]: c["name"] for c in COMPANIES}
assert len(COMPANIES) == 100 and len(TICKERS) == 100, "core는 100종목·중복 없음이어야 한다"
assert HOLDINGS <= set(TICKERS) and set(SUB) <= set(TICKERS), "HOLDINGS/SUB에 core에 없는 종목이 있다"

# ───────────────────────── 3. ISSUE + BENEFITS/HURTS ─────────────────────────
# 필수 속성(v1.2): evidence_chunk_ids(근거 청크), valid_from/valid_until(유효기간)
REVIEW = {"persistent": 180, "cyclical": 90, "event_driven": 30}
ISSUES, IMPACT_EDGES, DROPPED = [], [], []  # DROPPED: core에 없어 버린 (이슈, 종목) 엣지
def I(iid, name, typ, pol, dur, agendas, note, targets):
    ISSUES.append(dict(
        issue_id=iid, name=name, type=typ, polarity=pol, duration=dur, agenda_ids=agendas,
        notes=note, evidence_chunk_ids=[], valid_from=None, valid_until=None,
        review_cycle_days=REVIEW[dur], status="draft", labeled_by="claude_draft"))
    rel = "BENEFITS" if pol == "positive" else "HURTS"
    for tgt, strength in targets:
        ttype = "SECTOR" if tgt.startswith("SEC_") else "COMPANY"
        if ttype == "COMPANY" and tgt not in TICKERS:
            DROPPED.append([iid, tgt]); continue
        IMPACT_EDGES.append(dict(edge_type=rel, from_node=iid, from_type="ISSUE",
                                 to_node=tgt, to_type=ttype, strength=strength))

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
EXPOSED = [dict(edge_type="EXPOSED_TO", from_node=e["to_node"], from_type="COMPANY",
                to_node=e["from_node"], to_type="ISSUE", exposure=EXP[e["strength"]],
                exposure_source="claude_draft (strength 매핑: high .9 / mid .6 / low .3)")
           for e in IMPACT_EDGES if e["to_type"] == "COMPANY"]

# ───────────────────────── 4. SENSITIVE_TO / IMPACTS ─────────────────────────
# SENSITIVE_TO: SECTOR → MACRO. weight는 수경 회귀(상관 기반 민감도)로만 채움.
# expected_sign = 회귀 결과 부호 검증용 사전 가설 (weight 아님)
SENS = [
 ("SEC_IT","BASE_RATE_KR","-","성장주 할인율"),("SEC_IT","US_10Y_YIELD","-","글로벌 성장주 할인율"),
 ("SEC_IT","USD_KRW","+","수출 환산 이익"),("SEC_IT","DRAM_PRICE","+","메모리 실적 직결"),("SEC_IT","VIX","-","고베타"),
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

# weight_status (활성 엣지만):
#   aggregation_pending = 회귀 요인에 있음. 수경이 섹터별 corr_daily 중앙값 + 종목 수를 집계해 줄 예정 (최신 as_of 2026-11-06)
#   factor_requested    = 매크로는 수집 중이나 회귀 요인이 아님. 수경에게 요인 추가·별도 산출을 요청
# 비활성(수집 계획 없는 매크로에 걸린 엣지)은 weight_status = None
WEIGHT_FREQ = {"USD_KRW": "daily", "KOSPI": "daily", "KTB_3Y_KR": "daily", "KTB_10Y_KR": "daily",
               "CPI_KR": "monthly", "BRENT": "monthly"}
def _sens_edge(s, m, sign, why):
    inactive = m in INACTIVE_MACROS
    return dict(edge_type="SENSITIVE_TO", from_node=s, from_type="SECTOR", to_node=m, to_type="MACRO",
                status="inactive" if inactive else "active",
                inactive_reason="no_data_source" if inactive else None,
                weight=None, expected_sign=sign, weight_source=None, weight_window=None,
                weight_as_of=None, weight_n_tickers=None,
                weight_status=None if inactive else ("aggregation_pending" if m in SENS_FACTORS else "factor_requested"),
                weight_frequency=WEIGHT_FREQ.get(m),
                merged_from=MERGED_FROM.get((s, m), []),
                rationale=why)
SENSITIVE = [_sens_edge(*t) for t in SENS]

# IMPACTS: MACRO → MACRO (지표 간 전이). relation: same = 같은 방향, opposite = 반대 방향
IMP = [
 ("US_FFR","US_10Y_YIELD","same","정책금리→장기금리"),("US_FFR","USD_KRW","same","미 금리↑ 달러 강세"),
 ("US_10Y_YIELD","KTB_10Y_KR","same","장기금리 동조화"),("BASE_RATE_KR","KTB_3Y_KR","same","정책금리→단기 시장금리"),
 ("BASE_RATE_KR","KTB_10Y_KR","same","기간 구조"),("BASE_RATE_KR","USD_KRW","opposite","금리차 축소 시 원화 약세"),
 ("BRENT","PPI_KR","same","원자재 원가"),("PPI_KR","CPI_KR","same","생산자→소비자 물가 전가"),
 ("USD_KRW","CPI_KR","same","수입물가"),("CPI_KR","BASE_RATE_KR","same","물가 대응 통화정책"),
 ("VIX","USD_KRW","same","위험회피 시 원화 약세"),("VIX","KOSPI","opposite","위험회피 매도"),
 ("USD_CNY","USD_KRW","same","위안-원 동조화"),("CHINA_PMI_MFG","KOSPI","same","수출 경기"),
 ("DRAM_PRICE","KOSPI","same","반도체 지수 비중"),
]
IMPACTS = [dict(edge_type="IMPACTS", from_node=a, from_type="MACRO", to_node=b, to_type="MACRO",
                status="inactive" if {a, b} & INACTIVE_MACROS else "active",
                inactive_reason="no_data_source" if {a, b} & INACTIVE_MACROS else None,
                inactive_macros=sorted({a, b} & INACTIVE_MACROS),
                relation=rel, rationale=why) for a, b, rel, why in IMP]

BELONGS = [dict(edge_type="BELONGS_TO", from_node=c["ticker"], from_type="COMPANY",
                to_node=c["sector_id"], to_type="SECTOR") for c in COMPANIES]

# ───────────────────────── 검증 ─────────────────────────
sec_ids = {s["sector_id"] for s in SECTORS}; mac_ids = {m["indicator_id"] for m in MACROS}
iss_ids = {i["issue_id"] for i in ISSUES}
for e in SENSITIVE: assert e["from_node"] in sec_ids and e["to_node"] in mac_ids, e
for e in IMPACTS: assert e["from_node"] in mac_ids and e["to_node"] in mac_ids, e
for e in IMPACT_EDGES: assert e["to_node"] in sec_ids or e["to_node"] in TICKERS, e
for c in COMPANIES: assert c["sector_id"] in sec_ids, c
assert len(iss_ids) == len(ISSUES)
assert len(mac_ids) == len(MACROS), "macro indicator_id 중복"
_used = {c["sector_id"] for c in COMPANIES}
assert sec_ids == _used, f"소속 종목이 없는 섹터: {sorted(sec_ids - _used)}"
for e in SENSITIVE: assert e["weight"] is None or e["weight_source"], e  # weight는 출처 없이 못 채운다
assert len(INACTIVE_MACROS) == 7, INACTIVE_MACROS
for e in SENSITIVE + IMPACTS:  # 비활성 매크로에 걸린 엣지는 반드시 비활성, 활성 엣지는 활성 매크로만 잇는다
    touch = {e["from_node"], e["to_node"]} & INACTIVE_MACROS
    assert (e["status"] == "inactive") == bool(touch), e
for e in SENSITIVE:
    assert (e["weight_status"] is None) == (e["status"] == "inactive"), e
assert len({(e["from_node"], e["to_node"]) for e in SENSITIVE}) == len(SENSITIVE), "SENSITIVE_TO 쌍 중복"

nodes = dict(sectors=SECTORS, macros=MACROS, issues=ISSUES, companies_t1=COMPANIES)
edges = dict(belongs_to=BELONGS, sensitive_to=SENSITIVE, impacts=IMPACTS,
             benefits_hurts=IMPACT_EDGES, exposed_to=EXPOSED)
meta = dict(version="seed-v0.4", generated="2026-11-10", spec="온톨로지 기획서 v1.2",
            merged_sensitive_edges=MERGED, inactive_macros=sorted(INACTIVE_MACROS),
            t1_definition="KOSPI+KOSDAQ 통합 시가총액 상위 100 보통주(우선주 제외). 수경 파이프라인 companies.is_core, 2026-10-22 지정 후 고정",
            core_export=CORE_EXPORT, tier_assigned_on=TIER_ASSIGNED, sensitivities_latest_as_of=SENS_AS_OF,
            dropped_issue_edges=DROPPED,
            not_included=["COMPETES_WITH (COMPETITOR→COMPANY 통합 여부 미결)"])
os.makedirs(f"{OUT}/nodes", exist_ok=True); os.makedirs(f"{OUT}/edges", exist_ok=True)
for k, v in nodes.items(): json.dump(v, open(f"{OUT}/nodes/{k}.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
for k, v in edges.items(): json.dump(v, open(f"{OUT}/edges/{k}.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(dict(meta=meta, nodes=nodes, edges=edges),
          open(f"{OUT}/ontology_seed_all.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

# ───────────────────────── Python dict 모듈 ─────────────────────────
from pprint import pformat
pf = lambda o: pformat(o, width=110, sort_dicts=False)
py = f'''"""개미비서단 온톨로지 관계사전 — Phase A 시드 ({meta["version"]})

생성: {meta["generated"]} · 기준 스펙: {meta["spec"]} · T1 지정일: {TIER_ASSIGNED} (core 내보내기 {CORE_EXPORT})
T1 정의: {meta["t1_definition"]}

- SENSITIVE_TO.weight 는 전부 None. 수경 sensitivities(섹터별 corr_daily 중앙값 + 종목 수)로만 채운다.
  weight_status: aggregation_pending(회귀 요인에 있음, 수경 집계 대기) / factor_requested(수집 중이나 요인 아님, 수경에 요청).
- status == "inactive" (inactive_reason "no_data_source") 인 매크로·엣지는 수집 계획이 없어 보관만 한다.
  주입·Judge 경로 검증에는 active_edges() / active_macros() / company_context() 만 쓴다.
  expected_sign 은 회귀 부호 검증용 사전 가설이며 weight 로 쓰지 않는다.
- *_source == "claude_draft" 인 값은 유민 검토 전 초안.
- ISSUE 의 evidence_chunk_ids / valid_from / valid_until 은 필수 속성이지만 아직 비어 있음.
"""
from __future__ import annotations

META = {pf(meta)}

SECTORS: dict[str, dict] = {pf({s["sector_id"]: s for s in SECTORS})}

MACROS: dict[str, dict] = {pf({m["indicator_id"]: m for m in MACROS})}

ISSUES: dict[str, dict] = {pf({i["issue_id"]: i for i in ISSUES})}

COMPANIES_T1: dict[str, dict] = {pf({c["ticker"]: c for c in COMPANIES})}

EDGES: dict[str, list[dict]] = {pf(edges)}


def is_active(record: dict) -> bool:
    """status 필드가 없으면(섹터·종목·이슈 등) 활성으로 본다. status == "inactive" 는 주입·경로 검증 대상이 아니다."""
    return record.get("status", "active") != "inactive"


def active_macros() -> dict[str, dict]:
    return {{k: v for k, v in MACROS.items() if is_active(v)}}


def active_edges(kind: str) -> list[dict]:
    """EDGES[kind] 중 활성 엣지만. get_ontology_context 주입과 Judge 경로 검증은 이 함수만 쓴다."""
    return [e for e in EDGES[kind] if is_active(e)]


def company_context(ticker: str, include_inactive: bool = False) -> dict:
    """2홉: COMPANY → SECTOR → MACRO(SENSITIVE_TO) + COMPANY ↔ ISSUE. Phase A 확인용 헬퍼.

    기본은 활성 엣지만 돌려준다. 비활성(수집 계획 없는 매크로) 엣지가 필요하면 include_inactive=True.
    """
    c = COMPANIES_T1.get(ticker)
    if c is None:
        return {{}}
    sec = c["sector_id"]
    issues: dict[str, dict] = {{}}
    for e in EDGES["benefits_hurts"]:  # 섹터 엣지 먼저, 종목 엣지가 덮어씀 (종목 단위 우선)
        if e["to_node"] == sec:
            issues[e["from_node"]] = {{**ISSUES[e["from_node"]], "relation": e["edge_type"],
                                      "strength": e["strength"], "via": "SECTOR"}}
    for e in EDGES["benefits_hurts"]:
        if e["to_node"] == ticker:
            issues[e["from_node"]] = {{**ISSUES[e["from_node"]], "relation": e["edge_type"],
                                      "strength": e["strength"], "via": "COMPANY"}}
    return {{
        "company": c,
        "sector": SECTORS[sec],
        "sector_sensitivities": [e for e in EDGES["sensitive_to"]
                                 if e["from_node"] == sec and (include_inactive or is_active(e))],
        "issues": list(issues.values()),
    }}
'''
open(f"{OUT}/ontology_seed.py", "w", encoding="utf-8").write(py)

print("nodes:", {k: len(v) for k, v in nodes.items()})
print("edges:", {k: len(v) for k, v in edges.items()})
print("markets:", {m: sum(c["market"] == m for c in COMPANIES) for m in ("KOSPI", "KOSDAQ")})
print("macros collecting:", sum(m["in_pipeline"] for m in MACROS), "/", len(MACROS))
print("sensitive_to status:", {k: sum(e["status"] == k for e in SENSITIVE) for k in ("active", "inactive")},
      "| weight_status:", {k: sum(e["weight_status"] == k for e in SENSITIVE) for k in ("aggregation_pending", "factor_requested")})
print("impacts status:", {k: sum(e["status"] == k for e in IMPACTS) for k in ("active", "inactive")})
print("macros inactive:", sorted(INACTIVE_MACROS))
print("BASE_RATE_KR 합침:", [(m["sector"], m["action"]) for m in MERGED])
print("dropped issue edges (core에 없는 종목):", DROPPED)
print("무결성 검사 통과")
