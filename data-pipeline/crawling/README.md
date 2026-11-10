# Agent B 데이터 수집 인프라

AI Agent 기반 증권 리포트 분석 서비스에서 Agent B는 공통 데이터 인프라와 데이터 수집을 담당합니다. 리포트 목록, 표준 메타데이터, PDF 원본 파일 경로, 목표주가/투자의견, 주가 데이터, 매크로 데이터를 SQLite와 로컬 파일 시스템에 저장합니다.

## 지원 기업

수집 대상은 7개 기업으로 제한합니다. 내부 매칭 기준은 `ticker`이며, alias 기반 resolver는 `config/supported_companies.py`에 있습니다.

```text
005930 삼성전자
000660 SK하이닉스
005380 현대차
035420 NAVER
003230 삼양식품
352820 HYBE
373220 LG에너지솔루션
```

## 설치

Python 3.11 이상을 권장합니다.

레포 루트에서 실행합니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 환경 설정

프로젝트 루트의 `.env`를 자동으로 읽습니다. 셸, Docker, CI에 같은 환경변수가 있으면 해당 값이 우선합니다.

```dotenv
CRAWLER_SOURCE=naver
COLLECTION_MONTHS=1
MAX_PAGES=3
MAX_REPORTS_PER_COMPANY=10
MAX_TOTAL_REPORTS=50

REQUEST_TIMEOUT=20
REQUEST_INTERVAL_SECONDS=1.5
MAX_RETRIES=3

PRICE_DATA_PROVIDER=naver
MACRO_DATA_PROVIDER=ecos
NEWS_DATA_PROVIDER=naver
DISCLOSURE_DATA_PROVIDER=dart
INCLUDE_PRICE_DATA=false
INCLUDE_MACRO_DATA=false
INCLUDE_NEWS_DATA=false
INCLUDE_DISCLOSURE_DATA=false
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
DART_API_KEY=

CRAWLER_SCHEDULE_HOUR=7
CRAWLER_SCHEDULE_MINUTE=0
SCHEDULE_TIMEZONE=Asia/Seoul
```

로컬 MVP 기본값은 최근 1개월, 기업당 최대 10개, 전체 실행 최대 50개 리포트입니다. 운영 환경이나 클라우드 스토리지를 사용할 때는 `COLLECTION_MONTHS=3` 또는 `COLLECTION_MONTHS=6`처럼 확장할 수 있습니다.

## 실행

DB 초기화:

```bash
python main.py --init-db
```

수동 실행:

```bash
python main.py --run-once --source naver
python main.py --run-once --source kirs
python main.py --run-once --source all
```

옵션 포함 실행:

```bash
python main.py --run-once --source naver --months 6 --max-pages 3 --include-price-data --include-macro-data --include-news-data --include-disclosure-data
```

스케줄 실행:

```bash
python main.py --schedule
```

APScheduler가 `.env`의 `CRAWLER_SCHEDULE_HOUR`, `CRAWLER_SCHEDULE_MINUTE`, `SCHEDULE_TIMEZONE`에 따라 매일 실행합니다.

## 처리 흐름

1. `crawler_runs`에 실행 시작 기록
2. 지원 기업 7개 목록 로드
3. source별 리포트 목록 수집
4. company/ticker 매칭 및 report type 정규화
5. 재현 가능한 `report_id` 생성
6. `report_metadata` 저장
7. 목표주가/투자의견이 목록 HTML 또는 PDF 텍스트에서 확인되면 `target_price_data` 저장
8. `pdf_url` 중복 검사
9. PDF 다운로드, Content-Type/시그니처 검증, SHA-256 계산
10. SHA-256 중복 검사
11. 다운로드된 PDF에서 목표주가/투자의견 보강
12. `report_files` 저장 및 `report_metadata.status` 갱신
13. 옵션에 따라 실제 provider의 주가/매크로/뉴스/공시 데이터 저장
14. `crawler_runs`에 실행 결과 저장

## 저장 구조

PDF 원본은 DB에 직접 저장하지 않고 파일 시스템에 저장합니다.

```text
storage/raw_report_pdfs/{source}/{year}/{month}/{day}/{report_id}.pdf
```

