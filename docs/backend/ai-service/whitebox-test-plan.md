# aiService 화이트박스 테스트 설계표

## 1. 방법론

- 도구: `pytest` + `pytest-cov`(`coverage.py`). 구문(statement)·분기(branch) 커버리지를 실측한다.
- 기법: 조건/분기 커버리지(모든 `if`/`try-except` 분기를 최소 1회씩), 경계값(빈 리스트/None/0 표본), 오류 경로(예외가 실제로 발생하는 입력)를 우선한다. 이미 100%에 가까운 모듈은 기존 테스트가 이미 이 기준을 충족하므로 재작성하지 않는다.
- 실행:
  ```bash
  python -m pytest -q --cov=. --cov-report=term-missing --cov-config=/dev/null
  ```

## 2. 기준선(변경 전) vs 현재

선택 의존성(`xgboost`, `numpy`, `openpyxl`, `PyMuPDF`, `reportlab` 등)이 로컬 가상환경에 없어 관련 테스트 5개 파일이 전부 스킵되고 있었다. `requirements.txt` 그대로 설치하니 스킵이 사라지고 전체 커버리지가 80% → 92%로 올랐다 — 이건 새 테스트를 짜서 얻은 수치가 아니라, **원래 있던 테스트를 실행 가능하게 만든** 결과다.

이번에 실제로 새로 작성한 것은 아래 두 모듈이다. 나머지는 이미 기존 테스트가 분기 대부분을 덮고 있어 백지 상태가 아니었다.

| 모듈 | 이전 | 이후 | 비고 |
|---|---|---|---|
| `reality/adapter.py` | 61% | **100%** | F6에서 새로 만든 모듈, 원래 테스트가 없었다 |
| `ocr/preprocessor.py` | 28% | **97%** | 실 OCR 파이프라인이 쓰는데 테스트 파일 자체가 없었다 |

전체 프로젝트 커버리지(부록 A)는 92%로, 나머지 격차는 아래 3절에서 다룬다.

## 3. 상세 설계표

### 3.1 `reality/adapter.py` — `tests/test_reality_adapter.py`

