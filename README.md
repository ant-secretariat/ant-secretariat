<div align="center">
  <img src="docs/brand/app-icon-192.png" alt="개미비서단 앱 아이콘" width="120" height="120" />
  <h3>개미비서단 · ant-secretariat</h3>
  <p>애널리스트 리포트를 근거로 강세·약세 에이전트가 토론하고, 그 결론을 가격 분포로 보여주는 금융 AI 서비스</p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="Python 3.11" />
    <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/LangGraph-Orchestration-1C3C3C?logo=langchain&logoColor=white" alt="LangGraph" />
    <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=000000" alt="React 18" />
    <img src="https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white" alt="Vite" />
    <img src="https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white" alt="TypeScript 5" />
    <img src="https://img.shields.io/badge/Pinecone-Vector_DB-000000?logo=pinecone&logoColor=white" alt="Pinecone" />
    <img src="https://img.shields.io/badge/Upstage-Solar-7C3AED" alt="Upstage Solar" />
  </p>
</div>

개인 투자자가 종목을 판단할 때 필요한 근거를 한곳에 모아주는 서비스입니다. 증권사 리포트를 수집해 검색 가능한 형태로 쌓고, 강세(Bull)·약세(Bear) 에이전트가 같은 근거를 두고 토론한 뒤 판정 에이전트(Judge)가 정리합니다. 토론에서 나온 리스크는 몬테카를로 시뮬레이션의 입력이 되어 30일 가격 분포로 이어집니다.

원래 세 개로 나뉘어 있던 저장소(frontend / backend / data-pipeline)를 커밋 히스토리를 유지한 채 하나로 합친 **리빌드 저장소**입니다. 로컬에서 시연되던 프로토타입을 실제로 운영되는 서비스로 만드는 것이 목표이고, 자동화·평가·인증·배포를 새로 채우는 중입니다.

---

## 목차