DB에는 `file_path`만 저장합니다. PDF 원본은 내부 처리와 추적용이며 서비스 화면에서 직접 재배포하지 않는 전제입니다.

## DB 스키마

SQLite 테이블:

- `report_metadata`: 리포트 표준 메타데이터와 수집 상태
- `report_files`: PDF 파일 경로, URL, SHA-256, Content-Type, 유효성
- `target_price_data`: 리포트 목록 또는 PDF 텍스트에서 추출한 목표주가/투자의견
- `price_data`: Naver Finance 또는 선택 provider 기반 주가 데이터
- `macro_data`: ECOS/Naver 시장지표 또는 선택 provider 기반 매크로 데이터
- `news_metadata`: Naver Search API 기반 뉴스 메타데이터와 원문 본문 텍스트
- `disclosure_metadata`: OpenDART 기반 공시 메타데이터, 공시 유형, 원문 본문 텍스트
- `crawler_runs`: 실행 단위 집계와 실패 사유

상태값:

```text
discovered, success, failed, duplicate, no_pdf_url
```

## 중복 처리

중복은 두 단계로 확인합니다.

1. `pdf_url`이 `report_metadata` 또는 `report_files`에 이미 성공/중복 상태로 존재하면 다운로드하지 않고 `duplicate`
2. 다운로드 후 계산한 `sha256`이 이미 존재하면 임시 파일을 삭제하고 `duplicate`

중복 건은 `crawler_runs.duplicate_count`에 반영됩니다.

## Report Type

`normalize_report_type(raw_type, title)`은 다음 코드로 정규화합니다.

```text
company_report
issue_comment
industry_report
technical_report
ai_company_report
unknown
```

## 수치 데이터 Provider

기본값은 실제 수집 provider입니다.

- `PRICE_DATA_PROVIDER=naver`: Naver Finance 일별 시세를 수집해 `price_data`에 저장
- `MACRO_DATA_PROVIDER=ecos`: 한국은행 ECOS에서 기준금리, 국고채 3·10년 금리, CPI, USD/KRW 환율, 유가(WTI·Dubai·Brent 월평균), 통관 수출·수입과 무역수지(수출 − 수입), 전산업생산지수(계절조정), D램 수출물가지수(`DRAM_EXPORT_PRICE`, 달러기준 월별. TrendForce D램 가격이 유료라 대체 지표)를 수집
- `MACRO_DATA_PROVIDER=naver`: Naver 시장지표에서 USD/KRW만 수집

실제 수치 데이터까지 포함해 실행:

```bash
python main.py --run-once --source naver --include-price-data --include-macro-data
```

ECOS 수집에는 `ECOS_API_KEY`가 필요합니다. 네트워크가 없는 테스트 환경에서는 `.env`에서 `PRICE_DATA_PROVIDER=mock`,
`MACRO_DATA_PROVIDER=mock`으로 바꿀 수 있습니다. 추후 한국투자 Open API 같은 provider로 교체할 수 있도록 `collectors/`에 provider 경계를 두었습니다.

Supabase `macro_data` 테이블 적재(`SUPABASE_DB_URL`, `ECOS_API_KEY` 필요):

```bash
python -m crawling.macro_loader --backfill   # 2000년부터 전체 이력
python -m crawling.macro_loader --daily      # 최근 구간(일별 45일, 월별 400일) 갱신
```

DART 주요 재무계정(`financials`)과 파생 지표 뷰(`financial_metrics`: 부채비율, 영업이익률, 매출 성장률 YoY, ROE TTM) 적재:

```bash
python -m crawling.financials_loader --backfill   # 최근 3개 사업연도 + 올해
python -m crawling.financials_loader --recent     # 작년·올해 다시 받기 (분기 공시 시즌에 주 1회)
```

