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
    ├── report_chunks 
    ├── news_chunks 
    ├── disclosure_chunks
    └── macro_summary_chunks 
```

---

## 2. 사용 기술

- **Vector DB**: ChromaDB (로컬 파일 기반, API 키 불필요)
- **임베딩 모델**: Upstage `solar-embedding-1-large-passage`

---

## 3. 파일 구조

```
financial_research_data_agent/
├── schemas.py                      # 데이터 클래스 정의 (B↔C 인터페이스 포함)
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
│   ├── sqlite_db.py                # SQLiteDB 구현체 (B의 reports.db 공유)
│   └── schema_extension.sql        # C 담당 테이블 DDL (report_chunk_records)
│
└── config/
    └── constants.py                # document_type_codes / report_type_codes
```

---

## 4. 사전 준비

이 코드는 (https://github.com/boogiewooki02/financial-research-agent)가 먼저 실행되어 있어야 합니다.

- B의 DB 파일: `db/reports.db`
- B의 PDF 저장 경로: `storage/raw_report_pdfs/`

---

## 5. 환경 설정

가상환경 설치:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 6. 실행 방법

**API 키 없을 때 (Placeholder 임베딩)**

```powershell
python run_pipeline.py --db-path ..\financial-research-agent-main\db\reports.db --pdf-base-path ..\financial-research-agent-main
```

**API 키 있을 때 (Upstage 임베딩 + ChromaDB)**

```powershell
python run_pipeline.py --db-path ..\financial-research-agent-main\db\reports.db --pdf-base-path ..\financial-research-agent-main --upstage-api-key YOUR_API_KEY
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

## 7. 공통 함수 사용법

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

## 8. 현재 상태 및 제한사항

**리포트 수집 현황**
- 크롤링 기준 현재 4개 기업(삼성전자, SK하이닉스, 현대차, NAVER)만 리포트 존재
- 나머지 3개 기업(삼양식품, HYBE, LG에너지솔루션)은 네이버 증권/KIRS에 리포트 없음

**뉴스/공시**
- 아직 뉴스/공시 수집 미구현
- 구현 완료 후 `RawNewsInput`, `RawDisclosureInput` 필드 맞춰서 연동 예정

**매크로 요약문**
- `RawMacroInput`의 `summary_text` 필드는 매크로 숫자 데이터를 자연어로 변환해서 넘겨받아야 함
- 변환 방식 추후 B와 협의 예정

---

## 9. 주의사항

- `run_pipeline.py` 실행 전 반드시 (https://github.com/boogiewooki02/financial-research-agent)가 먼저 실행되어 있어야 합니다.
- Upstage API 키가 없으면 Placeholder 임베딩으로 동작하며, `embedding_status = pending`으로 저장됩니다. API 키 발급 후 재실행하면 pending chunk가 자동 처리됩니다.
- PDF가 스캔본이면 OCR이 필요할 수 있습니다. `pdf_processor.is_scanned_pdf()`로 감지 가능합니다.
- `target_price_data`는 HTML에서 추출한 값을 그대로 사용합니다. PDF에서 별도 추출하지 않습니다.
