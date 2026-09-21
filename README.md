# 개미비서단 (ant-secretariat)

개인 투자자를 위한 **토론형 금융 AI 서비스**. 애널리스트 리포트를 수집·검색해서 강세(Bull)·약세(Bear) 에이전트가 토론하고, 판정 결과를 몬테카를로 시뮬레이션으로 가격 분포까지 이어줍니다.

현재는 **리빌드 진행 중**입니다. 로컬에서 시연되던 프로토타입을 실제로 운영되는 서비스로 만드는 것이 목표이고, 자동화·평가·인증·배포를 새로 채우고 있습니다.

## 저장소 구조

세 개로 나뉘어 있던 저장소를 커밋 히스토리를 유지한 채 하나로 합쳤습니다.

| 디렉터리 | 스택 | 역할 |
| --- | --- | --- |
| `frontend/` | Vite + React 18 (TypeScript) | 온보딩, 대시보드, 토론·트렌드리포트 화면 |
| `backend/` | FastAPI + LangGraph | 오케스트레이터, 토론·시뮬레이션·트렌드리포트 에이전트 |
| `data-pipeline/` | Python (크롤러 + Pinecone RAG) | 리포트·뉴스·공시 수집, 청킹·임베딩, 검색 |

각 디렉터리의 `README.md`에 실행 방법이, `.env.example`에 필요한 환경변수가 있습니다.

## 시작하기

```bash
git clone https://github.com/ant-secretariat/ant-secretariat.git
cd ant-secretariat

# 프론트엔드
cd frontend && npm install && npm run dev

# 백엔드 (Python 3.11+)
cd backend && pip install -r requirements.txt && uvicorn main:app --reload

# 데이터 파이프라인
cd data-pipeline && pip install -r requirements.txt
```

> `backend/requirements.txt`는 아직 `-e ../ant-secretariat-data-pipeline` 상대경로로 data-pipeline을 참조합니다. 모노레포 구조에 맞춰 정리하는 작업이 리빌드 항목 6.2입니다.

## 기여 방법

- `main`은 보호되어 있습니다. `feature/<작업>` 브랜치에서 작업하고 PR로 올려주세요.
- PR은 팀원 1명 이상의 승인이 필요합니다.
- 작업 단위와 우선순위는 팀 노션의 **로드맵 백로그**를 따릅니다.
- 프롬프트·청킹·모델을 바꾸는 변경은 같은 평가셋으로 이전 버전과 비교한 수치를 PR에 적어주세요.

## 팀 내부 문서

접근 권한이 있는 팀원만 열 수 있습니다.

- 리빌드 로드맵 v2 — 항목별 업계 사례·디벨롭 방향, 직무 JD 분석: https://claude.ai/artifact/CADp3pwAnNfpC34tdx9ayt
- 팀 노션 (백로그·회의록·의사결정·실험 로그): https://app.notion.com/p/3df1fad9262e8130a679fdeb0df068dd

## 팀

리빌드 참여 (알파벳순)
- [@kkamret](https://github.com/kkamret)
- [@nasuzz](https://github.com/nasuzz)
- [@taeeunni](https://github.com/taeeunni)

## 출처와 원 기여자

이 저장소는 [tobigs-conference](https://github.com/tobigs-conference) 조직에서 진행된 팀 프로젝트를 이어받아 리빌드한 것입니다. 원 저장소의 커밋 히스토리를 그대로 가져왔습니다. 따라서 **커밋 목록과 Contributors에는 리빌드에 참여하지 않는 원 팀원도 함께 표시됩니다.** 그분들이 작성한 코드가 실제로 이 저장소에 포함돼 있기 때문이며, 리빌드 이후의 작업은 위 팀 목록의 3인이 진행합니다.

원 저장소
- [ant-secretariat-frontend](https://github.com/tobigs-conference/ant-secretariat-frontend)
- [ant-secretariat-backend](https://github.com/tobigs-conference/ant-secretariat-backend)
- [ant-secretariat-data-pipeline](https://github.com/tobigs-conference/ant-secretariat-data-pipeline)

원 기여자 (알파벳순)
- [@boogiewooki02](https://github.com/boogiewooki02)
- [@hyeyoon04](https://github.com/hyeyoon04)
- [@kkamret](https://github.com/kkamret)
- [@nasuzz](https://github.com/nasuzz)
- [@taeeunni](https://github.com/taeeunni)

## 라이선스

아직 정해지지 않았습니다. 원 저장소에 라이선스 파일이 없어 저작권이 각 기여자에게 있으므로, 원 팀과 합의한 뒤 `LICENSE` 파일을 추가할 예정입니다. 그 전까지는 코드의 재사용·배포 권한이 부여되지 않은 상태입니다.
