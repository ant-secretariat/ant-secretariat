# agents/debate_renewal — Claude Code 작업 지침

토론 에이전트(Agent F) 리빌드의 **신규 구현** 패키지. 위치: `backend/agents/debate_renewal/` (모노레포, 팀 결정: 레포 분리 없이 에이전트 폴더 안에서 작업하고 기능 단위로 PR을 계속 올린다). 담당: 유민(AI PM). 팀: 태은(오케스트레이터), 수경(데이터·인프라).

## 가장 중요한 규칙

1. **기존 `backend/agents/debate/`는 재활용도 수정도 하지 않는다.** 1차 프로토타입이고 오케스트레이터가 아직 호출하므로 당분간 그대로 병행한다. 교체는 새 버전 완성·연동 후 별도 PR로 한다.
2. **기준 문서는 `docs/debate-renewal/debate-agent-rebuild-spec-v3.0.html`** (토론 에이전트 리빌드 기획서 v3.0). 구현이 기획서와 다르면 코드를 맞추거나, 기획서를 바꿔야 하는 이유를 유민에게 먼저 묻는다. 온톨로지는 `docs/debate-renewal/ontology-spec-v1.2.html` (이번 범위에서는 인터페이스 참조용).
3. 내 담당이 아닌 부분은 만들지 않고 인터페이스(Protocol·스텁)만 둔다.

| 소유 | 항목 |
| --- | --- |
| 유민 (이 패키지) | `precheck()`, 키워드 사전, `PrecheckResult`, `run_debate`, Bull·Bear·Judge, 검증 레이어, 비교 모드, 평가셋 |
| 태은 | 관문1·`EntityResolution`, 작업 큐, `job_events`·SSE, 도구 레지스트리, Langfuse, `backend/contracts` |
| 수경 | `intent_data_sources.json`, `ensure_company_data`, 데이터 함수, 골든셋 마스터 |

## 협업 컨벤션 (`docs/CONVENTIONS.md` 요약)

- 브랜치 `feat/<로드맵ID>-<설명>`, main 직접 push 금지. 현재 브랜치: `feat/3.x-debate-agent-renewal`
- 커밋은 `feat: 한 줄 요약` + 한국어 본문, 한 커밋 한 변경. 제목 50자 안쪽, 마침표 없음
- PR은 400줄 이하, Squash merge, 리뷰어 1명 승인 (자세한 양식은 아래 "PR 양식")
- **팀 합의(11/9)**: 레포를 분리하지 않는다. 각자 에이전트 브랜치에서 작업하고, 기능 하나가 끝날 때마다 바로 PR을 올려 계속 병합한다(큰 PR 하나 금지). 다른 에이전트·데이터 파이프라인의 입출력을 같은 레포에서 바로 읽으며 맞추기 위함
- 응답 품질에 영향 주는 변경(프롬프트·모델·검색)은 평가 수치 비교표 없이 병합하지 않는다
- `.env`, API 키, 수집 원본 데이터는 커밋 금지

## PR 양식 (수경 nasuzz의 PR #10~#19와 같은 방식)

`.github/pull_request_template.md`의 제목(변경 요약·변경 이유·검증·체크리스트·리뷰 포인트·남은 작업·`Closes #`)을 **그대로** 쓰고 지우지 않는다. 참고용 실제 예: PR #17, #18 (`gh api repos/ant-secretariat/ant-secretariat/pulls/17 --jq .body` 또는 GitHub 웹).

