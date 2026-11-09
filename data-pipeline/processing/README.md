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

- **저장소·검색**: Supabase Postgres + pgvector (`document_chunks`). 예전 Pinecone은 조회 함수에서 쓰지 않음
- **임베딩 모델**: Upstage `solar-embedding-2-passage`(문서) / `solar-embedding-2-query`(질문), 1,024차원

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

### 리포트 (PDF) — 새 청커 `processors/report_chunker.py`

기존 `pdf_processor.py`는 지금 파이프라인이 쓰고 있어 그대로 두고, Supabase 적재(`document_chunks`)부터 새 청커로 바꿉니다.

- **소제목 기준 분할**: 본문보다 글자가 크거나 굵은 짧은 줄을 소제목으로 보고 그 단위로 섹션을 나눔. 본문 글자 크기는 문장처럼 긴 줄(30자 이상)에서만 셈(표·사이드바의 작은 글자가 더 많기 때문)
- **크기**: 섹션 안에서 문단을 1,200자 이하로 묶고, 긴 문단은 문장 경계에서 자름. 400자보다 짧은 조각은 이웃 조각과 합침
- **줄바꿈 복원**: 한국어 리포트는 글자 단위로 줄을 바꿔서, 문장이 끝나지 않은 줄은 이어 붙임. 원문 줄 끝에 공백이 있으면 진짜 띄어쓰기 자리라 띄우고, 없으면 단어 중간이라 붙임(확대 / 하고 → 확대하고, 순증은 / 이보다 → 순증은 이보다)
- **차트 글**: 30자 이하 숫자 덩어리(차트 축 값, 작은 수익률 표)와 그 바로 옆(15pt 안)의 짧은 글(차트 제목·범례·출처)은 본문에서 빼고 쪽마다 `차트·소형 표 수치` 청크(`text_only`)로 모음. 본문보다 큰 글자(리포트 제목)는 옮기지 않음. 한 쪽의 숫자 조각이 60자도 안 되면 버림(회사명·날짜·전화번호 조각). 단 `매출액 31조 5,970억원`처럼 이름 붙은 값이 있으면 남김
- **표**: PyMuPDF `find_tables`로 찾되, 칸에 긴 문장이 있는 상자(본문을 두른 테두리)는 본문으로 되돌림. 표 청크는 `table_structure`가 `intact`(행·열 유지) 또는 `text_only`(칸이 뭉치거나 반복됨, 숫자는 DB 값 사용). 표로 잡히지 않은 숫자 덩어리(재무제표 등)도 `text_only` 표로 분류. 단 `~다.` 문장이 3개 이상이면 본문으로 둠(표지 요약 문단이 주가·재무 박스와 한 조각으로 묶이는 경우). 머리글만 있는 빈 표는 버림
- **표 제목**: 표 바로 위 짧은 글 중 굵거나 큰 글자, 또는 `표1`·`그림`·`(단위` 형식만 제목으로 씀. 문장, 축 값, `자료:` 출처 줄, 고지 문구는 제외. 짧은 섹션을 합칠 때 이은 제목은 120자까지
- **머리말·꼬리말**: 여러 쪽의 위·아래 여백에 반복되는 글은 버림
- **면책 문구**: Compliance Notice, 투자의견 분류·변동 내역 등은 `section_type='disclaimer'`로 표시(기본 검색에서 제외용). 표·목록 형태 고지(투자의견 비율표, 투자등급 기준, 의견·목표가 이력표, 문장 없는 ESG 등급표)도 `is_boilerplate`로 면책 처리. 이 판별만 바꿀 때는 리포트를 다시 자르지 않고 `crawling.chunk_reclassify`로 기존 청크에 적용
- **청크 ID**: `{doc_id}:{정규화한 본문의 SHA-1 앞 12자}`. 다시 처리해도 같은 내용이면 같은 ID(온톨로지 ISSUE 근거가 참조)
- **머리말**: 임베딩 입력(`content`)은 `[회사(종목코드) | 증권사 | 날짜 | 소제목]` + 본문, 키워드 검색과 청크 ID는 머리말 없는 `body` 기준
- **시험**(2026-11-08, 리포트 8개): 본문 청크 길이 중앙값이 약 250자 → 약 500~1,000자, 400자 미만 조각이 거의 없어짐

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

