## 1. 담당 범위

수집한 데이터를 전처리하고 Vector DB에 저장하며, 다른 Agent들이 공통으로 사용할 검색/조회 함수를 구현합니다.

```
Agent B Storage
├── Relational DB
│   ├── report_chunk_records 
│   └── target_price_data   
│
└── Vector DB
    ├── report_chunks       (478건 / 문단 단위 청킹)
    ├── news_chunks         (607건 / 문단 단위, 길면 문장 단위)
    ├── disclosure_chunks   (144건 / 문단 단위, 길면 문장 단위)
    └── macro_summary_chunks (5건  / 1건 = 1청크)
```

---

## 2. 사용 기술

- **Vector DB**: Pinecone (클라우드 기반, API 키 필요)
- **임베딩 모델**: Upstage `solar-embedding-1-large-passage` (4096차원)

---

## 3. 파일 구조

```
financial_research_data_agent/
├── schemas.py                      # 데이터 클래스 정의
├── interfaces.py                   # 임베딩 / Vector DB / Relational DB 추상 인터페이스
├── pipeline.py                     # 메인 파이프라인 (처리 흐름 전체)
├── run_pipeline.py                 # 실행 진입점
├── requirements.txt
│
├── processors/
│   ├── pdf_processor.py            # PDF 추출 / 청킹
│   └── text_processor.py           # 뉴스 / 공시 / 매크로 청킹
│
├── functions/
│   ├── search_documents.py         # Vector DB 의미 기반 검색
│   ├── get_report_chunks.py        # 특정 리포트 chunk 전체 조회
│   ├── resolve_company.py          # 회사명 → ticker 변환
│   ├── get_report_metadata.py      # 리포트 메타데이터 조회
│   ├── get_target_price_data.py    # 목표주가 / 투자의견 조회
│   ├── get_price_data.py           # 주가 데이터 조회
│   ├── get_macro_data.py           # 매크로 지표 조회
│   ├── get_disclosure_data.py      # 공시 데이터 조회
│   ├── get_available_data_status.py # 기업별 데이터 준비 여부 확인
│   └── get_agent_context.py        # Agent별 필요 데이터 묶음 반환
│
├── storage/
│   ├── implementations.py          # Pinecone / Upstage 임베딩 / SQLiteDB 구현체
│   ├── sqlite_db.py                # SQLiteDB 구현체 (reports.db 공유)
│   └── schema_extension.sql        # 테이블 DDL (report_chunk_records)
│
└── config/
    └── document_type_codes.py      # document_type_codes
```

---

## 4. 청킹 방식

### 리포트 (PDF)
- **방식**: 문단 단위 청킹 (`\n\n` 기준 분할)
- **최대 길이**: 1500자
- **최소 길이**: 50자 (미만 시 제외)
- **fallback**: 문단이 너무 길면 문장 단위로 재분할
- **예외처리**: 문장이 1500자를 초과하는 경우 글자 수 기준으로 강제 분할 (표 등 비정형 텍스트 대응)
- **결과**: 14개 리포트 → 478개 청크 (4개 기업: 삼성전자, SK하이닉스, 현대차, NAVER)

### 뉴스
- **방식**: 문단 단위 청킹 (`\n\n` 기준), 문단이 1500자 초과 시 문장 단위로 재분할
- **본문 처리**: title + summary + content 순으로 합쳐서 임베딩 (summary/content 없으면 생략)
- **최대 길이**: 1500자
- **최소 길이**: 50자
- **예외처리**: 문장이 1500자를 초과하는 경우 글자 수 기준으로 강제 분할 (표 등 비정형 텍스트 대응)
- **결과**: 607개 청크

### 공시
- **방식**: 문단 단위 청킹 (`\n\n` 기준), 문단이 1500자 초과 시 문장 단위로 재분할
- **본문 처리**: 본문 있으면 report_name + content 사용, 없으면 report_name만 사용
- **최대 길이**: 1500자
- **최소 길이**: 50자 (본문 없는 경우 5자)
- **예외처리**: 문장이 1500자를 초과하는 경우 글자 수 기준으로 강제 분할 (표 등 비정형 텍스트 대응)
- **결과**: 144개 청크

