# ai/ — B/L Copilot AI 서비스

기획안의 **F1~F7** 을 그대로 폴더 이름으로 쓴다. "이 기능 코드가 어디 있나"를
문서 없이 `ls` 만으로 답할 수 있게 하는 것이 이 배치의 목적이다.

## 폴더 지도

| 폴더 | 기능 | 엔드포인트 |
|---|---|---|
| `api/` | FastAPI 진입점 (무상태 순수 함수를 HTTP 로 노출) | `/health` 외 전부 |
| `f1_intake/` | **F1** 서류 인테이크·초안 작성 (PDF 좌표 파싱 · PaddleOCR · 엑셀 · 이메일) | `/extract`, `/extract/pdf`, `/extract/excel`, `/extract/email`, `/extract/label` |
| `f2_terms/` | **F2** 표준 용어 교정 (6단계 캐스케이드 · 카탈로그 `std-2026.3`) | `/normalize`, `/normalize/apply`, `/normalize/reject`, `/glossary`, `/glossary/validate` |
| `f3_rules/` | **F3 계층 A** 룰엔진 (UCP600·ISBP·MT700 조문 코드화, 단일 29 + 서류 간 10) | `/verify`, `/verify/cross`, `/rules`, `/lc/mt700` |
| `f3_model/` | **F3 계층 B** XGBoost 하자 확률 — **서비스 추론 전용** (확률·임계값·판정만 반환) | `/verify` 응답에 포함 |
| `f3_research/` | **F3 계층 B** 논문 실험 트리 — 합성 데이터·학습·보정·SHAP. **비배포 · 로컬 전용(git 제외)** | 없음 |
| `f4_report/` | **F4** 선제 대응 분석 리포트 (수치는 템플릿, 서술만 LLM) + PDF · 공유 링크 | `/report`, `/report/pdf`, `/report/share`, `/report/shared/{token}` |
| `f5_impact/` | **F5** 정정 영향분석 — 전용 백엔드 모듈 없음 (`f5_impact/README.md` 참고) | 없음 |
| `f6_reality/` | **F6** 항만 운항 현실 대조 경보 (울산항 VTS 어댑터 + 결정론 룰 6건) | `/reality/check`, `/reality/rules` |
| `f7_explain/` | **F7** AI 판정 설명 — 백엔드 미구현 (`f7_explain/README.md` 참고) | 없음 |
| `tests/` | 서비스 테스트 (`f3_research` 테스트는 그 안에 따로 있다) | — |
| `archive_bl_model_v2/` | 대체된 초기 OCR 프로토타입. **비배포** — `f3_research` 가 실측 추출 정확도 근거로 `reports_eval_2000/` 만 읽는다 | 없음 |

`f3_research` 와 `archive_bl_model_v2` 는 `.dockerignore` 로 이미지에서 빠진다.
`f3_research` 는 논문용 실험 코드라 루트 `.gitignore` 로 git 에서도 제외한다 —
저장소를 새로 받으면 이 폴더가 없으니, 필요한 사람은 따로 받아 `ai/f3_research/` 에 둔다.
서비스 학습 모델은 `f3_model/artifacts/` 에 있어 이 폴더 없이도 서비스는 돈다.

## 임포트 규칙

**`ai/` 가 임포트 루트다.** F 모듈은 전부 최상위 이름으로 임포트한다 —
중첩 패키지가 아니다.

```python
from f1_intake import IntakePipeline
from f3_rules.types import LCTerms
from f4_report import build_report
```

`ai/` 를 `sys.path` 에 넣는 곳은 세 군데다: `Dockerfile`(`WORKDIR /app`),
`ai/pytest.ini`(`pythonpath = .`), 저장소 루트 `pyproject.toml`
(`pythonpath = ["ai"]`). 셋 중 하나만 고치면 나머지 두 경로에서 임포트가 깨진다.

## 실행

```bash
# 서비스 (개발)
cd ai && uvicorn api.main:app --reload --port 5000

# 서비스 테스트
cd ai && pytest -q

# 논문 실험 트리 테스트 — 로컬에 f3_research 가 있을 때만 (ML 의존성 필요: uv sync --extra ml)
cd ai && pytest f3_research/tests -q

# 점검 스크립트
cd ai && python -m api_check        # 전 엔드포인트 1회 호출
cd ai && python -m acceptance       # 수용 기준 실측
cd ai && python -m review_sheet     # 조문 인용 검토표
```

`f3_research` 는 저장소 루트에서 `pytest ai/f3_research/tests` 로도 돌지만,
`ai/pytest.ini` 가 rootdir 로 잡히므로 결국 같은 임포트 루트를 쓴다.

## Dockerfile 이 여기 있는 이유

`ai/Dockerfile` 은 이 폴더만 빌드 컨텍스트로 쓴다(`build: ./ai`). 게이트웨이는
`pyproject.toml`·`uv.lock`·`src/` 가 다 필요해 저장소 루트를 컨텍스트로 써야
하므로 `infra/docker/gateway.Dockerfile` 에 따로 있다. 두 Dockerfile 이 서로
다른 곳에 있는 건 컨텍스트 범위가 다르기 때문이다.
