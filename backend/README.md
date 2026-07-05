# ant-secretariat-backend

## 오케스트레이터 (`orchestrator/`) 및 InsightBoard 에이전트 (`agents/insight_board/`)

[Agent C 라우팅 케이스 설계 문서](https://swift-cost-472.notion.site/Agent-C-383a2756fda480a0a146d8d8535f5d9a)를
기준으로 구현했다. 오케스트레이터(Agent C)는 사용자 요청을 분석하는 게 아니라,
프론트엔드의 명시적 액션(기능 토글 선택 vs "토론 시작하기" 버튼 클릭)을 그대로
반영해 라우팅만 하는 단순한 LangGraph `StateGraph`다.

### 라우팅 케이스

| 구분 | 케이스 1 — InsightBoard | 케이스 2 — Debate(→ Simulation) |
|---|---|---|
| 트리거 | 기능 선택: 주가/매크로/공시 | "토론 시작하기" 버튼 클릭 |
| 호출 대상 | InsightBoard 단독 | Debate 단독 |
| 이후 흐름 | InsightBoard 내부에서 완결 | Debate가 완료 후 자체적으로 Simulation 호출 |
| 오케스트레이터의 인지 범위 | 호출 결과(JSON)를 그대로 반환 | 결과는 신경 쓰지 않음(fire-and-forget) — UI 전달은 각 에이전트 책임 |
| 응답 횟수 | 1회 | 2회(토론 완료 1회, 시뮬레이션 완료 1회) — 오케스트레이터가 아니라 Debate가 직접 전달 |

- `orchestrator/schemas.py` — `CompanyContext`, `OrchestratorRequest` (1~3개 기업,
  insight_board는 `feature` 필수, debate는 기업 1개만 허용하는 검증 포함)
- `orchestrator/router.py` — `decide_route()`: `request_type`을 그대로 라우팅 키로
  사용 (LLM 분류 없음 — 프론트 액션 자체가 이미 명확한 트리거이기 때문)
- `orchestrator/graph.py` — `route → insight_board | debate → END` StateGraph.
  insight_board는 `await`해서 결과를 그대로 반환하고, debate는 `asyncio.create_task`로
  던지기만 하고 기다리지 않는다
- `orchestrator/service.py` — `run_orchestrator_request()` 공개 진입점
- `api/orchestrator.py` — `POST /orchestrate/insight-board`, `POST /orchestrate/debate`.
  프론트가 보낸 기업명을 `processing.functions.resolve_company()`로 ticker/company/
  sector로 정규화하는 것까지 이 레이어가 맡는다(문서상 "Agent A" 역할 겸함)

### InsightBoard 에이전트 (Agent E, 신규 구현)

기업별 주가/매크로/공시 조회 + LLM 1줄 코멘트를 제공한다. `agents/debate/service.py`는
아직 인터페이스만 정의된 `NotImplementedError` 스텁이다(Debate 자체 구현은 별도
작업 범위).

- `agents/insight_board/config.py` — feature 타입, 기업 최대 3개, 코멘트 LLM 모델
- `agents/insight_board/data_client.py` — `processing.functions.get_price_data` /
  `get_macro_data` / `get_disclosure_data` 어댑터. 세 함수 모두 동기 sqlite 호출이라
  기업별 병렬 조회는 `asyncio.to_thread` + `asyncio.gather`로 구현(매크로는 종목
  무관이라 1회만 호출)
- `agents/insight_board/comment_generator.py` — Upstage(OpenAI 호환) LLM 1회 호출로
  1~2줄 코멘트 생성. 코멘트는 부가 정보라 실패해도 빈 문자열로 넘어가고 전체
  요청을 막지 않는다(trend_report/simulation의 `require_env()` fail-fast와는
  의도적으로 다른 정책)
- `agents/insight_board/badges.py` — `compute_badges()`. **문서에 배지 정의가 없어
  임계값은 전부 자리표시용 추정치**로 직접 설계함(실제 기획 요구사항이 정해지면
  조정 필요)
- `agents/insight_board/service.py` — `run_insight_board()`: 1) 병렬 데이터 조회
  → 2) LLM 코멘트 → 3) `{"raw_data", "llm_comment", "badges"}` 구조로 반환

## 유저 식별 (`functions/create_user.py`, `api/users.py`)

정식 회원가입/로그인 없이, 프론트엔드가 앱 최초 실행 시 UUID를 생성해 로컬에
저장하고 그 값을 `user_id`로 계속 사용하는 방식을 쓴다. 백엔드는 그 UUID를
`users` 테이블에 등록만 해준다.

- `functions/create_user.py` — `user_id`를 `users` 테이블에 INSERT (멱등: 이미
  있으면 조용히 무시)