### 매크로
- **방식**: 1건 = 1청크 (지표명 + 날짜 + 수치를 자연어로 변환)
- **수집 지표**: BASE_RATE_KR, CPI_KR, KTB_10Y_KR, KTB_3Y_KR, USD_KRW
- **결과**: 5개 청크

---

## 5. 사전 준비

`crawling/` 파이프라인(`python crawling/main.py`)이 먼저 실행되어 있어야 합니다.

- DB 파일: `crawling/db/reports.db` (crawling과 공유)
- PDF 저장 경로: `crawling/storage/raw_report_pdfs/`

---

## 6. 환경 설정

가상환경 설치 (레포 루트에서):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

`.env`에 아래 값을 채웁니다:

```
UPSTAGE_API_KEY=your_upstage_key
PINECONE_API_KEY=your_pinecone_key
PINECONE_INDEX=financial-research-data-agent
```

---

## 7. 실행 방법

**API 키 없을 때 (Placeholder 임베딩)**

레포 루트에서 실행합니다 (기본 `--db-path`는 `crawling/db/reports.db`).

```powershell
python processing/run_pipeline.py `
  --pdf-base-path crawling
```

**리포트만 처리 (API 키 있을 때)**

```powershell
python processing/run_pipeline.py `
  --pdf-base-path crawling `
  --pinecone-index financial-research-data-agent
```

**뉴스/공시/매크로 포함 전체 처리**

```powershell
python processing/run_pipeline.py `
  --pdf-base-path crawling `
  --pinecone-index financial-research-data-agent `
  --include-news-data `
  --include-disclosure-data `
  --include-macro-data
```

**dry-run (DB 저장 없이 청킹 결과만 확인)**

```powershell
python processing/run_pipeline.py --pdf-base-path crawling --dry-run
```

**특정 리포트만 처리**

```powershell
python processing/run_pipeline.py --pdf-base-path crawling --report-id REPORT_ID
```

---

## 8. 공통 함수 사용법

다른 Agent 개발자는 아래 함수들을 import해서 사용합니다.

---

### resolve_company()

회사명/선택값을 ticker로 변환

```python
from processing.functions.resolve_company import resolve_company

result = resolve_company(company_input="삼성전자")
```

```json
{
  "ticker": "005930",
  "company": "삼성전자",
  "sector": "반도체",
  "matched": true,
  "match_status": "alias",
  "match_confidence": 1.0
}
```

---

### search_documents()

Vector DB에서 의미 기반 문서 chunk 검색

```python
from processing.functions.search_documents import search_documents

result = search_documents(
    query="HBM 수요 증가",
    ticker="005930",
    date_from="2026-01-01",
    date_to="2026-06-21",
    document_type="report",
    report_type="company_report",
    source="KIRS",
    top_k=5,
    embedding_model=embedding_model,
    vector_db=vector_db,
)
```

```json
{
  "query": "HBM 수요 증가",
  "ticker": "005930",
  "results": [
    {
      "chunk_id": "KIRS_005930_001_chunk_001",
      "ticker": "005930",
      "company": "삼성전자",
      "date": "2026-06-15",
      "source": "KIRS",
      "document_type": "report",
      "report_type": "company_report",
      "title": "리포트 제목",
      "content": "검색된 본문",
      "score": 0.84,
      "url": "원문 URL"
    }
  ]
}
```

---

### get_report_chunks()

특정 리포트의 chunk 전체를 순서대로 조회

```python
from processing.functions.get_report_chunks import get_report_chunks

result = get_report_chunks(
    report_id="KIRS_005930_001",
    page=3,
    relational_db=db,
)
```

```json
{
  "report_id": "KIRS_005930_001",
  "ticker": "005930",
  "company": "삼성전자",
  "title": "리포트 제목",
  "chunks": [
    {
      "chunk_id": "KIRS_005930_001_chunk_001",
      "chunk_index": 1,
      "page_start": 1,
      "page_end": 1,
      "content": "첫 번째 chunk 본문"
    },
    {
      "chunk_id": "KIRS_005930_001_chunk_002",
      "chunk_index": 2,
      "page_start": 2,
      "page_end": 2,
      "content": "두 번째 chunk 본문"
    }
  ]
}
```

