# agents/debate_renewal

토론 에이전트(Agent F) **리빌드 신규 구현**. 기존 `backend/agents/debate`(1차 프로토타입, 당분간 병행)를 재활용하지 않고, 토론 에이전트 리빌드 기획서 v3.0 기준으로 처음부터 만든다.

## 구현 현황

| 항목 | 상태 |
| --- | --- |
| 공용 계약 타입(`contracts.py`) + 키워드 사전 + `intent_data_sources.json` 로더 | 완료 |
| `precheck()` 관문2·3 엔진 + 테스트 24개 | 완료 |
| precheck 어댑터(관문1 `resolve_company` 결과 → `CompanyContext`·`data_status`) | 완료 (테스트 14개) |
| Pydantic 스키마 (Bull·Bear·Judge·DebateResult, 단일·비교) | 완료 (테스트 10개) |
| 거절셋 v0.3 (dev 47·holdout 22·holdout2 22) + 측정기 + 키워드 사전 kw-0.3.1 | 완료 — `python -m agents.debate_renewal.eval.refusal` |
| 검증 레이어 L1 (결정적 검사) | 완료 (테스트 10개) |
| 기준선 비교 실험 루브릭(6항목)·문항(48개)·블라인드 채점 집계(승률 포함) | 완료 (테스트 13개) |
| 기준선 출력 생성기 (`eval/baseline/run.py`: 같은 근거로 토론·단일 LLM 출력, 블라인드 텍스트, 채점 pack) | 완료 (테스트 7개) — `python -m agents.debate_renewal.eval.baseline.run --out <git 밖 폴더>` |
| Bull·Bear·Judge 프롬프트 v3 (`prompts/`, 메시지 조립·strict 출력 스키마) | 완료 (테스트 13개) — LLM 호출은 run_debate 연동 때 |
| Solar 호출 클라이언트 (`llm.py`, strict json_schema + Pydantic 검증, 형식 오류 1회 재요청) | 완료 (테스트 11개) |
| 단일 모드 `run_debate` (`service.py`: 근거 → 아젠다별 Bull→Bear 병렬 → Judge → DebateResult → L1, 이벤트 emit 주입) | 완료 (테스트 11개, 실데이터 2종목 확인) |
| 근거 부족 루프, 비교 모드 실행, 2라운드 프롬프트 | 예정 |

## 실행

```bash
cd backend
pip install pydantic pytest pytest-asyncio -e ../data-pipeline
pytest tests/test_debate_renewal_precheck.py tests/test_debate_renewal_precheck_adapter.py
```

오케스트레이터(관문1)에서 부르는 법:

```python
from agents.debate_renewal.precheck import DataStatusUnavailable, company_context, data_status_provider, precheck

resolved = {t: resolve_company(t) for t in tickers}   # 관문1에서 이미 받은 값 재사용
try:
    result = precheck(query, [company_context(resolved[t]) for t in tickers],
                      data_status=data_status_provider(resolved), company_mentioned=mentioned)
except DataStatusUnavailable:
    raise UpstreamUnavailableError(...)  # 503, 조회 실패를 "데이터 없음"으로 바꾸지 않음
```

## 구조

```
backend/agents/debate_renewal/
  contracts.py              # AgendaId·Tier·DataTier·ReasonCode·NextAction·PrecheckResult (임시 위치)
  precheck/                 # 규칙 기반 순수 함수, LLM 없음
    adapter.py              # 관문1 결과 → precheck 입력. 조회 실패는 None → DataStatusUnavailable (503)
  prompts/                  # Bull·Bear·Judge 프롬프트 v3 문구·메시지 조립·Judge 출력 모양 (LLM 호출 없음)
  config.py                 # 모델·온도·타임아웃 (DEBATE_RENEWAL_LLM_* 환경변수로 덮어씀)
  llm.py                    # Solar 구조화 출력 호출 complete_structured()
  evidence.py               # 검색 결과 → Evidence(S1…), chunk_id 중복 제거
  structured.py             # 데이터 묶음의 지표·블록 → 근거 행, {{metric_id}} → display 치환
  service.py                # 단일 모드 run_debate()
  data/keyword_dictionary.json
  data/intent_data_sources.json   # 수경 제안값 반영 (소유자는 데이터 에이전트)
```

## 확정 필요 (코드에 임시값으로 들어가 있음)

