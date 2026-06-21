# financial_research_data_agent

## 1. 담당 범위

수집한 데이터를 전처리하고 Vector DB에 저장하며, 다른 Agent들이 공통으로 사용할 검색/조회 함수를 구현합니다.

```
Agent B Storage
├── Relational DB
│   ├── report_chunk_records 
│   └── target_price_data   
│
└── Vector DB
    ├── report_chunks       (272건 / 문단 단위 청킹)
    ├── news_chunks         (210건 / 1건 = 1청크)
    ├── disclosure_chunks   (84건  / 1건 = 1청크)
    └── macro_summary_chunks (5건  / 1건 = 1청크)
```

---

## 2. 사용 기술

- **Vector DB**: ChromaDB (로컬 파일 기반, API 키 불필요)
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
│   ├── search_documents.py         # 공통 함수 search_documents() 구현
│   └── get_report_chunks.py        # 공통 함수 get_report_chunks() 구현
│
├── storage/
│   ├── implementations.py          # ChromaDB / Upstage 임베딩 / SQLiteDB 구현체
│   ├── sqlite_db.py                # SQLiteDB 구현체 (reports.db 공유)
│   └── schema_extension.sql        # 테이블 DDL (report_chunk_records)
│
└── config/
    └── constants.py                # document_type_codes / report_type_codes
```

---

## 4. 청킹 방식

### 리포트 (PDF)
- **방식**: 문단 단위 청킹 (`\n\n` 기준 분할)
- **최대 길이**: 1500자
- **최소 길이**: 50자 (미만 시 제외)
- **fallback**: 문단이 너무 길면 문장 단위로 재분할
- **결과**: 6개 리포트 → 272개 청크 (4개 기업: 삼성전자, SK하이닉스, 현대차, NAVER)

### 뉴스
- **방식**: 1건 = 1청크 (title + summary 결합)
- **데이터 출처**: Naver Search API (본문 전문 없음, 요약본만 제공)
- **최소 길이**: 50자
- **결과**: 210개 청크

### 공시
- **방식**: 1건 = 1청크 (report_name만 사용)
- **데이터 출처**: OpenDART API (본문 없음, 제목만 저장)
- **최소 길이**: 5자
- **결과**: 84개 청크

### 매크로
- **방식**: 1건 = 1청크 (지표명 + 날짜 + 수치를 자연어로 변환)
- **수집 지표**: BASE_RATE_KR, CPI_KR, KTB_10Y_KR, KTB_3Y_KR, USD_KRW
- **결과**: 5개 청크

---

## 5. 사전 준비

이 코드는 (https://github.com/boogiewooki02/financial-research-agent) 가 먼저 실행되어 있어야 합니다.

- DB 파일: `db/reports.db`
- PDF 저장 경로: `storage/raw_report_pdfs/`

---

## 6. 환경 설정

가상환경 설치:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 7. 실행 방법

**API 키 없을 때 (Placeholder 임베딩)**

python run_pipeline.py \
  --db-path ..\financial-research-agent\db\reports.db \
  --pdf-base-path ..\financial-research-agent
  
**리포트만 처리 (API 키 있을 때)**

```powershell
python run_pipeline.py \
  --db-path ..\financial-research-agent\db\reports.db \
  --pdf-base-path ..\financial-research-agent \
  --upstage-api-key YOUR_API_KEY
```

**뉴스/공시/매크로 포함 전체 처리**

```powershell
python run_pipeline.py \
  --db-path ..\financial-research-agent\db\reports.db \
  --upstage-api-key YOUR_API_KEY \
  --include-news-data \
  --include-disclosure-data \
  --include-macro-data
```

**dry-run (DB 저장 없이 청킹 결과만 확인)**

```powershell
python run_pipeline.py --db-path ... --pdf-base-path ... --dry-run
```

**특정 리포트만 처리**

```powershell
python run_pipeline.py --db-path ... --pdf-base-path ... --report-id REPORT_ID
```

---

## 8. 공통 함수 사용법

다른 Agent 개발자는 아래 두 함수를 import해서 사용합니다.

### search_documents()

Vector DB에서 의미 기반 문서 chunk 검색

```python
from functions.search_documents import search_documents

result = search_documents(
    query="HBM 수요 증가",
    ticker="005930",
    date_from="2026-01-01",
    date_to="2026-06-21",
    document_type="report",     # report / news / disclosure / macro_summary
    report_type="company_report",
    source="KIRS",
    top_k=5,
    embedding_model=embedding_model,
    vector_db=vector_db,
)
```

반환 형태:
```json
{
  "query": "HBM 수요 증가",
  "ticker": "005930",
  "results": [
    {
      "chunk_id": "...",
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

### get_report_chunks()

특정 리포트의 chunk 전체를 순서대로 조회

```python
from functions.get_report_chunks import get_report_chunks

result = get_report_chunks(
    report_id="KIRS_005930_001",
    page=3,             # 특정 페이지만 조회 (None이면 전체)
    relational_db=db,
)
```

반환 형태:
```json
{
  "report_id": "KIRS_005930_001",
  "ticker": "005930",
  "company": "삼성전자",
  "title": "리포트 제목",
  "chunks": [
    {
      "chunk_id": "...",
      "chunk_index": 1,
      "page_start": 1,
      "page_end": 1,
      "content": "첫 번째 chunk 본문"
    }
  ]
}
```

---

## 9. 현재 상태 및 제한사항

**리포트 수집 현황**
- 크롤링 기준 현재 4개 기업(삼성전자, SK하이닉스, 현대차, NAVER)만 리포트 존재
- 나머지 3개 기업(삼양식품, HYBE, LG에너지솔루션)은 네이버 증권/KIRS에 리포트 없음 (데이터 소스 한계)

**뉴스/공시**
- Naver Search API 기반 뉴스 수집 완료 (210건)
- OpenDART API 기반 공시 수집 완료 (84건)
- 뉴스는 본문 전문 없이 요약본(summary)만 임베딩됨
- 공시는 본문 없이 제목(report_name)만 임베딩됨

**매크로**
- ECOS + Naver 기준 5개 지표 수집 완료
- `summary_text` 미입력 시 자동으로 자연어 변환하여 임베딩

---

## 10. 주의사항

- `run_pipeline.py` 실행 전 반드시 B 크롤러(https://github.com/boogiewooki02/financial-research-agent)가 먼저 실행되어 있어야 합니다.
- Upstage API 키가 없으면 Placeholder 임베딩으로 동작하며, `embedding_status = pending`으로 저장됩니다.
- PDF가 스캔본이면 OCR이 필요할 수 있습니다. `pdf_processor.is_scanned_pdf()`로 감지 가능합니다.
- `target_price_data`는 HTML에서 추출한 값을 그대로 사용합니다. PDF에서 별도 추출하지 않습니다.
- `chroma_db` 폴더는 런타임 산출물로 git에 포함되지 않습니다. 각 팀원이 파이프라인 실행 시 로컬에 생성됩니다.