---

### get_report_metadata()

리포트 목록과 메타데이터 조회

```python
from processing.functions.get_report_metadata import get_report_metadata

result = get_report_metadata(
    ticker="005930",
    date_from="2026-01-01",
    date_to="2026-06-21",
    report_type="company_report",
    relational_db=db,
)
```

```json
{
  "ticker": "005930",
  "count": 3,
  "reports": [
    {
      "report_id": "KIRS_005930_001",
      "ticker": "005930",
      "company": "삼성전자",
      "title": "리포트 제목",
      "source": "KIRS",
      "author_org": "작성 기관",
      "published_at": "2026-06-15",
      "report_type": "company_report",
      "original_url": "원문 URL"
    }
  ]
}
```

---

### get_target_price_data()

목표주가 및 투자의견 조회. Supabase `broker_opinions_adjusted`(KIS 종목투자의견)를 읽으며 `SUPABASE_DB_URL`이 필요합니다. 반환 형식은 API 계약서(`docs/api/openapi.yaml`)의 `TargetPriceData`를 따릅니다.

- `records`: 계약서 필드 `hts_goal_prc`(목표가), `invt_opnn`(투자의견), `rgbf_invt_opnn`(직전 투자의견), `mbcr_name`(증권사)은 KIS 원래 값 그대로
- `records` 추가 필드: `published_at`(발표일), `target_price_adjusted`(액면분할 환산 목표가), `opinion_norm`(매수 / 중립 / 매도 또는 `null`), `valid_from`(발표일), `superseded_at`(같은 증권사의 다음 발표일, 아직 없으면 `null`)
- `consensus`: 증권사마다 가장 최근 의견 1건의 환산 목표가로 계산한 평균·최고·최저. 최근 의견에 목표가가 없는 증권사는 빼고, `broker_count`에 계산에 쓴 증권사 수를 담음
- `as_of`: 주면 그날까지 발표된 의견만 쓰고, 그 뒤에 나온 의견은 `superseded_at`에도 드러내지 않음. 기본값은 오늘
- `target_prices`, `summary`: 트렌드 리포트가 계약서 형식으로 옮겨 갈 때까지 함께 주는 이전 형식(`summary`는 기간 안 모든 의견의 환산 목표가 기준)
- `relational_db` 인자: 기존 호출과의 호환을 위해 받기만 하고 쓰지 않음. `report_type` 인자는 계약서대로 삭제
- 조회 실패 시 예외 대신 빈 결과와 `"error": "target_price_unavailable"`을 반환
- 현재 T1/T2만 적재되어 있어 그 외 종목은 빈 결과

```python
from processing.functions.get_target_price_data import get_target_price_data

result = get_target_price_data(
    ticker="005930",
    date_from="2026-01-01",
    date_to="2026-06-21",
    as_of="2026-06-21",
)
```

```json
{
  "ticker": "005930",
  "company": "삼성전자",
  "records": [
    {
      "hts_goal_prc": 95000,
      "invt_opnn": "BUY",
      "rgbf_invt_opnn": "BUY",
      "mbcr_name": "삼성",
      "published_at": "2026-06-15",
      "target_price_adjusted": 95000,
      "opinion_norm": "매수",
      "valid_from": "2026-06-15",
      "superseded_at": null
    }
  ],
  "consensus": {
    "avg_target_price": 95000,
    "max_target_price": 95000,
    "min_target_price": 95000,
    "broker_count": 1,
    "basis": "증권사별 최신 1건"
  },
  "target_prices": [
    {
      "report_id": "",
      "ticker": "005930",
      "company": "삼성전자",
      "published_at": "2026-06-15",
      "source": "KIS",
      "author_org": "삼성",
      "title": "",
      "target_price": 95000,
      "investment_opinion": "매수",
      "opinion_raw": "BUY",
      "report_type": "",
      "original_url": "",
      "pdf_url": ""
    }
  ],
  "summary": {
    "count": 1,
    "avg_target_price": 95000,
    "min_target_price": 95000,
    "max_target_price": 95000
  }
}
```

