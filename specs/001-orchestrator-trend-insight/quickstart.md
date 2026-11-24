# Quickstart: 검증 시나리오

구현이 spec의 인수 조건을 만족하는지 확인하는 순서다. 구현 코드는 여기 두지 않는다.

## 준비

```bash
cd backend
pip install -r requirements.txt          # -e ../data-pipeline 포함
cp .env.example .env                     # UPSTAGE_API_KEY, SUPABASE_DB_URL 필수 (#60)
# Supabase에 supabase/migrations/ 신규 마이그레이션 적용 (agent_jobs, job_events, uncovered_query_log)
uvicorn main:app --reload
```

## 자동 테스트

```bash
cd backend && python -m pytest -q                 # 전체
python -m pytest -q tests/contract                # 응답이 openapi.yaml 스키마를 통과하는지 (SC-001)
```

## 수동 시나리오

| # | 요청 | 기대 결과 | 대응 |
| --- | --- | --- | --- |
| 1 | `POST /orchestrate/debate {"companies":["삼성전자"],"query":"밸류에이션 어때?"}` | 200 `job_started`, `reused:false`, 1초 안 | US1-1 |
| 2 | 1을 다시 보냄 (진행 중) | 같은 `job_id`, `reused:true` | US1-2 |
| 3 | 종목 3개로 토론 | 200 `rejected`, `too_many_companies`, `select_companies` | US1-3 |
| 4 | `query:"오늘 점심 메뉴"` | 200 `rejected`, `out_of_scope_topic`, job 0건, `uncovered_query_log` 1행 | US1-4 |
| 5 | `curl -N -H "Last-Event-ID: 2" /jobs/{id}/events` | `seq` 3부터, 15초 ping, 종료 이벤트 후 연결 종료 | US1-5 |
| 6 | `POST /orchestrate/trend-report {"company":"삼성전자"}` | `ok`, 모든 `evidence_ids`가 `evidence`에 있음, `target_price_trend.avg_target_price` = `get_target_price_data(...).consensus.avg_target_price` | US2-1 |
| 7 | 리포트 없는 종목(`news_only`)으로 6 | 증권사 시각차 카드 없음 | FR-008 |
| 8 | `POST /orchestrate/insight-board` 3종목, 한 종목 데이터 함수가 `error` (테스트 픽스처) | `partial`, `retry_failed_parts`, 나머지 2종목 `ok` | US3-1 |
| 9 | 종목 조회 DB 장애 (`SUPABASE_DB_URL` 잘못 설정) | 503 Problem `upstream_unavailable` (rejected 아님) | Edge |

## 측정 (PR 본문에 첨부)

- 트렌드 리포트: 고정 종목셋 10개로 근거 연결률·철회율·p95 지연 (SC-003, 헌법 원칙 V)
- 관문1: 종목 입력셋(정확·별칭·애매·미커버·오타) 기대 status 일치율 (SC-005)
- 목표주가 방향: 운영 DB 96종목의 방향 분포 (research R5)