- **제목**: `feat: 한 줄 요약` (한국어, 컨벤션 형식)
- **변경 요약**: 1~3줄. 무엇이 추가되고 무엇이 바뀌는지
- **변경 이유**: 누가 왜 필요한지 (예: "오케스트레이터가 job 생성 전에 거절 여부를 알기 위해")
- **검증**: 실제로 실행한 명령과 결과를 코드블록에 붙인다. 예: `cd backend` / `pytest tests/test_debate_renewal_precheck.py -q` / `# 24 passed`. 못 돌린 테스트는 이유를 쓴다
- **평가 비교표**: 프롬프트·모델·검색을 바꾼 PR만 채우고, 아니면 표를 지우고 체크리스트에 "(해당 없음)"으로 적는다
- **체크리스트**: 해당 항목을 `[x]`로 체크하고, 해당 없는 항목에는 이유를 괄호로 적는다
- **리뷰 포인트**: 판단이 애매했던 선택, 임시값(`envelope.py` 이름 등), 수경·태은이 확인할 부분은 `@멘션`으로 적는다
- **남은 작업**: 이번에 안 한 것. 없으면 "없음"
- **Draft**: 방향 확인이 필요하면 Draft로 먼저 연다
- **쌓인 PR(스택)**: 앞 PR이 머지되기 전에 그 위에서 다음 작업을 해야 하면, 다음 PR의 대상(base)을 앞 PR 브랜치로 열고 본문 맨 위에 인용문(`>`)으로 "N개 중 몇 번째, 머지 순서, 앞 PR 먼저 머지할 것, 앞 PR 머지 후 대상 변경은 작성자가 함"을 적는다 (PR #17 형식). 가능하면 main 기준 독립 PR을 우선한다
- **PR 크기**: 400줄 이하. 기획서 HTML(`docs/debate-renewal/`)은 줄 수가 커서 코드 PR에서 빼고 별도 `docs:` PR로 올린다
- **리뷰어**: @taeeunni 한 명만 지정한다 (멀티에이전트 담당. `.github/CODEOWNERS` 기본값으로 자동 지정됨). 수경은 리뷰어로 추가하지 않고, 데이터 계약 관련 확인이 필요하면 "리뷰 포인트"에 `@멘션`만 한다

## 다른 쪽과 맞춰야 할 때 읽을 곳 (같은 레포)

- 데이터: `data-pipeline/processing/functions/`(get_agent_context, get_available_data_status 등), `data-pipeline/crawling/`, `supabase/migrations/`. 수경의 진행 중인 브랜치 `origin/feat/data-*`(target-price-contract, metric-status, investor-flow, financials-point-in-time, kis-opinions 등)에 아직 main에 없는 계약이 있다. 연동 전에 `git fetch` 후 해당 브랜치 diff를 먼저 본다
- 오케스트레이터: `backend/orchestrator/`(schemas·graph·service), `backend/api/orchestrator.py`, `backend/api/debate_jobs.py`, `backend/functions/agent_jobs.py`. 기존 debate 호출 방식이 여기 있다(새 버전과 병행 중)
- 시뮬레이션: `backend/agents/simulation/` — 토론 결과의 macro·risk 아젠다를 `job_id`로 조회해 쓰게 될 대상
- 남의 파일은 수정하지 않는다. 필요한 변경은 인터페이스(Protocol)로 이 패키지 쪽에서 선언하고 담당자에게 알린다

## 설계 불변 조건 (기획서 v3.0)

- `AgendaId`·`DataTier`·`ReasonCode`·`NextAction`은 열거형만 쓴다. 문자열 하드코딩 금지
- `precheck()`는 **순수 함수**: LLM·네트워크·DB 호출 금지, 수 ms. 종목 데이터 현황은 `data_status` provider로 주입
- 데이터 접근은 도구 레지스트리 `invoke()` 경유. 데이터 함수 직접 import 금지
- LLM은 Upstage Solar(OpenAI 호환), `json_schema` strict 출력 + Pydantic 검증 (D7)
- `Claim.text`의 숫자는 `{{placeholder}}`로 쓰고 코드가 `get_metric` 값으로 치환
- 사실 층(근거·verdict·stance)은 사용자 성향과 무관하게 동일. 성향은 Judge의 `points_to_check`·`caution`에만 반영. **적합/부적합 label 노출 금지**
- 비교 모드는 최대 2종목: 종목별 Bull→Bear(종목끼리 병렬) + Judge 축별 비교, 제시 순서 무작위화, 한쪽 실패 시 단일 분석으로 전환
- 2라운드(D5)·시뮬레이션 버튼은 단일 모드 전용
- job 상태: `queued → running → debate_completed → (단일) simulation_pending → … → completed/failed`. `simulation_handoff` 필드는 없다(삭제됨)
- 진행 이벤트는 노드·주장 단위(`node_started`·`claim_completed`·`agenda_completed`·`node_completed`). 토큰 단위 금지 (D8) — 단, 태은 쪽 확정 전까지는 제안 상태

## 구현 순서

| # | 항목 | 상태 |
| --- | --- | --- |
| 1 | `precheck()` + 키워드 사전 + `intent_data_sources.json` 로더 | 완료 (24 tests). PR 2개로 나눠 병합: 계약·설정 로더 → 엔진·테스트 |
| 2 | 거절셋 수집 (`ReasonCode` 라벨) | 예정 — precheck 튜닝용, 키워드 사전 보강과 함께 |
| 3 | Pydantic 스키마: Evidence·Claim·DebateResult(단일→비교), Bull·Bear·Judge 출력 | **다음** |
| 3b | Bull·Bear·Judge 프롬프트 v3 (D6 `agreed_points`, Bear의 Bull Claim 인용) | 예정 |
| 4 | 검증 레이어 L1 + 근거 부족 루프(1회 수정) | 예정 |
| 5 | 기준선 비교 실험 루브릭 5~6항목 + 문항 30~50개 | 예정 |
| 6 | 온톨로지 ISSUE 시드 20~30개 | 예정 (온톨로지 기획서) |

## 확정 필요한 임시값 (코드 곳곳에 TODO)

- `ReasonCode.insufficient_data` — `envelope.py` 확정 이름으로 교체 (`contracts.py`). 3종목·한쪽 미커버 등 관문1 코드도 같음
- 관문1 거절 코드(미커버 종목·3종목 이상·비교 한쪽 미커버)의 `envelope.py` 이름. 11/9 기준 회의에서 확정되지 않았다. precheck 밖이라 이 패키지는 정의하지 않고, 확정되면 `ReasonCode`에 추가한다
- 공용 계약 위치(`backend/contracts`, data-pipeline)가 생기면 `contracts.py`를 import로 교체하고 파일 삭제
- `data/intent_data_sources.json` — 수경과 아젠다별 필요 데이터·신선도·T0 가능 여부 확정
- 아젠다 대체 우선순위(`data/keyword_dictionary.json`의 `selection_rules`) — 기획서에 "최대 3개 유지"만 있음
- `flow` 아젠다 `active: false` — `investor_flow_daily` 확보 후 활성화
- 큐 라이브러리(PgQueuer vs Procrastinate), 배포 방식은 팀 결정 대기

## 명령

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate     # macOS/Linux: source .venv/bin/activate
pip install pydantic pytest pytest-asyncio          # precheck만 돌릴 때는 이것으로 충분
pytest tests/test_debate_renewal_precheck.py
# 전체 백엔드 테스트는 requirements.txt 전체 설치 필요 (torch 등 무거움)
```

## 작업 방식

- 한 번에 한 항목씩. 항목마다: 구현 → 테스트 → 로컬 커밋(컨벤션대로) → 유민에게 요약 보고
- 기획서에 없는 결정이 필요하면 임의로 정하지 말고 질문하거나, 임시값으로 두고 위 "확정 필요" 표에 추가한다
- 유민은 한국어 반말 캐주얼, 간결한 답변을 선호한다