---

### get_price_data()

주가, 거래량, 변동성 등 숫자 데이터 조회

```python
from processing.functions.get_price_data import get_price_data

result = get_price_data(
    ticker="005930",
    date_from="2026-01-01",
    date_to="2026-06-21",
    relational_db=db,
)
```

```json
{
  "ticker": "005930",
  "company": "삼성전자",
  "filters": {
    "date_from": "2026-01-01",
    "date_to": "2026-06-21"
  },
  "latest": {
    "price_date": "2026-06-21",
    "current_price": 80000,
    "market_cap": null,
    "volatility_30d": 0.21
  },
  "prices": [
    {
      "price_date": "2026-06-21",
      "open": 79000,
      "high": 81000,
      "low": 78500,
      "close": 80000,
      "volume": 12345678
    }
  ]
}
```

---

### get_macro_data()

금리, 환율, CPI 등 매크로 숫자 데이터 조회

```python
from processing.functions.get_macro_data import get_macro_data

result = get_macro_data(
    indicators=["BASE_RATE_KR", "USD_KRW"],
    date_from="2026-01-01",
    date_to="2026-06-21",
    relational_db=db,
)
```

```json
{
  "country": "KR",
  "indicators": [
    {
      "indicator_id": "BASE_RATE_KR",
      "indicator_name": "한국 기준금리",
      "unit": "%",
      "frequency": "monthly",
      "records": [
        {
          "date": "2026-06-19",
          "value": 2.75,
          "source": "ECOS"
        }
      ]
    }
  ]
}
```

---

### get_disclosure_data()

공시 데이터 조회

```python
from processing.functions.get_disclosure_data import get_disclosure_data

result = get_disclosure_data(
    ticker="005930",
    date_from="2026-01-01",
    date_to="2026-06-21",
    disclosure_type="사업보고서",
    relational_db=db,
)
```

```json
{
  "ticker": "005930",
  "company": "삼성전자",
  "disclosures": [
    {
      "disclosure_id": "DART_005930_20260615_001",
      "date": "2026-06-15",
      "source": "OpenDART",
      "title": "신규 시설투자 공시",
      "disclosure_type": "investment",
      "summary": "고대역폭 메모리 생산설비 증설을 위한 투자 결정",
      "url": "공시 원문 URL"
    }
  ]
}
```

---

### get_available_data_status()

해당 기업에 어떤 데이터가 있는지 확인 (실행 Agent 선택 전 데이터 준비 여부 확인). 반환 형식은 API 계약서 `DataStatus`이고, 이전 형식(`available`, `latest`)도 함께 줍니다.

- 정형 데이터(시세·매크로·재무·목표주가·시뮬레이션 파라미터)는 Supabase에서, 리포트·뉴스·공시 건수는 문서 테이블을 옮기기 전까지 `relational_db`(SQLite)에서 셉니다. `relational_db`가 없으면 문서 건수는 0
- `simulation_ready`: 가장 최근 `sim_params`가 `ok`인지. FE가 시뮬레이션 버튼을 미리 끄는 데 씀
- `derived_snapshot_available`: `get_derived_snapshot` 구현 전이라 `false`
- `collection_job_status`: T2 수집이 Post-MVP라 `null`
- `as_of_dates`: 데이터 종류별 최신 기준일 (오래된 데이터 표시용)
- Supabase 조회가 실패해도 예외 대신 정형 데이터 항목을 비운 결과를 반환

```python
from processing.functions.get_available_data_status import get_available_data_status

result = get_available_data_status(
    ticker="005930",
    relational_db=db,
    vector_db=vector_db,
)
```