| ID | 대상 | 분기/조건 | 입력 | 기대 결과 |
|---|---|---|---|---|
| A1 | `FixtureSource.fetch` | 정상 경로 | 유효한 JSON 리스트 파일 | 파싱된 리스트 반환 |
| A2 | `FixtureSource.fetch` | `OSError` | 존재하지 않는 경로 | `EventSourceError` |
| A3 | `FixtureSource.fetch` | `json.JSONDecodeError` | 손상된 JSON | `EventSourceError` |
| A4 | `FixtureSource.fetch` | `isinstance(data, list)` 거짓 | JSON 객체(dict) | `EventSourceError` |
| A5 | `FixtureSource.__init__` | 경로 미지정 → 환경변수 | `REALITY_FIXTURE_PATH` 설정 | 그 경로를 `self.path`로 사용 |
| A6 | `UlsanVtsSource.fetch` | `base_url` 없음 | 빈 문자열 | 즉시 `EventSourceError` (네트워크 호출 없이) |
| A7 | `UlsanVtsSource.fetch` | `service_key` 없음 | 빈 문자열 | 즉시 `EventSourceError` |
| A8 | `UlsanVtsSource.fetch` | `service_key == "changeme"` | 기본값 그대로 | 즉시 `EventSourceError` |
| A9 | `UlsanVtsSource.fetch` | `URLError` | `urlopen`이 예외 | `EventSourceError`로 번역 |
| A10 | `UlsanVtsSource.fetch` | 응답이 JSON 아님 | `b"not json"` | `EventSourceError` |
| A11 | `UlsanVtsSource.fetch` | `items`가 리스트 아님 | `items: "not-a-list"` | `EventSourceError` |
| A12 | `UlsanVtsSource.fetch` | 정상 경로 | 유효한 응답 body | `items` 리스트 반환 |
| A13 | `UlsanVtsSource.fetch` | **회귀** — serviceKey 이중 인코딩 | `%2B`/`%3D%3D` 포함 키 | URL에 `%25`가 나타나면 안 됨(이번 세션에 발견·수정한 버그) |
| A14 | `UlsanVtsSource.__init__` | 생성자 인자 vs 환경변수 우선순위 | 둘 다 설정 | 생성자 인자가 이긴다 |
| A15 | `source_from_env` | 기본값 | 미설정 | `FixtureSource` |
| A16 | `source_from_env` | 대소문자/공백 무관 | `" ULSAN "` | `UlsanVtsSource` |
| A17 | `source_from_env` | 오타/미지원 값 | `"typo"` | `FixtureSource`로 폴백 |
| A18 | `UlsanVtsSource.fetch` | `call_sign` 없음 | 미지정 | 네트워크 호출 전에 즉시 `EventSourceError`(실측: callsgn 없이는 게이트웨이가 HTTP_ERROR) |
| A19 | `UlsanVtsSource.fetch` | 헤더 `resultCode != "00"` | `resultCode: "10"` | `EventSourceError` |
| A20 | `UlsanVtsSource.fetch` | 최상위 `resultCode: "030"`(결과 없음) | `response` 봉투 없이 최상위 필드만 | 오류가 아니라 빈 리스트 |
| A21 | `UlsanVtsSource.fetch` | 게이트웨이 오류 봉투(`OpenAPI_ServiceResponse.cmmMsgHeader`) | 필수 파라미터 누락 시 실측 응답 | `EventSourceError` |
| A22 | `UlsanVtsSource.fetch` | 정상 응답, 단건 | `body.items.item`이 dict(리스트 아님) | `[item]`으로 감싸 리스트 반환 |
| A23 | `UlsanVtsSource.fetch` | `items`가 빈 문자열 | `items: ""` | 빈 리스트 |
| A24 | `UlsanVtsSource.fetch` | 알 수 없는 봉투 모양 | 위 세 형태 어디에도 안 걸림 | `EventSourceError` |
| A25 | `UlsanVtsSource.fetch` | `year` 파라미터 전달 | `year="2025"` | URL에 `ptentVtsYr=2025` 실림 |
| A26 | `resolve_call_sign` | 선명 빈 문자열/공백/`None` | `""`/`"  "`/`None` | 즉시 `None`(네트워크 호출 없이) |
| A27 | `resolve_call_sign` | `service_key` 없음/`"changeme"` | 빈 문자열 / `"changeme"` | 즉시 `None` |
| A28 | `resolve_call_sign` | 영문 선명 정확일치 1건 | `"OSUNG"`, 부분일치 노이즈(`"NO.2000 BOSUNG"`) 섞인 응답 | 정확일치 항목의 `clsgn` 반환 |
| A29 | `resolve_call_sign` | 국문 선명 정확일치 1건 | `"오성호"` | `clsgn` 반환 |
| A30 | `resolve_call_sign` | 동명이선 — 정확일치 2건 이상 | 같은 선명, 다른 `clsgn` 2건 | `None`(하나로 못 좁힘) |
| A31 | `resolve_call_sign` | 부분일치만 있고 정확일치 없음 | `"OSUNG"` 검색에 `"NO.2000 BOSUNG"`만 옴 | `None` |
| A32 | `resolve_call_sign` | 헤더 `resultCode != "00"` | `resultCode: "99"` | `None`(예외 아님) |
| A33 | `resolve_call_sign` | `URLError` | `urlopen`이 예외 | `None` |
| A34 | `resolve_call_sign` | XML 파싱 실패 | `b"not xml"` | `None` |

결과: 34개 케이스, 100% 통과, 분기 커버리지 100%.

**세션 중 발견한 버그들**:
1. **(A13)** `fetch()`가 이미 퍼센트 인코딩된 공공데이터포털 "Encoding" 키를 `urlencode()`에 다시 태워 `%2B → %252B`로 이중 인코딩하고 있었다. `serviceKey`를 인코딩 없이 직접 붙이는 방식으로 고쳤다.
2. **엔드포인트 경로 누락**: `.env`의 `ULSAN_VTS_BASE_URL`이 서비스 루트(`.../VslNvgtInfoService`)까지만 있고 오퍼레이션명이 빠져 있었다. 사용자가 `docs/endpoint screen shot.png`로 공유한 API 문서에서 `/getVtsBaseVslNvgtInfo`를 확인해 채웠다.
3. **쿼리 파라미터명 오류**: JSON 응답을 받으려면 `resultType=json`이어야 하는데 코드는 `type=json`을 보내고 있었다 — 문서에 없던 값이라 이전 세션엔 확인할 방법이 없었다.
4. **필수 파라미터 누락**: 실측 결과 `callsgn`+`ptentVtsYr` 없이는 항상 `HTTP_ERROR`(reasonCode 04)가 난다 — 전체 목록 조회를 지원하지 않는다. `RealityEngine.fetch_records()`가 `call_sign`/`year`를 받아 어댑터로 넘기도록 시그니처를 바꿨고(`engine.py`, `api/main.py`의 `/reality/check` 호출부), 실 소스는 `call_sign` 없이는 즉시 `EventSourceError`를 낸다 — 이전엔 파라미터 없이 호출해 빈 결과를 "경보 없음"으로 잘못 읽을 수 있었다.
5. **응답 봉투 파싱 오류**: 정상 응답은 `body.items`가 아니라 `body.items.item`(단건이면 dict, 다건이면 list)이고, 결과 없음은 `response` 봉투 자체 없이 최상위 `{"resultCode":"030"}`로, 파라미터 오류는 `OpenAPI_ServiceResponse.cmmMsgHeader`로 온다 — 세 가지 모양을 다 확인하지 않으면 오류를 "0건"으로 삼키거나 정상 응답을 "형식 오류"로 거부한다. `_extract_items()`로 통합했다.

