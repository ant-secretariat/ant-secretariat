# financial_research_data_agent — 담당자 C 담당 코드

## 담당 범위 (Agent B Storage 기준)

```
Agent B Storage
├── Relational DB
│   ├── report_chunk_records     ✅ C 담당 (chunk 원본 및 관리 정보 저장)
│   └── target_price_data        ✅ B 담당 (HTML에서 추출, C는 읽기만)
│
└── Vector DB
    ├── report_chunks            ✅ C 담당
    ├── news_chunks              ✅ C 담당
    ├── disclosure_chunks        ✅ C 담당
    └── macro_summary_chunks     ✅ C 담당
```

---

## 파일 구조

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
│   └── search_documents.py         # 공통 함수 search_documents() 구현
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

## 실행 방법

```powershell
# API 키 없을 때 (Placeholder 임베딩)
python run_pipeline.py --db-path ..\financial-research-agent-main\db\reports.db --pdf-base-path ..\financial-research-agent-main

# API 키 있을 때 (Upstage 임베딩 + ChromaDB)
python run_pipeline.py --db-path ..\financial-research-agent-main\db\reports.db --pdf-base-path ..\financial-research-agent-main --upstage-api-key YOUR_API_KEY

# dry-run (DB 저장 없이 청킹 결과만 확인)
python run_pipeline.py --db-path ... --pdf-base-path ... --dry-run
```

---

## 주의사항 (회의 확정)

- target_price_data는 B가 HTML에서 추출 - C는 PDF 파싱 추출 X, 읽기만
- 스캔본 PDF는 OCR 필요 → `pdf_processor.is_scanned_pdf()` 로 감지
- chunk에 출처 metadata 반드시 포함 (page / source / date)
- 검색 결과에 page / source / date 함께 반환
- 중복 chunk 저장 방지 → `relational_db.chunk_exists()` 로 확인
