# agents/debate_renewal

토론 에이전트(Agent F) **리빌드 신규 구현**. 기존 `backend/agents/debate`(1차 프로토타입, 당분간 병행)를 재활용하지 않고, 토론 에이전트 리빌드 기획서 v3.0 기준으로 처음부터 만든다.

## 구현 현황

| 항목 | 상태 |
| --- | --- |
| 공용 계약 타입(`contracts.py`) + 키워드 사전 + `intent_data_sources.json` 로더 | 완료 |
| `precheck()` 관문2·3 엔진 + 테스트 24개 | 다음 PR (이 PR 위에 쌓임) |
| Pydantic 스키마 (Bull·Bear·Judge·DebateResult) | 예정 |
| 거절셋 v0 (47문항) + 측정기 | 완료 — `python -m agents.debate_renewal.eval.refusal` |
| 기준선 비교 실험 루브릭(6항목)·문항(40개)·블라인드 채점 집계 | 완료 (테스트 8개) — 실험 실행은 출력 생성 후 |
| 프롬프트 v3, 검증 레이어, 비교 모드 | 예정 |

## 실행

```bash
cd backend
pip install pydantic pytest pytest-asyncio
pytest tests/test_debate_renewal_precheck.py
```

## 구조

```
backend/agents/debate_renewal/
  contracts.py              # AgendaId·DataTier·ReasonCode·NextAction·PrecheckResult (임시 위치)
  precheck/                 # 규칙 기반 순수 함수, LLM 없음
  data/keyword_dictionary.json
  data/intent_data_sources.json   # 스텁 — 소유자는 데이터 에이전트(수경)
```

## 확정 필요 (코드에 임시값으로 들어가 있음)

- `ReasonCode.insufficient_data`: envelope.py 확정 이름으로 교체 (`contracts.py` TODO)
- 공용 계약 위치(`backend/contracts`, data-pipeline)가 생기면 `contracts.py`를 import로 교체
- `intent_data_sources.json`: 아젠다별 필요 데이터·신선도 기준·T0 가능 여부 (수경과 확정)
- 아젠다 대체 우선순위(`selection_rules`): 기획서에 "최대 3개 유지"만 있고 무엇을 빼는지는 없음
- `flow` 아젠다는 `active: false` (investor_flow_daily 확보 후 활성화)