이 다섯 개 모두 실 API에 실제로 호출해 보지 않고는 발견할 수 없는 결함이라, 이번에 라이브 스모크 테스트로 잡고 회귀 테스트(A18-A25)를 남겼다.

**`resolve_call_sign` (A26-A34) — 선명만으로 실 API 조회 지원**: 울산항 VTS 는 `callsgn` 없이 호출이 안 되는데(A18) B/L 엔 콜사인이 없다(`f6-customs-reality-check.md` §3.2). 사용자가 공유한 해양수산부_선박제원정보 API(`docs/스크린샷 2026-08-19 오후 6.24.44.png`, `.55.png`) 문서로 선명 → 콜사인 역방향 조회를 추가했다. 라이브 검증에서 확인한 것:
- `vsslNm` 검색은 부분일치다 — `"OSUNG"` 검색에 `"NO.2000 BOSUNG"`도 걸린다. `vsslEngNm`/`vsslKorNm` 정확일치로 클라이언트에서 걸러야 한다.
- **동명이선이 실측으로 실재한다**: `"오성호"`로 검색하면 정확일치가 2건 나온다(석유제품 운반선 `clsgn=150040`과 무관한 어선 `clsgn=9506158`) — A30 은 가상 케이스가 아니라 실제로 재현된 시나리오다. 이 경우 하나로 못 좁혀지므로 `None`.
- 기존 `ULSAN_VTS_SERVICE_KEY`(울산항 VTS 용으로 발급된 키)가 이 API에도 그대로 통했다 — 공공데이터포털 일반인증키가 계정 단위임을 실측으로 재확인.
- `api/main.py`의 `/reality/check`는 `call_sign` 이 없고 소스가 fixture 가 아니면 fetch 전에 이걸 먼저 시도하고, 실패하면(동명이선·미등록 등) 네트워크를 타지 않고 바로 `records=[]`로 떨어뜨린다 — §1 무상태 원칙과 같은 이유로, 못 찾은 건 오류(503)가 아니라 정상 미매칭(200)이어야 하기 때문이다.

### 3.2 `ocr/preprocessor.py` — `tests/test_preprocessor.py`

| ID | 대상 | 분기/조건 | 입력 | 기대 결과 |
|---|---|---|---|---|
| P1 | `_load` | 파일 없음 | 존재하지 않는 경로 | `FileNotFoundError` |
| P2 | `_load` | 정상 | 실제 이미지 파일 | `ndarray` |
| P3 | `_to_grayscale` | 3채널 | BGR 이미지 | 2차원(그레이스케일)로 변환 |
| P4 | `_to_grayscale` | 이미 2차원 | 그레이스케일 입력 | 그대로 반환(같은 객체) |
| P5 | `_remove_noise` | 정상 | 임의 이미지 | 형태(shape) 보존 |
| P6 | `_binarize` | 정상 | 그레이스케일 | 픽셀 값이 {0, 255}만 |
| P7 | `_detect_skew_angle` | `lines is None` | 빈(직선 없는) 이미지 | 각도 0.0, `_deskew`가 원본 그대로 반환 |
| P8 | `_detect_skew_angle` | 직선 있음 | 여러 대각선 | 0이 아닌 각도 추정 |
| P9 | `_detect_skew_angle` | `x2 == x1`(수직선) → `continue` / `abs(angle) >= 45` → 필터 | 수직선 + 급경사선 + 완만한 선 혼합 | 완만한 선만 반영된 각도 |
| P10 | `_deskew` | 임계각(`0.5˚`) 미만 | 각도 0.1 (모킹) | 회전 보정 안 함, 원본 그대로 |
| P11 | `_deskew` | 임계각 이상 | 각도 5.0 (모킹) | 회전 보정 적용(픽셀이 달라짐) |
| P12 | `_normalize_resolution` | `w >= STANDARD_WIDTH` | 너비 1654 | 그대로(같은 객체) |
| P13 | `_normalize_resolution` | `w < STANDARD_WIDTH` | 너비 200 | `STANDARD_WIDTH`로 확대 |
| P14 | `process` | 전체 파이프라인 통합 | 합성 스캔 이미지 | 최종 너비 == `STANDARD_WIDTH` |
| P15 | `save` | 정상 | 임의 이미지 | 출력 파일 생성됨 |