- 손익 항목의 `amount`는 분기 단독(3개월), `amount_ytd`는 연초부터 누적. 4분기 단독은 연간 − 3분기 누적
- 시점 관리: 정정공시가 와도 덮어쓰지 않고 접수번호(`rcept_no`)별로 쌓는다. `rcept_dt`는 접수일. 현재 기준 최신 값은 뷰 `financials_latest`, 과거 시점 기준은 함수 `financials_as_of('YYYY-MM-DD')`
- 4분기 손익은 사업보고서와 3분기 보고서 중 더 늦게 접수된 쪽의 접수번호를 쓴다(3분기가 나중에 정정되면 4분기도 새 버전으로 쌓임)
- DART는 최신 버전만 주므로, 원래 값을 남기려면 공시 시즌에 정정이 나오기 전에 받아 두어야 한다
- 지표는 연결재무제표 우선, 없으면 별도. ROE는 지배주주 귀속분이 아닌 전체 당기순이익 기준
- 은행·보험·증권은 DART 주요계정에 매출액이 없어 매출 관련 지표가 비고, 부채비율은 업종 특성상 1,000%를 넘는다

WICS 섹터 분류(`companies.sector_l1` 대분류, `sector_l2` 중분류) 갱신. 분류는 자주 바뀌지 않아 주 1회면 충분합니다:

```bash
python -m crawling.market_loader --sectors
```

wiseindex.com의 robots.txt는 일반 크롤러를 허용하지 않으므로 팀 내부 테스트 범위에서만 사용합니다. 우선주는 보통주 분류를 따르고, 코넥스·외국기업 등 WICS 미편입 종목은 비워 둡니다.

투자자별 순매수·공매도(`investor_flow_daily`) 적재(pykrx, KRX 로그인 필요):

```bash
python -m crawling.investor_flow_loader --backfill   # T1/T2, 최근 3년
python -m crawling.investor_flow_loader --recent     # T1/T2, 최근 14일 다시 받기 (매일)
```

- 기관합계·외국인합계·개인·기타법인의 순매수 금액(원)과 수량(주), 공매도 거래량·거래대금·비중, 공매도 잔고 수량·금액·비중
- 공매도 거래량과 비중은 당일 값이 나오지만, 공매도 거래대금과 잔고는 KRX가 약 2거래일 늦게 공개해 최근 며칠은 비어 있다가 다음 `--recent` 때 채워진다
- 공매도 조회는 1년이 넘는 기간을 한 번에 요청하면 실패해서 180일씩 나눠 받는다
- 2023-11-06 ~ 2025-03-30은 공매도 전면 금지 기간이라 공매도 수치가 매우 작다(시장조성 등 예외 거래만 있음)

대주주·임원 지분 변동(`insider_holdings`) 적재(DART 지분공시 종합정보, `DART_API_KEY` 필요):

```bash
python -m crawling.insider_holdings_loader                     # T1/T2 보통주 전체 (매일)
python -m crawling.insider_holdings_loader --tickers 005930
```

- `report_kind`: `major`(대량보유 상황보고, 5% 이상) / `insider`(임원·주요주주 소유보고)
- DART는 날짜를 고르는 조회가 없고 최근 약 2년 치를 한 번에 주므로, 매번 전체를 받아 덮어쓴다
- 접수일(`rcept_dt`) 기준으로 시점 조회한다. 임원 보고에는 주식 보상 같은 소액 변동도 들어 있다

증권사 리포트 청크(`report_metadata`, `document_chunks`) 적재. 청커는 `processing/processors/report_chunker.py`:

```bash
python -m crawling.report_chunks_loader --backfill               # T1, 최근 3개월
python -m crawling.report_chunks_loader --recent                 # T1, 최근 14일 (매일)
python -m crawling.report_chunks_loader --backfill --rechunk     # 이미 자른 리포트도 다시 자름
```