문서 조각 검색. Supabase `document_chunks`(리포트·뉴스·공시)만 검색한다. `embedding_model`, `vector_db` 인자는 기존 호출 호환용으로 받기만 한다.

```python
from processing.functions.search_documents import search_documents

result = search_documents(
    query="SK하이닉스 HBM4 출하 전망",
    ticker="000660",            # 빈 문자열이면 전 종목. mentioned_tickers에 든 문서도 포함
    date_from=None, date_to=None,
    document_type="report",      # report / news / disclosure / macro (macro_summary도 받음)
    as_of="2026-09-30",          # 그날까지 게시된 문서만 (미래 정보 누출 방지)
    broker=None,                 # 증권사로 거르기
    include_disclaimer=False,    # 면책 문구는 기본 제외
    top_k=5,
    mode="hybrid",               # hybrid(기본) / bm25 / vector
)
# → {"query", "ticker", "mode", "results": [{chunk_id, report_id, ticker, company, date, source,
#    author_org, document_type, title, page_start, page_end, content, score, url,
#    section_title, section_type, chunk_type, table_structure}]}
```

- **필터 먼저**: 활성 청크(`is_active`)만, 종목·기간·`as_of`·면책 제외를 먼저 걸고 그 안에서 점수를 낸다
- **bm25**: 질문과 청크를 같은 Kiwi 규칙(`processing/search/korean_tokens.py`)으로 잘라 BM25(k1=1.2, b=0.75)로 점수. 외부 API 없음. 청크 색인은 `search_tokens`(적재기가 채움, 처음 한 번은 `python -m crawling.chunk_indexer`)
- **vector**: 질문을 `solar-embedding-2-query`로 임베딩해 코사인 유사도 순. 같은 질문은 한 번만 임베딩
- **hybrid**: 두 방식 상위 50개를 RRF(k=60)로 합침. 질문 임베딩이 실패하면 BM25로 대신하고 `mode`에 실제 쓴 방식을 남김
- 기본값은 하이브리드: 골든셋 30문항 비교(2026-11-09)에서 nDCG@10 BM25 0.51 / 의미 0.52 / 하이브리드 0.59, Hit@10 0.90 / 0.90 / 0.97. 의미 검색까지 쓰려면 호출하는 환경에 `UPSTAGE_API_KEY`가 필요하고, 없으면 BM25로 대신한다
- 차트 축 값만 모은 `차트·소형 표 수치` 청크는 기본 제외(`include_chart_numbers=True`로 포함)
- `report_type`은 계약서 인자라 받지만 지금 청크에 리포트 유형이 없어 거르지 않는다
- 조회 실패 시 예외 대신 빈 `results`와 `reason: "search_unavailable"`

**검색 평가(골든셋)**: 질문과 정답 청크 ID를 `search_golden_set` 표에 두고 방식별 점수를 잰다. 청커나 검색을 바꾼 뒤 다시 돌려 비교한다.

```bash
python -m processing.search.golden_set evaluate --snapshot 2026-11-09-v1                 # 30문항
python -m processing.search.golden_set evaluate --snapshot 2026-11-09-v1 --reviewed-only # 사람이 검토한 14문항만
python -m processing.search.golden_set import <golden.json> --snapshot <태그> --reviewed G01-G14
```

- 2026-11-09 개선 결과(하이브리드): 차트 수치 청크 제외 + 표 형태 고지 정리 후 nDCG@10 0.59 → 0.61, Hit@5 0.87 → 0.90, 최신 의견 유형 0.56 → 0.63. 표 청크 점수 낮추기는 효과가 ±0.02로 불분명해 적용하지 않음
- `2026-11-09-v1`: 리포트 기준 30문항(유형 6가지 × 5). G01~G14는 수경 검토, G15~G30은 Claude 라벨(검토 전)
- 정답 후보는 세 방식 상위 10개를 모아 만들어서 세 방식이 모두 놓친 정답은 없다. 절대 점수보다 방식끼리 비교에 쓴다
- 골든셋 JSON과 검토 화면은 리포트 내용이 들어 있어 git에 올리지 않고 `storage/golden/`(무시 폴더)에 둔다