- `api/users.py` — `POST /users` (APIRouter; 메인 앱에 `include_router`로
  등록되는 것을 전제로 함)

온보딩/시뮬레이션/트렌드 리포트 등 다른 기능은 이렇게 등록된 `user_id`가 이미
있다고 가정하고 그대로 받아쓴다. 나중에 실제 로그인이 필요해지면 `users`
테이블에 email 등 인증 관련 컬럼을 추가해 이 UUID에 매핑하는 방식으로
확장하면 된다.

## 온보딩 (`onboarding/`, `functions/`, `api/onboarding.py`)

7개 질문 응답을 받아 `users` 테이블의 5개 필드(`risk_profile`, `investment_goal`,
`investment_amount_range`, `investment_experience`, `interest_sectors`)로 변환해
저장하고, 다른 에이전트가 유저 컨텍스트를 조회할 수 있게 한다.

- `onboarding/processor.py` — DB 접근 없는 순수 변환 로직 (점수 산출, 섹터 검증)
- `functions/save_onboarding.py` — 변환 후 `users` 테이블에 UPSERT
- `functions/get_user_context.py` — `users` 테이블 조회, JSON 필드 파싱
- `api/onboarding.py` — `POST /onboarding`, `GET /users/{user_id}/context` (APIRouter;
  메인 앱에 `include_router`로 등록되는 것을 전제로 함)

### 중요: `ant-secretariat-data-pipeline`에 대한 의존성

`users` 테이블을 포함한 DB 스키마(`CREATE TABLE`)는 이 레포가 아니라
`ant-secretariat-data-pipeline` 레포의 `crawling/db/schema.sql`이 canonical로 소유한다.
`reports.db` 하나를 crawling/processing/backend가 함께 쓴다.

이 레포는 자체 DB 접근 계층을 새로 만들지 않고, `db.py`를 통해
`ant-secretariat-data-pipeline`의 `crawling.db.database.Database`를 그대로 재사용한다.
연결은 `sys.path` 조작이 아니라 `requirements.txt`의 editable install로 이루어진다:

```
-e ../ant-secretariat-data-pipeline
```

**두 레포가 같은 부모 디렉토리 아래 형제(sibling)로 클론되어 있어야 한다**
(로컬/동일 서버 배포 기준):

```
투빅스/
├── ant-secretariat-backend/       (이 레포)
└── ant-secretariat-data-pipeline/  (pyproject.toml로 pip 설치 가능한 패키지)
```

배포 구조가 바뀌어 두 레포가 다른 위치에 있게 되면 `requirements.txt`의 이 경로를
재검토해야 한다 (예: git URL 설치로 전환).

## 트렌드 리포트 (`agents/trend_report/`)