- 네이버 리서치 목록을 `report_metadata`에 넣고, 아직 안 잘랐거나 실패했거나 청커 버전(`CHUNKER_VERSION`)이 바뀐 리포트만 PDF를 받아 자른다
- PDF는 임시 폴더에 받아 자른 뒤 바로 지운다
- `chunk_status`: `chunked` / `failed`(다음 실행 때 다시 시도) / `no_pdf`(PDF 주소 없음) / `no_text`(글자를 그림으로 그린 PDF라 OCR 없이는 못 읽음. 미래에셋증권 등)
- 임베딩(`embedding`)은 적재 때 비워 두고 `python -m crawling.chunk_embedder`로 채운다(아래). 임베딩 입력(머리말 + 본문)은 저장하지 않고 그때 만든다
- BM25 색인(`search_tokens`, `search_token_count`)은 적재할 때 Kiwi로 바로 만든다
- `mentioned_tickers`는 지금은 리포트 대상 종목 하나만 넣는다. 다른 종목 언급은 온톨로지 연결 단계에서 채운다
- 다시 자를 때 본문이 같은 청크는 그대로 두어 임베딩을 지키고, 사라진 청크는 지우지 않고 `is_active=false`로 남긴다(토론 근거·온톨로지 ISSUE의 청크 ID 링크 유지). 검색은 활성 청크만, 청크 ID로 여는 근거 조회는 비활성도 포함
- PDF 자르기는 별도 프로세스에서 돈다. PyMuPDF가 죽거나 5분을 넘기면 그 리포트만 `failed`로 남기고 이어 간다
- 청커가 PyMuPDF 레이아웃 모델로 표를 찾아서 리포트 1건에 약 10초 걸린다(모델을 끄면 7배 빠르지만 본문이 표로 잘못 잡힘)

뉴스 청크 적재 (`news_metadata`, `document_chunks` document_type='news'):

```bash
python -m crawling.news_chunks_loader                  # 최근 3일, 매일 실행
python -m crawling.news_chunks_loader --days 90 --embed # 첫 적재 + 임베딩
python -m crawling.news_chunks_loader --tickers 005930 --limit 30
```

- 네이버 **API HUB** 뉴스 검색만 쓴다(`naverapihub.apigw.ntruss.com/search/v1/news`, 헤더 `X-NCP-APIGW-API-KEY-ID/KEY`). 키는 NCP 콘솔 > NAVER API HUB > Application > 인증 정보의 Client ID/Secret(`NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`). NCP 계정 Access Key(`ncp_iam_…`)는 안 된다
- API가 검색어당 최신 1,100건까지만 줘서 과거 뉴스는 나중에 받을 수 없다. 대형주는 하루치도 다 안 받힌다 → 매일(가능하면 하루 여러 번) 돌려 쌓는다
- 제목에 종목명이 있고(다른 회사 이름의 일부가 아닌 형태, 조사는 허용) 허용 언론사(`PRESS_ALLOWLIST`: 주요 일간지·경제지·통신사·방송 + 업종 전문지)인 기사만 남긴다. 기사에서 쓰는 이름이 다른 종목은 `NEWS_NAMES`(네이버, 에쓰오일, 기아차 등)
- 같은 기사가 여러 종목에 걸리면 한 행으로 두고 `mentioned_tickers`에 모은다
- 본문은 원문 페이지에서 받고(시험 48건 중 85% 성공, 평균 약 1,700자), 못 받으면 검색 API 요약문을 쓴다(`extraction_method='summary'`)
- 90일(`--expire-days`)보다 오래된 뉴스 청크는 `is_active=false`(행과 임베딩은 남김)

공시 청크 적재 (`disclosure_metadata`, `document_chunks` document_type='disclosure'):

```bash
python -m crawling.disclosure_chunks_loader                  # 최근 7일, 매일 실행
python -m crawling.disclosure_chunks_loader --days 90 --embed # 첫 적재 + 임베딩
python -m crawling.disclosure_chunks_loader --tickers 000660 --limit 20
```

