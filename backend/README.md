# ant-secretariat-backend

금융 분석 에이전트 백엔드입니다. FastAPI로 API를 제공하고, 공통 데이터는
`ant-secretariat-data-pipeline`의 SQLite `reports.db`와 Pinecone 인덱스를 사용합니다.

## 주요 기능

- 데모 사용자 등록, 온보딩 저장, 사용자 컨텍스트 조회
- 인사이트 보드: 주가, 시장 환경, 공시 데이터 조회 및 코멘트 생성
- 트렌드 리포트: 리포트, 뉴스, 시장 환경 기반 카드형 리포트 생성
- 토론 분석: 찬성 측, 반대 측, 판정 생성 후 시뮬레이션 실행
- 비동기 분석 job 상태 및 결과 조회
- 시연 계정 초기화

## 요구 사항

- Python 3.11+
- 형제 디렉터리에 `ant-secretariat-data-pipeline` 필요
- `requirements.txt`의 editable dependency가 아래 경로를 참조합니다.

```text
../ant-secretariat-data-pipeline
```

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 환경변수

`.env`에 필요한 값을 설정합니다.

```dotenv
UPSTAGE_API_KEY=
PINECONE_API_KEY=
PINECONE_INDEX=
DATABASE_PATH=../ant-secretariat-data-pipeline/crawling/db/reports.db
```

선택값:

```dotenv
DEBATE_LLM_MODEL=solar-mini
TREND_REPORT_LLM_MODEL=solar-mini
RISK_CLASSIFIER_MODEL=solar-pro
```

`DATABASE_PATH`를 생략하면 data-pipeline의 기본 `crawling/db/reports.db`를 사용합니다.

## 실행

```bash
uvicorn main:app --reload
```

기본 주소:

```text
http://127.0.0.1:8000
```

헬스 체크:

```bash
curl http://127.0.0.1:8000/health
```

## 주요 API

### Users

```http
POST /users
DELETE /users/{user_id}/reset
GET /users/{user_id}/context
```

### Onboarding

```http
POST /onboarding
```

### Companies

```http
GET /companies
GET /companies/{ticker}/data-status
```

### Insight Board

```http
POST /orchestrate/insight-board
```

요청 예:

```json
{
  "user_id": "demo-balanced-investor",
  "companies": ["삼성전자"],
  "feature": "price"
}
```

`feature` 값:

```text
price | macro | disclosure
```

### Trend Report

```http
POST /agents/trend-report
```

요청 예:

```json
{
  "company": "삼성전자"
}
```

### Debate

```http
POST /orchestrate/debate
GET /debate/jobs/{job_id}
GET /debate/jobs/{job_id}/result
GET /debate/jobs/{job_id}/simulation
GET /users/{user_id}/jobs
```

토론 시작 요청 예:

```json
{
  "user_id": "demo-balanced-investor",
  "company": "삼성전자",
  "query": "최근 업황 기준으로 주가 상승 여력이 있는지 분석해줘"
}
```

`POST /orchestrate/debate`는 즉시 `job_id`를 반환합니다. 프론트는
`GET /debate/jobs/{job_id}`를 폴링해 진행 상태와 중간 결과를 조회합니다.

## Job 상태

```text
queued
running
debate_completed
simulation_running
completed
failed
```

`running` 상태에서는 `partial_result`에 중간 결과가 저장될 수 있습니다.

```text
data_collected
bull_completed
bear_completed
judge_completed
```

## 데이터 갱신

백엔드는 데이터를 직접 수집하지 않습니다. 실제 데이터는 data-pipeline에서 갱신합니다.

```bash
cd ../ant-secretariat-data-pipeline

python crawling/main.py \
  --run-once \
  --source naver \
  --include-price-data \
  --include-macro-data \
  --include-news-data \
  --include-disclosure-data

python processing/run_pipeline.py \
  --pdf-base-path crawling \
  --include-news-data \
  --include-disclosure-data \
  --include-macro-data
```

## 테스트

```bash
pytest
```

일부 에이전트는 외부 API 키와 Pinecone 인덱스가 필요합니다. 단위 테스트는 가능한 범위에서
외부 호출을 mock/stub 처리합니다.