예전 Pinecone 검색 경로는 없앴다(2026-11-10). 트렌드 리포트·토론처럼 `embedding_model`, `vector_db`를 넘기는 기존 호출도 에러 없이 Supabase를 검색하고, 결과의 키 이름은 예전과 같다. Supabase에는 매크로 요약 청크가 없어 `document_type="macro_summary"`(`macro`) 검색은 빈 결과다.

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

리포트 목록과 메타데이터 조회. Supabase `report_metadata`(네이버·KIRS)를 읽습니다(`SUPABASE_DB_URL` 필요).

- `author_org`는 증권사, `published_at`은 발행일. `as_of`를 주면 그날까지 나온 리포트만
- Supabase 표에 리포트 유형 칸이 없어 `report_type`은 빈 값이고 `report_type` 인자로 거르지 않음
- 추가 필드 `chunk_status`, `chunk_count`: 본문이 검색(`search_documents`)에 들어갔는지
- `relational_db` 인자는 기존 호출 호환용으로 받기만 함. 조회 실패 시 빈 결과와 `"error": "report_metadata_unavailable"`

```python
from processing.functions.get_report_metadata import get_report_metadata

result = get_report_metadata(
    ticker="005930",
    date_from="2026-01-01",
    date_to="2026-06-21",
    as_of="2026-06-21",
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
      "report_type": "",
      "original_url": "원문 URL",
      "pdf_url": "PDF URL",
      "chunk_status": "chunked",
      "chunk_count": 12
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

주가, 거래량, 변동성 등 숫자 데이터 조회. Supabase `price_data`(pykrx 수정주가)를 읽습니다(`SUPABASE_DB_URL` 필요).

- `prices`는 최신 날짜부터. `as_of`를 주면 그날까지의 시세만(`date_to`와 `as_of` 중 이른 날)
- `volatility_30d`: 최근 30거래일 일별 로그수익률의 표준편차(연율화하지 않음, 수익률 20개 미만이면 `null`). 인사이트보드 변동성 배지(0.03 기준)와 시뮬레이션 전처리가 같은 정의를 씀
- 추가 필드 `trading_value`(거래대금). `source`는 `KRX`
- 현재 T1만 적재되어 있어 그 외 종목은 빈 결과(`latest: null`)
- `relational_db` 인자는 기존 호출 호환용으로 받기만 함. 조회 실패 시 빈 결과와 `"error": "price_unavailable"`

```python
from processing.functions.get_price_data import get_price_data

result = get_price_data(
    ticker="005930",
    date_from="2026-01-01",
    date_to="2026-06-21",
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
    "market_cap": 477000000000000,
    "volatility_30d": 0.021
  },
  "prices": [
    {
      "ticker": "005930",
      "company": "삼성전자",
      "price_date": "2026-06-21",
      "open": 79000,
      "high": 81000,
      "low": 78500,
      "close": 80000,
      "volume": 12345678,
      "trading_value": 987654321000,
      "market_cap": 477000000000000,
      "volatility_30d": 0.021,
      "source": "KRX"
    }
  ]
}
```

---

### get_macro_data()

금리, 환율, CPI 등 매크로 숫자 데이터 조회. Supabase `macro_data`(ECOS)를 읽습니다(`SUPABASE_DB_URL` 필요).

- 지표: `BASE_RATE_KR`, `KTB_3Y_KR`, `KTB_10Y_KR`, `USD_KRW`(일별), `CPI_KR`, `IPI_KR`, `EXPORTS_KR`, `IMPORTS_KR`, `TRADE_BALANCE_KR`(월별, KR), `BRENT`, `WTI`, `DUBAI`(월별, `country='GLOBAL'`)
- `indicators` 없이 부르면 `country`(기본 `KR`) 지표만, `indicators`를 주면 국가와 상관없이 그 지표를 줌
- 월간 지표의 `date`는 해당 월 1일이고 발표일은 따로 두지 않음. `as_of`를 주면 그날까지의 값만
- `relational_db` 인자는 기존 호출 호환용으로 받기만 함. 조회 실패 시 빈 결과와 `"error": "macro_unavailable"`

- Supabase `macro_data`에는 D램 수출물가지수 `DRAM_EXPORT_PRICE`(한국은행 수출물가지수 D램, 달러기준, 월별)도 있음

```python
from processing.functions.get_macro_data import get_macro_data

