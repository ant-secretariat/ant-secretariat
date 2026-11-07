# debate-agent-renewal

토론 에이전트(Agent F) **리빌드 신규 구현**. 기존 `backend/agents/debate`(1차 프로토타입)를 재활용하지 않고, 토론 에이전트 리빌드 기획서 v3.0 기준으로 처음부터 만든다.

## 구현 현황

| 항목 | 상태 |
| --- | --- |
| `precheck()` 관문2·3 + 키워드 사전 + `intent_data_sources.json` 로더 | 완료 (테스트 24개) |
| Pydantic 스키마 (Bull·Bear·Judge·DebateResult) | 예정 |
| 프롬프트 v3, 검증 레이어, 비교 모드 | 예정 |

## 실행

```bash
cd debate-agent-renewal
pip install -e ".[dev]"
pytest
```

## 구조

```
src/debate_agent/
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
