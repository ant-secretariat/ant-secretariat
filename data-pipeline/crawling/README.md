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
- `MACRO_DATA_PROVIDER=ecos`: 한국은행 ECOS에서 기준금리, 국고채 3·10년 금리, CPI, USD/KRW 환율, 유가(WTI·Dubai·Brent 월평균), 통관 수출·수입과 무역수지(수출 − 수입), 전산업생산지수(계절조정)를 수집
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