result = get_macro_data(
    indicators=["BASE_RATE_KR", "USD_KRW"],
    date_from="2026-01-01",
    date_to="2026-06-21",
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

공시 데이터 조회. Supabase `disclosure_metadata`(DART 수시공시·주요사항보고서)를 읽습니다(`SUPABASE_DB_URL` 필요).

- `disclosure_type`은 공시 분류: `earnings`(실적 잠정), `contract`(공급계약), `shareholder_return`(배당·자사주·소각·밸류업), `capital`(증자·사채), `investment`(출자·시설투자·합병), `risk`(해명·조회공시·소송·중대재해·채무보증), `other`. 같은 이름으로 거를 수 있음
- 정기보고서·지분공시·증권 발행 서류는 적재 대상이 아니라 나오지 않음(`crawling/README.md` 공시 청크 적재 참고)
- `summary`는 원문 첫 조각(최대 1,000자). 본문 검색은 `search_documents(document_type="disclosure")`
- 추가 필드 `rcept_no`(접수번호), `is_correction`(정정 공시), `filer`(제출인), `chunk_ids`(본문 청크 ID)
- `as_of`를 주면 그날까지 접수된 공시만. `relational_db` 인자는 기존 호출 호환용으로 받기만 함. 조회 실패 시 빈 결과와 `"error": "disclosure_unavailable"`

```python
from processing.functions.get_disclosure_data import get_disclosure_data

result = get_disclosure_data(
    ticker="005930",
    date_from="2026-01-01",
    date_to="2026-06-21",
    disclosure_type="investment",
)
```

```json
{
  "ticker": "005930",
  "company": "삼성전자",
  "disclosures": [
    {
      "disclosure_id": "20260615800123",
      "date": "2026-06-15",
      "source": "DART",
      "title": "신규시설투자등",
      "disclosure_type": "investment",
      "summary": "신규시설투자등\n1. 투자구분: 신규시설투자 ...",
      "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260615800123",
      "rcept_no": "20260615800123",
      "is_correction": false,
      "filer": "삼성전자",
      "chunk_ids": ["DART_20260615800123:3f2a9c1b7d0e"]
    }
  ]
}
```

---

### get_available_data_status()

해당 기업에 어떤 데이터가 있는지 확인 (실행 Agent 선택 전 데이터 준비 여부 확인). 반환 형식은 API 계약서 `DataStatus`이고, 이전 형식(`available`, `latest`)도 함께 줍니다.

- 모두 Supabase에서 셉니다. 정형 데이터(시세·매크로·재무·목표주가·시뮬레이션 파라미터)는 최신 기준일, 리포트·뉴스·공시는 `document_chunks`에서 검색에 쓸 수 있는 문서(활성·면책 아닌 청크가 있는 문서) 수와 최신 게시일
- `relational_db`, `vector_db` 인자는 기존 호출 호환용으로 받기만 함
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
- 지분공시 지표: 그날까지 접수된 최근 90일 보고. 지분공시를 받는 종목에서 보고가 없으면 0, 받지 않는 종목은 `no_data`. 임원 보고에는 주식 보상 같은 소액 변동도 들어 있음
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
| `insider_net_shares_90d` | 주 | `insider_holdings` |
| `insider_sell_reports_90d` | 건 | `insider_holdings` |
| `major_holder_ratio_change_90d` | %p | `insider_holdings` |

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