- 거절 코드는 계약 이름을 쓴다: 데이터가 없어 남는 아젠다가 없으면 `no_data` (11/17 결정)
- 공용 계약 위치(`backend/contracts`, data-pipeline)가 생기면 `contracts.py`를 import로 교체
- `intent_data_sources.json`: 아젠다별 필요 데이터·신선도 기준·T0 가능 여부 (수경과 확정). ds-0.3.0부터 매크로 아젠다는 종목 데이터(`sensitivity`·`news`·`report`) 중 하나가 있어야 함 — `macro` 건수는 시장 전체 지표 수라서(#72 리뷰)
- 아젠다 대체 우선순위(`selection_rules`): 기획서에 "최대 3개 유지"만 있고 무엇을 빼는지는 없음
- `allowed_agendas` 순서: 질의에서 확인한 아젠다가 앞, 남은 자리는 기본 아젠다로 채운다(#98). 기본 3개(밸류에이션·매크로·리스크)를 묻는 질의는 구성은 빈 질의와 같고 순서만 다르다(예: "금리 영향" → `[macro, valuation, risk]`)
- `flow` 아젠다는 `active: false` (investor_flow_daily 확보 후 활성화)
- 토론 모델 `solar-pro-4`, 온도 0.2, 타임아웃 60초, SDK 재시도 2회는 임시값. 11/23 프로브에서 pro-4·mini-4 모두 strict 스키마 통과(pro 약 2~4초, mini 약 1초). 기준선 평가(#51) 후 확정
- 출력이 재요청 후에도 스키마와 다르면 `LLMOutputInvalidError`(지금은 503 `upstream_unavailable`). 전용 코드는 정책표(OQ-2) 확정 후
- 환경변수 이름은 기존 `agents/debate`의 `DEBATE_LLM_MODEL`과 겹치지 않게 `DEBATE_RENEWAL_LLM_*`
- `run_debate` claim_id: 프롬프트는 아젠다마다 `B1`·`R1`부터 매기고, 코드가 아젠다 ID를 앞에 붙인다(`valuation-B1`). L1이 결과 전체에서 유일한 id를 요구해서
- 지표·블록 근거(`structured.py`): 사실 문장으로 넣는 사유(`loss_making`·`capital_impaired`·`not_applicable_financials`), 블록 요약 문장 형식(목표가 최근 의견 5건, 재무 8분기, 매크로는 최신 값만)은 임시값. 기준선 출력 보고 다듬음
- 근거 본문 길이 `PREVIEW_CHARS` 600자, `data_richness`는 `data_tier == report`면 rich 그 외 limited (임시값)
- 진행 이벤트는 계약 `JobEvent`(ADR 0009) 이름·payload: `data_collected`(문서 종류별 건수) → 아젠다마다 `claim_completed`(`role`·`agenda_id`·`claim`)·`bull_completed`·`bear_completed`(`agenda_id`·`claim_count`) → `judge_completed` → `verifying`. `job_started`·`completed`·`failed`는 워커
- Judge가 아젠다 판정을 빠뜨리면 채우지 않고 `LLMOutputInvalidError`
- 근거 부족 루프: 근거 없는 Claim의 문장으로 `fetch_evidence`를 다시 불러 Claim당 2개(`GAP_TOP_K`, 임시값)까지 `gap_fill`로 더한다. 1회 수정은 문제가 있는 노드만 다시 생성(Bull을 다시 쓰면 Bear·Judge도)
- partial: 수정 뒤에도 실패한 Claim은 빼고 `DebateRun.removed_claim_ids`에 남긴다. MVP에서는 결과에 partial 고지 칸을 만들지 않고 로그(`debate partial … removed=`)로만 남긴다(#78 리뷰). 기준선 48문항에서 빠진 Claim 수를 세어 자주 나오면 계약 칸·고지 UI를 정한다. Bear가 반박한 Bull Claim이 빠지면 `bad_bull_claim_ref`를 L1에 남기고 반박 대상을 바꾸지 않는다. 보여 주는 방식은 기준선에서 실제로 나오면 R4 렌더링(#119)과 함께 정한다
- 기준선 단일 LLM 프롬프트(`eval/baseline/single.py`, single-1.0.0): 토론과 같은 `COMMON_RULES`, 긍정 2~4·부정 1~3·엇갈리는 점·요약. 토론에 불리하거나 유리하지 않은지 채점 전에 한 번 더 확인 필요
- 블라인드 텍스트(`render.py`): 두 시스템을 긍정·부정·엇갈리는 점·종합·근거 목록으로 맞추고 Bull·Bear 이름을 긍정론·부정론으로 바꾼다. 토론의 엇갈리는 점에는 Judge 판정 이유와 Bear `agreed_points`를 넣는다. 반박 문체("~라고 보지만")로 짐작될 수 있는 한계는 남음
- 기준선 문항은 아젠다를 문항의 `agenda_id` 하나로 고정해 토론을 돌린다(precheck 아젠다 선택은 거치지 않음)
