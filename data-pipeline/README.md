# ant-secretariat-data-pipeline

금융 AI Agent 서비스의 데이터 인프라는 두 단계로 구성됩니다.

```
.
├── crawling/     # 리포트/뉴스/공시/시세 수집 → SQLite(reports.db) 적재
│   └── db/
│       ├── schema.sql      # 전체 스키마 (report_metadata, report_chunk_records 등 canonical 소유)
│       └── reports.db      # 공유 SQLite DB 파일 (crawling, processing이 함께 사용)
├── processing/   # reports.db의 리포트를 청킹 → 임베딩 → 벡터DB(Pinecone) 적재, 조회 함수 제공
├── requirements.txt
└── .env.example
```

- `crawling/`과 `processing/`은 원래 별도 레포(`financial-research-agent`, `financial_research_data_agent`)였으나
하나의 레포로 병합
- 두 폴더는 서로의 Python 코드를 import하지 않고, `crawling/db/reports.db` 파일만 공유
- DB 테이블 구조(`CREATE TABLE`)는 항상 `crawling/db/schema.sql`이 canonical 소유

## 설치

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

`.env`에 필요한 값(API 키 등)을 채웁니다. 자세한 항목은 `.env.example` 주석 참고.

## 실행

항상 레포 루트에서 실행

```bash
# 1) 리포트/뉴스/공시/시세 수집 → crawling/db/reports.db 적재
python crawling/main.py --run-once --source naver

# 2) 수집된 리포트를 청킹·임베딩 → Pinecone 적재
python processing/run_pipeline.py --pdf-base-path crawling
```

각 단계의 세부 옵션과 함수 사용법은 `crawling/README.md`, `processing/README.md` 참고.

## 테스트

```bash
pytest crawling/tests processing/tests
```

## 패키지 구조

1. `crawling`, `processing`은 각각 최상위 Python 패키지입니다 (`crawling/__init__.py`, `processing/__init__.py` 존재).
2. 내부 모듈은 `crawling.db.database`, `processing.functions.search_documents`처럼 각 패키지 이름을 포함한 절대 경로로 import합니다.
3. `crawling/main.py`, `processing/run_pipeline.py` 등 진입점 스크립트는 레포 루트를 `sys.path`에 추가하는 부트스트랩 코드를 포함하고 있기 때문에  `python crawling/main.py`처럼 직접 실행해도, 패키지로 import해도 동일하게 동작합니다.