- OpenDART `list.json`으로 목록, `document.xml`로 원문을 받는다(`DART_API_KEY`, 하루 2만 회)
- 토론 근거로 쓸 종류만 넣는다(`CATEGORY_RULES`): 실적 잠정(`earnings`), 공급계약(`contract`), 배당·자사주·소각·밸류업(`shareholder_return`), 증자·사채(`capital`), 출자·시설투자·합병(`investment`), 해명·조회공시·소송·중대재해·채무보증(`risk`), 그 밖의 주요사항보고서·주요경영사항(`other`). 시험(T1, 90일)에서 3,427건 중 737건
- 빼는 것(`EXCLUDE_KEYWORDS`): 정기보고서(숫자는 `financials`), 지분공시(`insider_holdings`), 증권 발행 서류(증권사 파생상품 발행분이 대부분), IR 개최 안내, 계열사 거래 공시
- 원문 표는 행마다 "항목 - 세부항목: 값" 한 줄로 바꾼다(병합 칸은 아래 행에 다시 채움). 숫자는 원문 그대로. 섹션 제목은 본문 줄로 넣고 공시 하나를 1,200자 단위로 묶는다. 공시 하나당 40조각까지
- `doc_id`는 `DART_{접수번호}`, `broker`(→ `Evidence.author_org`)는 제출인, 정정 공시는 `is_correction=true`로 따로 쌓는다(원래 공시도 남김)
- 과거 공시는 언제든 다시 받을 수 있어서 뉴스처럼 비활성으로 돌리지 않는다

청크 임베딩과 BM25 색인:

```bash
python -m crawling.chunk_embedder --dry-run   # 대상 수·글자 수만 (API 호출 없음)
python -m crawling.chunk_embedder --limit 100 # 시험
python -m crawling.chunk_embedder             # 빈 임베딩 전부 (Upstage solar-embedding-2-passage, 1,024차원)
python -m crawling.chunk_indexer              # 비어 있는 BM25 색인 채우기 (API 없음)
python -m crawling.chunk_indexer --all        # 형태소 규칙을 바꾼 뒤 전부 다시
python -m crawling.chunk_reclassify --dry-run # 청커의 고지 판별 규칙을 기존 청크에 다시 적용 (PDF 다시 안 받음)
```

- 임베딩 대상은 활성 청크 중 면책 문구가 아닌 것. 100개씩 보내고 묶음마다 저장해서 끊겨도 다시 실행하면 빈 칸만 채운다
- 분당 25만 토큰 이하로 보낸다(한도 30만). 입력은 6,000자까지 잘라 모델 한도 8,192토큰을 넘지 않게 한다
- 2026-11-09 기준 리포트 청크 15,285개, 약 1,000만 토큰

KIS 목표주가·투자의견(`broker_opinions`) 적재(`KIS_APP_KEY`, `KIS_APP_SECRET` 필요). 조회 API만 호출합니다:

```bash
python -m crawling.opinions_loader --backfill   # T1/T2, 최근 12개월
python -m crawling.opinions_loader --recent     # T1/T2, 최근 14일 다시 받기 (매일)
```

- `opinion`은 증권사 원래 표기, `opinion_norm`은 buy/hold/sell로 통일한 값. NotRated 등은 null
- `target_price`는 발표 당시 기준. 분할을 환산한 값은 뷰 `broker_opinions_adjusted`의 `target_price_adjusted`
- 분할 판별(`stock_split_events`): 주식수 1.5배 이상 또는 0.5배 이하이면서 시가총액 변화가 0.8~1.25배. 무상증자처럼 권리락일과 신주 상장일이 다른 경우는 잡히지 않을 수 있음

시뮬레이션 파라미터(`sim_params`, GJR-GARCH + FHS)와 민감도(`sensitivities`) 적합. 시세·지수·매크로 적재 후 실행:

```bash
python -m crawling.sim_loader                     # T1/T2 종목, 최신 거래일 기준 최근 3년
python -m crawling.sim_loader --tickers 005930    # 특정 종목만
```

- `sim_params.params_json`: 계수(omega·alpha·gamma·beta), 다음날 조건부 분산, 표준화 잔차(`std_resid`), 30일 예상 변동성. 경로 생성은 `crawling.analytics.garch.simulate_paths` 참고
- `status=not_converged`이면 `params_json.status_reason`이 `optimizer_failed`(최적화 실패) 또는 `nonstationary`(지속성 ≥ 1)
- `sensitivities`: 요인(KOSPI·USD_KRW·KTB_3Y_KR)이 30거래일 동안 1σ 움직일 때 종목 30일 수익률(%) 변화. `multi`는 세 요인 동시 회귀, `simple`은 단일 요인 회귀, `corr_daily`는 일별 상관계수(온톨로지 엣지 가중치)
- 국고채 10년(`KTB_10Y_KR`)은 `simple`과 `corr_daily`만 낸다. 3년물과 일별 변화 상관이 0.9라 `multi`에 같이 넣으면 계수가 불안정해진다(2026-11-10 추가)
- 섹터별 묶음은 뷰 `sector_sensitivities`(WICS l1/l2, corr_daily 중앙값·사분위·종목 수, 최신은 `is_latest`)