결과: 15개 케이스, 100% 통과. 구문 97%(75건 중 미실행 2줄), 남은 미실행분은 `__init__`의 `except ImportError`(로컬에 `opencv-python`이 아예 없을 때만 타는 분기) — cv2가 설치된 CI/로컬에서는 재현 불가능하므로 의도적으로 제외.

## 4. 다루지 않은 격차와 그 이유

전체 범위(`aiService` 전체)를 훑되, 아래는 새 테스트를 추가하지 않았다 — 이유를 남긴다.

| 파일 | 커버리지 | 제외 사유 |
|---|---|---|
| `api_check.py` | 0% | `python -m api_check`로 수동 실행하는 스모크 스크립트다. `pytest`가 이 파일을 임포트하지 않아 0%로 잡히지만, 안에서 호출하는 모든 엔드포인트는 `test_api.py`/`test_reality_api.py`가 이미 더 정밀하게 검증한다. 이 파일 자체를 단위테스트하면 같은 걸 두 번 테스트하는 셈이라 스킵. |
| `acceptance.py`, `review_sheet.py` | 74%, 69% | 기획안 수용 기준 실측·조문 검토표를 만드는 리포트 생성 스크립트(CLI 진입점). 핵심 계산 로직은 이미 `test_acceptance.py`/`test_review_sheet.py`가 덮고, 남은 미실행분은 `__main__`의 출력 포맷팅/파일 저장 분기라 값이 낮다. |
| `terms/cascade.py` | 88%(686줄 중 84줄) | 파일이 커서 미실행 라인이 절대량으로 많아 보이지만 비율은 이미 높다. 남은 분기는 표준 사전 캐스케이드의 드문 폴백 조합(2개 이상의 동시 예외 조합)으로, 기존 `test_terms_cascade.py`(363개 테스트)가 이미 백지 상태가 아니다. |
| `mlModel/evaluate.py`, `mlModel/corpus.py` | 85%, 65% | 모델 성능 리포트 생성 CLI. `__main__` 분기·프린트 포맷팅이 미실행분의 대부분. |
| `report/llm_providers.py` | 76% | 외부 LLM 실호출 분기(Gemini/OpenAI 실제 네트워크 왕복)는 `conftest.py`가 스위트 전체에서 의도적으로 꺼 둔다(비용·지연 때문 — `_no_ambient_llm` 픽스처 주석 참고). |

이 파일들은 "테스트가 없다"가 아니라 "이미 있는 테스트가 핵심 분기를 덮고, 남은 미실행분은 CLI 출력부거나 의도적으로 끈 외부 호출부"라는 공통점이 있다. 여기까지 백지부터 설계표를 채우는 건 이번 요청의 실익 대비 비용이 크다고 판단해 제외했다 — 필요하면 개별 파일 단위로 추가 요청 바란다.

## 5. 실행 결과

```
python -m pytest -q --cov=. --cov-report=term-missing --cov-config=/dev/null
...
TOTAL   11594   881   92%
```

`tests/test_reality_adapter.py`(34, `resolve_call_sign` 9건 포함), `tests/test_preprocessor.py`(15) 포함, 전체 스위트 통과. 기존에 있던 5개 실패(`test_acceptance.py`, `test_extractor.py`의 OCR 축소 4건)는 선택 의존성을 설치하고 나니 함께 사라졌다 — 이번 화이트박스 작업과 무관한 환경 문제였다.