- [주요 기능](#주요-기능)
- [빠른 시작](#빠른-시작)
- [환경변수](#환경변수)
- [기술 스택](#기술-스택)
- [디렉터리 구조](#디렉터리-구조)
- [서비스 구성과 데이터 흐름](#서비스-구성과-데이터-흐름)
- [리빌드 진행 방향](#리빌드-진행-방향)
- [팀 소개](#팀-소개)
- [개발 명령어](#개발-명령어)
- [기본 작업 흐름](#기본-작업-흐름)
- [출처와 원 기여자](#출처와-원-기여자)
- [라이선스](#라이선스)

---

## 주요 기능

- **온보딩 투자성향 진단** — 투자권유준칙 기반 문항으로 성향 점수를 산출하고 결과를 대시보드에 반영
- **트렌드리포트** — 수집한 리포트를 검색해 종목·섹터 단위 카드로 요약
- **토론형 분석** — Bull / Bear / Judge 에이전트가 같은 근거 위에서 상반된 해석을 제시
- **가격 시뮬레이션** — 토론에서 추출한 리스크 요인을 반영해 30일 누적 수익률 분포를 몬테카를로로 추정
- **리서치 수집 파이프라인** — 네이버 리서치·KIRS 리포트 수집, 3중 중복 제거, 청킹·임베딩 후 벡터 검색

현재 단계에서 솔직히 적어둘 부분이 있습니다. 로그인은 데모 계정이고, 토론은 3번의 단발 호출을 이어 붙인 구조이며, 결과는 폴링으로 받아옵니다. 뉴스·공시·거시지표 수집기는 코드만 있고 기본값이 꺼져 있습니다. 이 항목들이 리빌드 대상입니다.

---

## 빠른 시작

### 1. 저장소 클론

```bash
git clone https://github.com/ant-secretariat/ant-secretariat.git
cd ant-secretariat
```

### 2. 데이터 파이프라인 (Python 3.11 이상)

```bash
cd data-pipeline
pip install -r requirements.txt
cp .env.example .env
```

### 3. 백엔드

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload      # http://localhost:8000
```

> `backend/requirements.txt`는 아직 `-e ../ant-secretariat-data-pipeline` 상대경로로 data-pipeline을 참조합니다. 모노레포 구조에서는 경로가 맞지 않으므로, 당분간은 `pip install -e ../data-pipeline`으로 설치해 주세요. 워크스페이스 정리는 리빌드 항목 6.2입니다.

### 4. 프론트엔드 (Node.js 18 이상)

```bash
cd frontend
npm install
cp .env.example .env
npm run dev                    # http://localhost:5173
```

---

## 환경변수

값은 각 디렉터리의 `.env.example`을 복사해 채웁니다. 실제 키는 저장소에 커밋하지 않고, 배포 환경에서는 GitHub Actions 또는 호스팅 서비스의 시크릿으로만 관리합니다.

| 변수 | 위치 | 용도 | 없으면 |
| --- | --- | --- | --- |
| `UPSTAGE_API_KEY` | backend, data-pipeline | Solar LLM 호출, 임베딩 생성 | 토론·요약·임베딩 불가 |
| `PINECONE_API_KEY` | backend, data-pipeline | 벡터 검색 | 로컬 벡터 DB로 자동 대체 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | data-pipeline | 뉴스 수집 | 뉴스 수집 비활성 |
| `DART_API_KEY` | data-pipeline | 전자공시 수집 | 공시 수집 비활성 |
| `ECOS_API_KEY` | data-pipeline | 한국은행 거시지표 | 거시지표 수집 비활성 |
| `VITE_API_BASE_URL` | frontend | 백엔드 주소 | 로컬 기본값 사용 |

---

## 기술 스택

| 영역 | 기술 | 용도 |
| --- | --- | --- |
| 프론트엔드 | React 18, Vite, TypeScript 5 | 온보딩·대시보드·토론 화면 |
| 백엔드 | FastAPI, LangGraph | API, 에이전트 오케스트레이션 |
| LLM | Upstage Solar | 토론·요약·리스크 분류 |
| 검색 | Pinecone, solar-embedding | 리포트 청크 임베딩과 검색 |
| 수집 | requests, BeautifulSoup, APScheduler | 리포트·뉴스·공시 크롤링 |
| 시뮬레이션 | PyTorch (LSTM), NumPy | 수익률 분포 학습과 몬테카를로 |
| 저장소 | SQLite | 리포트 원본, 작업 상태 |

---

## 디렉터리 구조

```text
ant-secretariat/
├── frontend/               # Vite + React SPA
│   └── src/pages/          # 로그인, 온보딩, 대시보드, 토론, 트렌드리포트
├── backend/                # FastAPI 서버
│   ├── agents/             # debate, simulation, trend_report, insight
│   ├── orchestrator/       # LangGraph 라우팅
│   ├── onboarding/         # 투자성향 스코어링 (순수 함수)
│   ├── api/                # 사용자·작업 엔드포인트
│   └── tests/              # pytest
├── data-pipeline/
│   ├── crawling/           # 크롤러, 콜렉터, 스케줄러, SQLite 스키마
│   └── processing/         # 청킹, 임베딩, 벡터 저장·검색
├── docs/
│   ├── brand/              # 심볼·아이콘 등 브랜드 에셋
│   └── CONVENTIONS.md      # PR·이슈·브랜치·커밋 규칙
└── .github/                # PR·이슈 템플릿, 라벨, CODEOWNERS
```

---

## 서비스 구성과 데이터 흐름

```text
증권사 리포트(네이버·KIRS) → 크롤러 수집·중복 제거 → SQLite 원본 저장
   → 청킹·임베딩 → 벡터 검색(Pinecone)
   → 트렌드리포트 / Bull·Bear·Judge 토론
   → 토론에서 추출한 리스크 → 몬테카를로 시뮬레이션 → 가격 분포
```

- 수집한 리포트 원본(PDF)과 로컬 DB는 저장소에 커밋하지 않습니다.
- 생성된 문장은 검색된 청크를 근거로 삼고, 근거 없는 수치를 단정적으로 쓰지 않습니다.
- 서비스는 투자 정보를 정리해 보여줄 뿐 투자 권유나 매매 판단을 대신하지 않습니다.
- 크롤러는 `robots.txt`와 요청 간 지연을 지킵니다.

---

## 리빌드 진행 방향

8개 카테고리, 32개 항목으로 정리해 두었습니다. 우선순위는 팀 백로그에서 관리합니다.

| 카테고리 | 핵심 과제 |
| --- | --- |
| 01 데이터 인프라 | 크롤러 무중단 실행, 실패 알림, 수집 소스 활성화 |
| 02 RAG 재구축 | 표·섹션 구조를 반영한 청킹, 하이브리드 검색과 리랭킹 |
| 03 에이전트 | 멀티턴 토론 그래프, 구조화 출력 강제, 스트리밍 전달 |
| 04 평가지표 | 검색 품질(Recall@k·nDCG), 사실성, 토론 품질 평가 |
| 05 UI/UX | 디자인 토큰, 실제 로그인 플로우, 접근성 |
| 06 배포·인프라 | 컨테이너 패키징, CI/CD, 프리뷰 배포 |
| 07 보안·인증 | 인증·인가, CORS 제한, 호출량 제한 |
| 08 관측성·QA | 구조화 로깅, LLM 비용·지연 추적, 테스트 |

---

## 팀 소개

| 팀원 | 담당 영역 |
| --- | --- |
| [@kkamret](https://github.com/kkamret) | 킥오프에서 확정 |
| [@nasuzz](https://github.com/nasuzz) | 킥오프에서 확정 |
| [@taeeunni](https://github.com/taeeunni) | 킥오프에서 확정 |

---

## 개발 명령어

```bash
# 프론트엔드
npm run dev        # 개발 서버
npm run build      # 타입 검사 + 프로덕션 빌드
npm run preview    # 빌드 결과 확인

# 백엔드
uvicorn main:app --reload
pytest             # 테스트

# 데이터 파이프라인
python -m crawling.main          # 수집 1회 실행
python -m processing.run_pipeline # 청킹·임베딩
```

PR을 올리기 전에 변경한 영역의 빌드와 테스트를 실행하고, 결과를 PR 본문에 적습니다.

---

## 기본 작업 흐름

1. 작업 범위를 설명하는 이슈를 만듭니다.
2. `main`이 아닌 작업 브랜치에서 개발합니다.
3. 검색·프롬프트·모델을 바꾸는 변경은 같은 평가셋으로 이전 버전과 비교한 수치를 함께 남깁니다.
4. 테스트와 빌드를 실행한 뒤 PR을 엽니다.
5. 팀원 1명의 리뷰를 받고 병합합니다.

브랜치·커밋·이슈·PR 규칙은 [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md)에 정리되어 있습니다.

---

## 출처와 원 기여자

이 저장소는 [tobigs-conference](https://github.com/tobigs-conference) 조직에서 진행된 팀 프로젝트를 이어받아 리빌드한 것입니다. 원 저장소의 커밋 히스토리를 그대로 가져왔기 때문에, **커밋 목록과 Contributors에는 리빌드에 참여하지 않는 원 팀원도 함께 표시됩니다.** 그분들이 작성한 코드가 실제로 포함되어 있기 때문이며, 리빌드 이후의 작업은 위 팀 목록의 3인이 진행합니다.

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

---

## 라이선스

아직 정해지지 않았습니다. 원 저장소에 라이선스 파일이 없어 저작권이 각 기여자에게 있으므로, 원 팀과 합의한 뒤 `LICENSE` 파일을 추가할 예정입니다. 그 전까지는 코드의 재사용·배포 권한이 부여되지 않은 상태입니다.
