# Smart_e-BL — B/L Copilot

선하증권(B/L) 등 무역서류의 **내용 정확성**과 **운항 현실 정합성**을 제출 이전
단계에서 검증하는 AI 지원 시스템.

## 최상위 구조

| 경로 | 내용 |
|---|---|
| `ai/` | **AI 서비스 (F1~F7)** — FastAPI, 무상태 순수 함수. 폴더 지도는 `ai/README.md` |
| `src/smart_e_bl/` | **게이트웨이** — FastAPI, 선적·서류·필드값 영속화와 업로드 안전장치. 상태를 갖는 쪽은 여기뿐이다 |
| `frontend/` | React 19 + Vite. 화면 단위(S0~S7)로 나뉜다 — 규칙은 `frontend/CLAUDE.md` |
| `migrations/` | PostgreSQL 스키마 (SQL 10파일 + Alembic) |
| `infra/` | `docker/gateway.Dockerfile` · AWS IAM 정책 · postgres initdb |
| `docs/` | (로컬 전용·git 제외) 기획안·설계서·QA 기록·시연 샘플 |
| `scripts/` | `demo-check.sh`(시연 전 점검) · `scenario-check.py` |
| `eval/` | (로컬 전용·git 제외) 논문용 근거 검증 실험 |
| `data/documents/` | (실행 시 생성·git 제외) Docker 밖에서 게이트웨이를 띄울 때의 업로드 저장소. Docker 에서는 `document-storage` 볼륨을 쓴다 |

AI 서비스와 게이트웨이는 **축이 다르다.** `ai/` 는 기능(F1~F7)으로 나뉘고,
게이트웨이는 계층(api·models·worker·storage)으로 나뉜다. AI 서비스가 무상태 순수
함수이고 영속화는 게이트웨이가 전담하기 때문이다.

## 실행

```bash
docker compose up -d --build          # postgres · ai-service · api · worker · frontend
```

```bash
cd ai && pytest -q                    # AI 서비스 테스트
uv run pytest src/smart_e_bl/tests/   # 게이트웨이 테스트 (Postgres 필요)
cd frontend && npm test && npm run build
```

## 정리 이력 (2026-09-06)

AI 코드가 `backend/aiService/` · `ai/defect_model/` · `ai_sample/` 세 곳에
흩어져 있어 F1~F7 기준으로 `ai/` 한 곳에 모았다.

| 이전 | 현재 |
|---|---|
| `backend/aiService/ocr/` | `ai/f1_intake/` |
| `backend/aiService/terms/` | `ai/f2_terms/` |
| `backend/aiService/ruleEngine/` | `ai/f3_rules/` |
| `backend/aiService/mlModel/` | `ai/f3_model/` |
| `backend/aiService/report/` | `ai/f4_report/` |
| `backend/aiService/reality/` | `ai/f6_reality/` |
| `backend/aiService/{api,tests,Dockerfile,…}` | `ai/{api,tests,Dockerfile,…}` |
| `ai/defect_model/` | `ai/f3_research/` |
| `ai_sample/B_L_model_v2/` | `ai/archive_bl_model_v2/` |

임포트도 같이 바뀌었다 — `from ruleEngine.types import ...` → `from
f3_rules.types import ...`. 자세한 규칙은 `ai/README.md` "임포트 규칙".

**삭제:** `backend/api/`, `backend/blockchain/` — 초기 기획의 Node/Express
게이트웨이·Hardhat 스캐폴드였으나 코드 없이 `.gitkeep` 과 `.env.example` 만
남아 있었고, 실제 구현은 각각 `src/smart_e_bl/`(Python/FastAPI)와
`ai/f3_rules/`(룰엔진)로 대체되었다. 두 디렉터리가 사라지면서 `backend/` 도
없어졌다. 복원이 필요하면 커밋 `d8fd930` 시점에 있다.

`docs/` 안의 날짜가 박힌 기록(`테스트결과_및_개선항목_2026-08-19.md`,
`QA_테스트케이스_2026-08-19.md`, `DB연동_작업정리_2026-08-19.md`)은 그 시점의
스냅샷이라 경로를 고치지 않았다. 거기 적힌 `backend/aiService/...` 는 위 표로
읽으면 된다.