```json
{
  "ticker": "005930",
  "company": "삼성전자",
  "report_count": 12,
  "news_count": 30,
  "disclosure_count": 8,
  "derived_snapshot_available": false,
  "collection_job_status": null,
  "simulation_ready": true,
  "as_of_dates": {
    "price": "2026-11-06",
    "macro": "2026-11-06",
    "financials": "2026-08-14",
    "target_price": "2026-11-04",
    "report": "2026-11-05",
    "news": "2026-11-06",
    "disclosure": "2026-11-03"
  },
  "available": {
    "reports": true,
    "news": true,
    "disclosures": true,
    "price_data": true,
    "macro_data": true,
    "target_price_data": true
  },
  "latest": {
    "report_date": "2026-06-15",
    "news_date": "2026-06-21",
    "disclosure_date": "2026-06-19",
    "price_date": "2026-06-21",
    "macro_date": "2026-06-19"
  }
}
```

---

### get_metric()

시맨틱 레이어의 단일 정의로 지표 하나를 계산합니다. 반환 형식은 API 계약서 `MetricValue`입니다. PER·PBR·ROE처럼 매일 바뀌는 값은 온톨로지 노드에 저장하지 않고 이 함수로 조회합니다.

- `as_of`는 필수(`YYYY-MM-DD`). 그날까지 공개된 데이터만 씀
- 시세·밸류에이션 지표: 그날까지의 가장 최근 거래일 값. `as_of`는 그 거래일
- 재무 지표: `financials_as_of(as_of)`로 그날까지 접수된 공시만 써서 계산. 연결 우선, 없으면 별도. `as_of`는 계산에 쓴 공시의 가장 늦은 접수일, `period`는 대상 분기
- 수급 지표: 그날까지 최근 20거래일 합계(순매수) 또는 평균(공매도 비중). 20일보다 적으면 `basis`에 실제 일수를 적음
- 공매도 잔고 비중: KRX가 약 2거래일 늦게 공개하므로 그날 기준 2거래일 전까지의 값만 씀
- 값을 낼 수 없으면 `value`는 `null`이고 `reason`에 사유: `unknown_metric`, `no_data`, `no_value`, `not_applicable_financials`(금융 섹터 부채비율), `metric_unavailable`(조회 실패)

| metric_id | 단위 | 출처 |
|---|---|---|
| `per`, `pbr` | 배 | `market_daily` |
| `eps`, `bps`, `dps` | 원 | `market_daily` |
| `dividend_yield`, `foreign_ratio` | % | `market_daily` |
| `shares_outstanding` | 주 | `market_daily` |
| `close`, `market_cap` | 원 | `price_data` |
| `debt_ratio`, `operating_margin`, `revenue_growth_yoy`, `roe_ttm` | % | `financials` |
| `foreign_net_buy_20d`, `inst_net_buy_20d`, `individual_net_buy_20d` | 원 | `investor_flow_daily` |
| `short_volume_ratio_20d`, `short_balance_ratio` | % | `investor_flow_daily` |

```python
from processing.functions.get_metric import get_metric

result = get_metric(ticker="005930", metric_id="roe_ttm", as_of="2026-09-01")
```

```json
{
  "ticker": "005930",
  "metric_id": "roe_ttm",
  "value": 30.79,
  "unit": "%",
  "basis": "2026Q2 연결, 최근 4개 분기 순이익 합 / 평균 자본",
  "as_of": "2026-08-14",
  "source": ["financials"],
  "reason": null,
  "period": "2026Q2"
}
```

---

### get_agent_context()

특정 Agent에 필요한 데이터 묶음을 한 번에 반환

```python
from processing.functions.get_agent_context import get_agent_context

result = get_agent_context(
    ticker="005930",
    agent_type="trend_report",  # trend_report(D용) / debate(F용) / simulation(G용)
    query="HBM 수요 전망",
    relational_db=db,
    embedding_model=embedding_model,
    vector_db=vector_db,
)
```

```json
{
  "ticker": "005930",
  "agent_type": "trend_report",
  "target_prices": { "...": "..." },
  "price_data": { "...": "..." },
  "macro_data": { "...": "..." },
  "documents": { "...": "..." }
}
```

---

## 9. 현재 상태 및 제한사항

**리포트 수집 현황**
- 크롤링 기준 현재 4개 기업(삼성전자, SK하이닉스, 현대차, NAVER)만 리포트 존재
- 나머지 3개 기업(삼양식품, HYBE, LG에너지솔루션)은 네이버 증권/KIRS에 리포트 없음 (데이터 소스 한계)