월별 지표 상관 (`price_monthly`, `monthly_correlations`, 뷰 `sector_monthly_correlations`):

```bash
python -m crawling.monthly_corr_loader --backfill   # 처음 한 번: T1 10년 치 월말 종가 + 상관 계산
python -m crawling.monthly_corr_loader              # 매달: 최근 3개월 종가 갱신 + 상관 다시 계산
python -m crawling.monthly_corr_loader --skip-fetch # 상관만 다시 계산
```

- 월별로만 나오는 지표(CPI_KR, BRENT, DRAM_EXPORT_PRICE)는 corr_daily를 낼 수 없어서, 종목 월 로그수익률과 요인 월 로그변화의 상관(최근 최대 120개월, 최소 24개월)을 따로 낸다
- 일별 시세는 3년 치만 두므로 월말 수정종가(pykrx 월봉)만 10년 치 저장한다(T1 100종목 약 1.1만 행, 1MB). 끝나지 않은 이번 달은 넣지 않는다
- 개월 수(`n_months`)와 95% 신뢰구간(`ci_low`, `ci_high`)을 함께 남긴다. 36개월이면 ±0.3, 120개월이면 ±0.18 정도 흔들린다
- 요인마다 as_of가 다르다(발표가 늦은 지표는 1~2달 늦음). 섹터 뷰는 요인별 최신을 `is_latest`로 표시
- **1달 시차**(`lead_months=1`): t월 주가 수익률과 t+1월 지표 변화를 짝짓는다. 지표는 월평균인데 종가는 월말이라 같은 달끼리는 시점이 어긋나고, 주가가 지표를 앞서 반영한다. 같은 달로 맞추면 S-Oil–브렌트 0.20, 삼성전자–D램 0.14였는데 1달 시차로 0.41, 0.27
- `as_of`는 계산에 쓴 마지막 지표 달, `window_start`는 첫 주가 달
- 섹터 중앙값은 업종과 상관없는 종목이 섞여 희석된다(예: D램은 반도체 중분류 0.15인데 삼성전자 0.27·SK하이닉스 0.26). 지표가 경기 전반과도 같이 움직여 은행 등에서도 0.1~0.2가 나온다. 핵심 종목은 종목 값을 보는 게 낫다
- 전년 대비(12개월) 상관은 0.5~0.8로 높게 나오지만, 12개월 변화가 서로 겹쳐 실제보다 부풀려지고 신뢰구간을 낼 수 없어 넣지 않았다

## 뉴스 / 공시 Provider

- `NEWS_DATA_PROVIDER=naver`: Naver Search API로 뉴스 메타데이터를 수집하고 `original_url` 본문을 best-effort로 파싱해 `news_metadata.content`에 저장
- `DISCLOSURE_DATA_PROVIDER=dart`: OpenDART API로 공시 목록과 원문 문서를 수집해 `disclosure_metadata.content`에 저장

뉴스 수집에는 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`이 필요합니다.
공시 수집에는 `DART_API_KEY`가 필요합니다.
키가 비어 있으면 해당 수집은 skip되고 파이프라인은 계속 진행됩니다.

```bash
python main.py --run-once --source naver --include-news-data --include-disclosure-data
```

## 로그

콘솔과 `logs/crawler.log`에 다음을 기록합니다.

- 수집 시작/종료와 source
- 기업별 발견 리포트 수
- 총 발견 리포트 수
- 다운로드 성공, 중복, 실패 수
- target/price/macro/news/disclosure 저장 수
- 실패 사유와 PDF 저장 경로

## 테스트

```bash
python -m unittest discover -v
```

테스트 범위는 company resolver, report type 정규화, report_id 생성, SHA-256/PDF 검증, 중복 검사, target price 저장 조건, price/macro/news/disclosure provider를 포함합니다.