증권사 리포트, 목표주가, 뉴스, 매크로 컨텍스트를 Agent B(`ant-secretariat-data-pipeline`의
`processing` 모듈) 공통 함수로 조회해 카드형 트렌드 리포트 JSON을 생성한다.
[tobigs-conference/trend-report-agent](https://github.com/tobigs-conference/trend-report-agent)를
이 레포 구조에 맞게 가져온 것이다.

- `agents/trend_report/config.py` — 지원 기업(`SUPPORTED_COMPANIES`), 조회 범위 확장
  정책(1→3→7→30일), 환경변수 헬퍼
- `agents/trend_report/schemas.py` — `ReportChunk`, `CompanyEvidence`,
  `TrendReportRequest`, `TrendReportResult`
- `agents/trend_report/data_agent_client.py` — Agent B 어댑터. `processing.functions.*`
  (search_documents, get_report_metadata, get_target_price_data, get_price_data,
  get_macro_data)와 `processing.storage.*`(SQLiteDB, PineconeVectorDB,
  UpstageEmbeddingModel)를 그대로 재사용한다
- `agents/trend_report/pinecone_retriever.py` — Pinecone `report_chunks` 직접 조회
  (레거시 마크다운 브리핑 전용, `service.py`의 `run()`에서만 사용)
- `agents/trend_report/prompts.py`, `report_generator.py` — 카드 JSON/브리핑 생성 프롬프트와
  Upstage(OpenAI 호환) 호출
- `agents/trend_report/service.py` — `TrendReportAgent`. `run_trend_report()`가 주 경로
  (카드 JSON), `run()`은 `--legacy-markdown` 호환 경로
- `agents/trend_report/run.py` — CLI 진입점: `python -m agents.trend_report.run --ticker 005930`

### Agent B 의존성

원본 저장소는 `data_agent_client.py`가 별도의 `financial_research_data_agent` 레포를
sys.path로 끌어오는 구조였다. 이 레포에서는 그 "Agent B"가 실제로는
`ant-secretariat-data-pipeline`의 `processing` 패키지(`processing.functions.*`,
`processing.storage.*`, `processing.interfaces`)와 동일한 코드이고, 이미
`-e ../ant-secretariat-data-pipeline`로 editable install되어 있으므로 별도 경로
설정 없이 `processing.functions.search_documents`처럼 바로 import한다(db.py가
`crawling.db.database.Database`를 재사용하는 것과 같은 패턴). report_chunks
계열 조회에 필요한 `SQLiteDB`는 `db.py`의 `Database`와 별개 클래스지만, 같은 공유
`reports.db` 파일을 가리킨다.

환경변수(`UPSTAGE_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX` 등)는
`.env.example` 참고.

## 시뮬레이션 (`agents/simulation/`)

증권사 리포트가 아니라 주가/매크로 시계열로 LSTM 기반 수익률 분포를 학습하고,
Monte Carlo(1,000-path, 30일)로 가격 경로를 시뮬레이션해 리스크 프로필에 맞는
해석 문구까지 패키징한다. [tobigs-conference/simulation-agent](https://github.com/tobigs-conference/simulation-agent)를
이 레포 구조에 맞게 가져온 것이다.

```
1단계: 데이터 수집    (data_collector.py)   - Agent B DB에서 주가/매크로/유저 컨텍스트 수집
2단계: 전처리         (preprocessor.py)     - 로그수익률 계산, LSTM 텐서 구성
3단계: 리스크 분류    (risk_classifier.py)  - LLM(Upstage solar-pro)으로 매크로 리스크 요인 분류
4단계: LSTM 예측      (model.py)            - 수익률 분포(mu, sigma) 예측 + What-if(apply_shock)
5단계: Monte Carlo    (monte_carlo.py)      - 1,000개 가격 경로 시뮬레이션
6단계: 결과 패키징    (result_packager.py)  - 리스크 프로필 기반 해석 문구 생성
7단계: 진입점         (service.py)          - run_simulation(), 프론트/디베이트 에이전트 호출 지점
```

- `evaluate_model.py` — 학습된 LSTM의 MAE/RMSE/방향 정확도/커버리지 평가 유틸리티
- 학습된 모델은 `agents/simulation/_model_cache/{ticker}.pt`에 캐싱되고 24시간 지나면 재학습된다

### 원본 대비 변경한 부분

- **Agent B 연동**: 원본은 `_external_deps.py`가 별도의 `financial_research_data_agent`
  레포를 sys.path로 끌어오는 구조였다. `agents/trend_report`와 마찬가지로 이 "Agent B"는
  실제로 `ant-secretariat-data-pipeline`의 `processing` 패키지와 동일한 코드이므로
  `_external_deps.py`는 제거하고 `data_collector.py`에서
  `processing.functions.get_agent_context`, `processing.storage.sqlite_db.SQLiteDB`,
  `processing.interfaces.BaseRelationalDB`를 바로 import한다. 별도 sys.path 조작이나
  외부 레포 클론이 필요 없다.
- **DB 경로 통일**: 원본의 `B_DB_PATH`, `DATA_AGENT_REPO_PATH` 환경변수를 없애고, 이미
  db.py/trend_report가 쓰는 `DATABASE_PATH` 하나로 합쳤다(모두 같은 공유 `reports.db`를
  가리키므로 환경변수가 두 개일 이유가 없다).
- **`get_user_context()` 실제 연결**: 원본은 `_mock_get_user_context()`가 항상
  `moderate`/`mid_term` 목업 데이터를 반환했다(README에도 "실제 유저 DB 연결 필요"로 명시된
  제약이었음). 이 레포는 이미 `functions/get_user_context.py`가 구현되어 있으므로
  그것을 그대로 연결했다. 따라서 온보딩을 완료하지 않은 `user_id`로 시뮬레이션을 요청하면
  (목업처럼 조용히 넘어가지 않고) `ValueError`가 발생해 `run_simulation()`의 에러 응답
  경로로 처리된다 — 온보딩 여부를 확인하지 않고 넘어가던 원본 동작보다 엄격해진 것이니
  참고할 것.
- 모듈 경로를 `simulation_agent.*` → `agents.simulation.*`로 변경했고, CLI는
  `python -m agents.simulation.service --ticker 005930` 형태로 실행한다.

### 필요 환경변수

`UPSTAGE_API_KEY`(trend_report와 공유), `RISK_CLASSIFIER_MODEL`(선택, 기본 `solar-pro`).
`.env.example` 참고.

## 설치 및 테스트

```bash
pip install -r requirements.txt   # -e ../ant-secretariat-data-pipeline 포함
cp .env.example .env
pytest
```