**뉴스/공시**
- Naver Search API 기반 뉴스 수집 완료 (210건, 607개 청크)
- OpenDART API 기반 공시 수집 완료 (79건, 144개 청크)
- 뉴스는 210건 중 186건 본문 포함, 나머지는 요약본(summary)만 임베딩됨
- 공시는 74건 전체 본문 포함되어 임베딩됨

**매크로**
- ECOS + Naver 기준 5개 지표 수집 완료
- `summary_text` 미입력 시 자동으로 자연어 변환하여 임베딩

**미수집 데이터**
- `market_cap` (시가총액): `price_data` 미수집 → KIS API 연동 시 수집 가능
- `target_price_data`: 13건 수집 완료
- `disclosure_type`: 74건 전체 값 있음

---

## 10. 주의사항

- `processing/run_pipeline.py` 실행 전 반드시 `crawling/main.py`가 먼저 실행되어 있어야 합니다.
- Upstage API 키와 Pinecone API 키는 `.env` 파일에 저장하며 git에 포함되지 않습니다.
- Upstage API 키가 없으면 Placeholder 임베딩으로 동작하며, `embedding_status = pending`으로 저장됩니다.
- PDF가 스캔본이면 OCR이 필요할 수 있습니다. `pdf_processor.is_scanned_pdf()`로 감지 가능합니다.
- `target_price_data`는 HTML에서 추출한 목표주가/투자의견을 저장합니다. (13건 수집 완료)

## 11. 테스트

공통 함수 동작 확인:

```powershell
python test_functions.py
```

10개 함수 전체를 삼성전자(005930) 기준으로 테스트하며, 결과 요약이 출력됩니다.

---

## 12. 브랜치 작업 요약

이 브랜치는 트렌드 리포트 Agent가 Agent B 데이터를 안정적으로 사용할 수 있도록 반환 포맷과 함수 계약을 보강하기 위해 만든 작업 브랜치입니다.

브랜치명:

```text
data-agent-trend-report-fixes
```

### 반영한 수정사항

- `main`은 건드리지 않고 별도 브랜치 `data-agent-trend-report-fixes` 생성
- `search_documents()` 반환값 보강
  - 기존보다 근거 추적에 필요한 필드 추가
  - `report_id`
  - `author_org`
  - `page_start`
  - `page_end`
- `chunk_id`에서 `report_id`를 자동 추론하는 로직 추가
- `get_target_price_data()` 수정
  - `report_metadata`와 조인
  - `company`가 `author_org`로 잘못 반환될 수 있던 문제 수정
  - `title`, `original_url`, `pdf_url`도 함께 반환
- `get_agent_context("trend_report")` 보강
  - `report_documents`
  - `news_documents`
  - `macro_documents`
  - 위 세 종류를 분리해서 반환하도록 수정
- Trend Report Agent와 연결되는 계약 테스트 추가
  - `tests/test_trend_report_contracts.py`

### 검증 결과

```bash
python -m compileall .
python -m pytest tests -q
```

검증 결과:

```text
2 passed
```

### 관련 커밋

```text
b1b88d0 Fix Agent B trend report contract fields
```

### 남은 작업

- 실제 `crawling/db/reports.db` 생성 및 공유/연결
- 수집 파이프라인 실행 후 실제 데이터 적재 확인
- Pinecone에 실제 chunk 저장 확인
  - `report_chunks`
  - `news_chunks`
  - `macro_summary_chunks`
  - 필요 시 `disclosure_chunks`
- `search_documents()`가 실제 Pinecone 데이터에서도 기대한 필드를 반환하는지 확인
- 뉴스/RSS 데이터 품질 확인
- 매크로 데이터가 현재 환율 중심인지, ECOS 확장까지 필요한지 결정
- `get_available_data_status()`가 실제 DB/Vector DB 상태를 정확히 반영하는지 확인
- Agent C/D/F/G가 공통 함수 호출 시 같은 반환 포맷을 쓰는지 최종 점검
- 실제 데이터 기준 통합 테스트 작성
