# agents/debate_renewal

토론 에이전트(Agent F) **리빌드 신규 구현**. 기존 `backend/agents/debate`(1차 프로토타입, 당분간 병행)를 재활용하지 않고, 토론 에이전트 리빌드 기획서 v3.0 기준으로 처음부터 만든다.

## 구현 현황

| 항목 | 상태 |
| --- | --- |
| 공용 계약 타입(`contracts.py`) + 키워드 사전 + `intent_data_sources.json` 로더 | 완료 |
| `precheck()` 관문2·3 엔진 + 테스트 24개 | 다음 PR (이 PR 위에 쌓임) |
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
pytest tests/test_debate_renewal_precheck.py
```

## 구조

```
backend/agents/debate_renewal/
  contracts.py              # AgendaId·Tier·DataTier·ReasonCode·NextAction·PrecheckResult (임시 위치)
  precheck/                 # 규칙 기반 순수 함수, LLM 없음
  prompts/                  # Bull·Bear·Judge 프롬프트 v3 문구·메시지 조립·Judge 출력 모양 (LLM 호출 없음)
  config.py                 # 모델·온도·타임아웃 (DEBATE_RENEWAL_LLM_* 환경변수로 덮어씀)
  llm.py                    # Solar 구조화 출력 호출 complete_structured()
  evidence.py               # 검색 결과 → Evidence(S1…), chunk_id 중복 제거
  service.py                # 단일 모드 run_debate()
  data/keyword_dictionary.json
  data/intent_data_sources.json   # 수경 제안값 반영 (소유자는 데이터 에이전트)
```

## 확정 필요 (코드에 임시값으로 들어가 있음)

- 거절 코드는 계약 이름을 쓴다: 데이터가 없어 남는 아젠다가 없으면 `no_data` (11/17 결정)
- 공용 계약 위치(`backend/contracts`, data-pipeline)가 생기면 `contracts.py`를 import로 교체
- `intent_data_sources.json`: 아젠다별 필요 데이터·신선도 기준·T0 가능 여부 (수경과 확정)
- 아젠다 대체 우선순위(`selection_rules`): 기획서에 "최대 3개 유지"만 있고 무엇을 빼는지는 없음
- `flow` 아젠다는 `active: false` (investor_flow_daily 확보 후 활성화)
- 토론 모델 `solar-pro-4`, 온도 0.2, 타임아웃 60초, SDK 재시도 2회는 임시값. 11/23 프로브에서 pro-4·mini-4 모두 strict 스키마 통과(pro 약 2~4초, mini 약 1초). 기준선 평가(#51) 후 확정
- 출력이 재요청 후에도 스키마와 다르면 `LLMOutputInvalidError`(지금은 503 `upstream_unavailable`). 전용 코드는 정책표(OQ-2) 확정 후
- 환경변수 이름은 기존 `agents/debate`의 `DEBATE_LLM_MODEL`과 겹치지 않게 `DEBATE_RENEWAL_LLM_*`
- `run_debate` claim_id: 프롬프트는 아젠다마다 `B1`·`R1`부터 매기고, 코드가 아젠다 ID를 앞에 붙인다(`valuation-B1`). L1이 결과 전체에서 유일한 id를 요구해서
- 근거 본문 길이 `PREVIEW_CHARS` 600자, `data_richness`는 `data_tier == report`면 rich 그 외 limited (임시값)
- 아젠다 하나의 Bull·Bear가 실패하면 토론 전체가 실패한다. 남은 아젠다로 계속할지(부분 결과)는 기획서에 없음
- Judge가 아젠다 판정을 빠뜨리면 채우지 않고 `LLMOutputInvalidError`
- 기준선 단일 LLM 프롬프트(`eval/baseline/single.py`, single-1.0.0): 토론과 같은 `COMMON_RULES`, 긍정 2~4·부정 1~3·엇갈리는 점·요약. 토론에 불리하거나 유리하지 않은지 채점 전에 한 번 더 확인 필요
- 블라인드 텍스트(`render.py`): 두 시스템을 긍정·부정·엇갈리는 점·종합·근거 목록으로 맞추고 Bull·Bear 이름을 긍정론·부정론으로 바꾼다. 토론의 엇갈리는 점에는 Judge 판정 이유와 Bear `agreed_points`를 넣는다. 반박 문체("~라고 보지만")로 짐작될 수 있는 한계는 남음
- 기준선 문항은 아젠다를 문항의 `agenda_id` 하나로 고정해 토론을 돌린다(precheck 아젠다 선택은 거치지 않음)
