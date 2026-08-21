# aiService — 설계 노트

> 기획안 6.2 백엔드: "Express 5(API 게이트웨이·인증·알림) + **FastAPI(AI 모듈군)**"

Express 게이트웨이(`:4000`)가 이 서비스(`:5000`)를 호출한다. 코드는 `aiService/api/` 에 있다.

이 문서는 **왜 이렇게 만들었는가**를 다룬다. 요청/응답 계약은 명세 문서에 있다.

| | 문서 |
|---|---|
| 공통 규약 (Base URL·에러 형식·상태 코드) · `/health` | [api-spec.md](api-spec.md) |
| F1 인테이크 — 추출 5건 | [f1-intake.md](f1-intake.md#api-명세) |
| F2 표준 용어 교정 — `/normalize` `/normalize/apply` `/normalize/reject` `/glossary` `/glossary/validate` | [f2-standard-terms.md](f2-standard-terms.md#api-명세) |
| F3 하자 예측 — `/rules` `/lc/mt700` `/verify` | [f3-defect-prediction.md](f3-defect-prediction.md#api-명세) |
| F4 리포트 — 리포트·공유 5건 | [f4-report.md](f4-report.md#api-명세) |

엔드포인트는 19건이다(F2 5건 추가). 목록의 정본은 `app.openapi()` 이며, 문서와 어긋나면 그쪽이 정답이다.

F2 의 5건은 화면으로 나누면 **S3 초안 편집기**(`/normalize`·`/normalize/apply`·`/normalize/reject`)와 **S11 설정**(`/glossary`·`/glossary/validate`) 둘이다. 앞의 셋이 한 벌인 것이 설계의 핵심이다 — 제안을 내는 경로와 값을 바꾸는 경로가 갈라져 있는 것 자체가 승인 게이트다(기획안 5.2 "자동 치환은 하지 않는다").

### L/C 원문은 `/extract/*` 가 아니다

`POST /lc/mt700`(MT700 전문 → L/C 조건)은 기획안 v2 5.1 이 **F1 입력 경로**로 적은 것이지만 추출 접두어 아래 두지 않았다. 위 "다섯 개의 추출 경로"가 성립하는 이유가 **응답 형태가 전부 같다**는 데 있기 때문이다 — 여섯 번째로 L/C 조건을 내는 경로를 끼우면 그 불변이 깨지고, S3 편집기가 경로마다 분기하게 된다.

구현도 `ocr/` 가 아니라 `ruleEngine/mt700.py` 에 있다. 산출물이 `LCTerms` 이고, 그걸 소유한 쪽이 룰엔진이다.

## 기획안 v2 의 API 경로와 다르다 (2026-08-11)

v2 는 5장 각 기능의 "연계" 항목에 API 경로를 못박았다 — `POST /api/v1/documents`, `GET /api/v1/jobs/{job_id}`, `POST /api/v1/shipments/{id}/verify`, `POST /api/v1/shipments/{id}/reports` 처럼 **선적(shipment) 자원 아래에 붙는 형태**다. 우리 경로(`/extract`, `/verify`, `/report`)는 그렇지 않다.

**바꾸지 않았다.** v2 의 경로는 `shipment_id` 로 서버에 저장된 상태를 지목하고 `job_id` 로 비동기 진행을 폴링하는 설계인데, 이 서비스는 **저장하지 않는다**(아래 절). 저장·비동기 큐·선적 식별자는 Express 게이트웨이의 책임이므로, 그 계약을 AI 모듈이 흉내 내면 두 곳이 같은 상태를 각자 관리하게 된다.

즉 **v2 5장의 경로는 게이트웨이가 프런트에 제공할 외부 계약**으로 읽고, 이 문서의 경로는 그 뒤에 있는 내부 호출로 둔다. 게이트웨이가 `/api/v1/shipments/{id}/verify` 를 받아 저장된 서류를 꺼내고, 이 서비스의 `/verify` 에 입력을 통째로 실어 보내는 구조다. **다만 이건 우리 쪽 판단이므로 게이트웨이 담당과 맞춰야 한다** — 비동기 `job_id` 를 누가 발급하는지가 특히 그렇다.

## 저장하지 않는다

이 서비스는 **상태를 갖지 않는다.** 저장 책임은 게이트웨이에 있다.

계획 단계에서는 여기에 저장소 포트(인터페이스 + 인메모리 구현)를 두려 했으나, 서비스 자체가 저장하지 않으면 포트가 필요 없다. 더 단순하고, AI 모듈이 스키마 변경에 묶이지 않는다. 저장소 추상화가 필요해지는 건 Express 계층이고 그건 이번 범위 밖이다.

결과적으로 스키마가 확정돼도 이 서비스 코드는 바뀌지 않는다.

이 원칙이 API 형태를 결정한다 — **조회·목록·삭제 엔드포인트가 하나도 없다.** 모든 요청이 입력을 통째로 싣고 온다.

## F2 도 저장하지 않는다

F2 는 이 서비스에서 **저장을 가장 많이 요구하는 기능**이다 — 사전 관리·승인 이력·영향 범위가 전부 상태다. 그런데 원칙은 위 절과 같으므로, 기획안 5.2 가 적은 API 를 그대로 만들 수 없는 자리가 둘 생긴다. 게이트웨이 담당이 "AI 모듈이 해 준다"고 믿지 않도록 여기 적는다.

**`POST /api/v1/normalize/{suggestion_id}/accept|reject` 를 그대로 못 만든다.** `{suggestion_id}` 로 서버에 저장된 제안을 지목하는 형태이기 때문이다. 대신 `POST /normalize/apply`·`/normalize/reject` 가 **제안 객체를 본문으로** 받는다. 게이트웨이가 id → 제안 조회를 맡고, 서버는 받은 재료에서 `suggestion_id` 를 재파생해 대조한다.

`suggestion_id` 는 저장 없이 결정론적으로 파생한다(사전 버전 · 캐스케이드 버전 · 자리 · 정규화한 원값 · 교정값 · 사전 항목 id · 단계 · 클래스의 해시). **HMAC 이 아니라 순수 해시다** — 목적이 위조 방지가 아니라 *같은 입력에 같은 이름*이라 `report/share.py` 의 서명키(프로세스마다 달라질 수 있다)를 쓰면 재현성이 깨진다.

**`POST /api/v1/glossary`(사전 등록)를 그대로 못 만든다.** 대신 `POST /glossary/validate` 가 **검증만** 한다. 저장·버전 관리는 게이트웨이 몫이다. 이 엔드포인트의 유일한 목적은 깨진 사전이 DB 에 들어가는 것을 막는 것이며, 표준 카탈로그와 **같은 검증기**를 태운다 — 다른 검증기를 쓰면 조직 사전이 더 느슨한 규칙으로 들어오고 그 차이는 조회 시점에야 드러난다.

게이트웨이가 떠안는 것을 한 표로 모은다. 자세한 근거는 [f2-standard-terms.md](f2-standard-terms.md) §무상태의 한계에 있다.

| 기획안 요구 | aiService 가 하는 것 | 게이트웨이가 해야 하는 것 |
|---|---|---|
| `POST /api/v1/glossary` 사전 등록 | `/glossary/validate` 로 **검증만** | 조직 사전 저장·버전 관리 |
| `/normalize/{id}/accept\|reject` | `/normalize/apply`·`/reject` 가 **본문으로** 받음 | id → 제안 조회 후 본문 전달 |
| 거절 사유 **기록** | `Correction` 을 만들어 반환 | 저장 |
| 영향 범위 = 선적 전체 | **요청에 실린 서류 안에서만** 계산 | **선적의 전 서류를 한 요청에 실을 것** |
| 판정 재현성 | 응답 `versions` 3종 + `ranker` | 저장 + 재현 시 되쏨 |
| LLM 판정 재현 | 후보 목록을 응답에 실음 | **후보 목록 전체를 저장** — 재호출로는 재현되지 않는다 |
| 조직 사전·선적 예외 | `overrides` 로 주입받음 | 저장·주입 |
| 과거 버전 재현 | 카탈로그 여러 버전을 빌드에 동봉 | 이미지에서 옛 버전 디렉터리를 지우지 말 것 |
| 반복 승인 → 조직 사전 자동 제안 | **하지 않는다** (이력이 없다) | 승인 이력 집계 |

**네 번째 줄이 가장 새기 쉽다.** 영향 범위는 요청 경계에서 잘린다. 선적의 일부만 실어 보내면 `impact` 가 **조용히 짧아지고**, 화면은 그것을 "이 값은 여기에만 쓰였다"로 읽는다. 잘렸다는 사실이 응답 어디에도 드러나지 않으므로 계약으로만 막을 수 있다.

## 다섯 개의 추출 경로

| 경로 | 입력 | OCR | 용도 |
|---|---|---|---|
| `/extract` | 이미지 | 필요 | 스캔 서류 운영 경로 |
| `/extract/pdf` | PDF | **텍스트 레이어면 불필요** | 전자 발행 서류 |
| `/extract/excel` | xlsx | 불필요 | 사내 양식·선적 명세 |
| `/extract/email` | .eml | 첨부에 따라 | 포워더 메일 수신 |
| `/extract/label` | 라벨 JSON | 불필요 | 파서 검증·CI |

`/extract/label` 을 두는 이유는 PaddleOCR·PaddlePaddle 설치가 무겁고 플랫폼을 타는데, 파서 동작 확인과 시연에는 그게 필요 없기 때문이다. CI 에서도 이 경로로 전 구간을 검증한다.

**다섯 경로가 모두 같은 파서를 탄다.** `FieldParser.REGIONS` 가 비율(`xr`/`yr`) 기반이라 좌표계 크기가 흡수되기 때문이다. 테스트가 이걸 직접 잡는다 — 같은 bbox 목록으로 만든 PDF 와 라벨 JSON 이 완전히 동일한 초안을 내는지 비교한다.

같은 이유로 **응답 형태도 다섯이 동일하다.** 서류 종류(`form_type`)가 달라도 마찬가지다. 종류마다 다른 응답 구조를 내면 S3 편집기가 종류 수만큼 렌더러를 갖게 되고, 종류를 추가할 때마다 화면도 함께 고쳐야 한다.

### 파일 형식은 확장자가 아니라 내용으로 판정한다

PDF 는 `%PDF`, xlsx 는 `PK`(zip 컨테이너) 매직바이트를 본다.

이미지를 `.pdf` 로 바꿔 올리거나 구형 `.xls` 를 그대로 올리는 일이 흔한데, 그때 PyMuPDF·openpyxl 오류를 그대로 흘리면 원인을 알 수 없는 500 이 된다. 무엇이 잘못됐는지 알려주는 400 이 낫다.

### PDF 는 텍스트 레이어를 먼저 본다

전자 발행 B/L 은 대부분 텍스트 레이어를 갖는다. 그걸 이미지로 굽고 OCR 에 넣으면 정확한 글자를 흐린 픽셀로 바꿔 다시 추측하는 셈이다 — 정확도가 떨어지고 느리다.

```
텍스트 레이어 경로   0.39초   source=pdf-text
OCR 경로            13초     source=pdf-ocr
```

텍스트 줄이 10개 미만이면 스캔본으로 보고 200dpi 로 구워 OCR 에 넘긴다. 스캔 PDF 에도 워터마크·도장 정도의 텍스트는 있으므로, 그걸 보고 "텍스트 레이어 있음"으로 판단하면 본문이 통째로 빠진 결과를 자신 있게 내놓게 된다.

> **주의.** 이 경로는 전 필드를 신뢰도 1.0 으로 내놓는다. 텍스트 레이어는 추측이 아니라 원문이므로 맞는 값이지만, *글자를 정확히 읽었는가* 와 *올바른 필드에 꽂혔는가* 는 다른 질문이다. 임의 레이아웃에서는 값이 밀리면서도 확인 대기열이 빈다 — `uncalibrated_layout` 판정이 이 구멍을 메운다. `remaining-work.md` 3.3 절 참조.

### 이메일은 첨부를 먼저 본다

본문은 대개 안내문이고 첨부가 서류다. 본문부터 읽으면 선하증권 대신 인사말을 파싱한다. 지원 첨부가 없을 때만 본문을 읽는다.

어느 경로였는지는 `source` 에 남는다(`email-pdf` / `email-excel` / `email-image` / `email-body`). 본문에서 뽑은 값과 첨부 원본에서 뽑은 값은 신뢰 수준이 다르므로 화면이 이를 구분할 수 있어야 한다.

## 공유는 저장 없이 한다

기획안 5절이 "PDF 출력·**공유** 가능"을 요구하지만, 이 서비스는 저장하지 않는다(위 절). 리포트를 저장하기 시작하면 그 원칙이 깨지고 만료·삭제·권한까지 AI 모듈이 떠안게 된다.

> v2 10.1 은 이번 기간 F4 산출물에서 **공유 링크·권한 제어를 제외**했다("공유 기능은 검증 가치 대비 공수가 큼"). 이미 만들었고 테스트가 붙어 있으므로 되돌리지 않되, **컷라인 밖 추가분**으로 다룬다. v2 5.4 가 정한 공유 사양(만료 기한 있는 열람 링크 기본 7일 · 열람 이력 기록 · **온프레미스 프로파일에서는 외부 링크 공유 비활성화**) 중 우리가 가진 것은 만료뿐이다.

그래서 **링크가 입력을 싣는다.** 토큰은 `v1.<zlib+base64url(입력)>.<HMAC-SHA256>` 이고, 열릴 때마다 서버가 같은 리포트를 다시 조립한다. 저장소도 DB 도 없다. 전체 B/L + L/C 를 실어도 토큰은 620자 안팎이다.

발급 시 한 번 조립해 보고 실패하면 400 을 낸다. 열어 봐야 터지는 링크를 쥐여주면 받는 쪽에서 깨지고, 그때는 원인을 알 방법이 없다.

**한계 두 가지를 알고 쓸 것.**

1. **토큰은 암호문이 아니다.** 서명은 위조를 막을 뿐 내용을 가리지 않는다. 링크를 가진 사람은 base64 를 풀어 B/L 원문을 읽을 수 있다 — 받을 사람은 어차피 리포트를 볼 사람이므로 의도상 문제는 아니지만, **링크가 새면 서류가 샌다.** 완화책은 짧은 만료뿐이다(기본 7일, `ttl_seconds` 로 조정).
2. **`REPORT_SHARE_SECRET` 를 설정하지 않으면 프로세스마다 임시 키를 쓴다.** 재시작하면 발급한 링크가 전부 죽는다. 고정 기본값을 두면 소스를 읽은 누구나 토큰을 위조할 수 있으므로 이쪽을 택했다. 기동 로그와 발급 응답(`ephemeral_secret`, `warning`)이 이 상태를 알린다.

## 상태 코드를 가르는 기준

코드별 조건표는 [api-spec.md](api-spec.md) 에 있다. 여기서는 왜 그렇게 갈랐는지만 적는다.

**503 과 500** — 게이트웨이 재시도 때문이다. OCR 엔진·PyMuPDF 미설치는 서버 구성 문제지 요청 오류가 아니다. 500 으로 흘리면 게이트웨이가 무의미하게 재시도한다.

**400 과 500** — 입력 형 오류(`TypeError`)는 400 이다. 같은 이유로, 500 을 내면 재시도가 붙는다.

**410 과 404** — 공유 링크 만료를 404 로 내면 받은 쪽이 '주소가 틀렸나'를 의심한다. 만료는 주소가 맞는데 시간이 지난 것이므로 구분해야 한다.

**예측 실패는 200 이다** — 하자 확률 예측이 터져도 검증 결과는 돌려준다. 모델은 부가 축이고, 여기서 500 을 내면 룰엔진이 정상적으로 낸 하자 목록까지 함께 잃는다. 대신 `prediction.model` 이 `rules-v1` 로 남아 산출 출처가 응답에 드러난다.

**F2 의 LLM 실패도 같은 이유로 200 이다** — ⑤단계가 터져도 결정론 제안(①②③④)은 그대로 나가고, `stats.llm_path` 가 `"failed"` 로 그 사실을 알린다.

### F2 가 400 을 내는 세 가지

[api-spec.md](api-spec.md) 의 400 조건에 F2 사유가 셋 늘었다. 셋 다 **요청이 실어 온 것이 잘못된 경우**라 400 이지, 서버 구성 문제(500·503)가 아니다.

| 사유 | 왜 200 이 아닌가 |
|---|---|
| **없는 사전 버전** (`glossary_version`) — 가용 버전을 `detail` 에 나열 | 조용히 기본 버전으로 떨어지면 **다른 사전으로 낸 판정이 같은 기준으로 기록된다.** 룰엔진이 version 과 digest 를 함께 남긴 것과 같은 걱정이다 |
| **`suggestion_id` 불일치** — "제안이 변조되었거나 사전 버전이 다릅니다" | 본문이 자기 자신과 어긋난 것이라 요청 오류다. 공유 링크 서명 깨짐을 404 로 내는 것과 자리가 다르다 — 거기는 URL 이 가리키는 자원의 문제다 |
| **조직 사전 형식 오류** (`overrides` · `/glossary/validate`) | 요청이 실어 온 사전이다. 표준 카탈로그가 깨지면 서버가 아예 뜨지 않는 것(구성 오류)과 구분된다 |

**둘째는 "하나라도"가 아니라 "전부"일 때만 400 이다.** 일부 제안만 어긋난 경우 나머지는 정상 적용됐을 수 있으므로 **200 + 그 건만 `unapplied`** 로 낸다. 거기서 요청 전체를 400 으로 내리면 이미 성공한 적용을 클라이언트가 못 받고, 게이트웨이는 "아무것도 안 됐다"로 오해한다. 반대로 전부 어긋났다면 대개 사전을 올린 뒤 옛 배치를 재전송한 것이고, 그때는 `unapplied` 목록보다 400 하나가 더 정확한 신호다.

> **`/glossary/validate` 의 400 은 `detail` 이 배열이다.** 공통 규약상 배열은 422 뿐이므로 예외다([api-spec.md](api-spec.md)). 로더가 "문제를 전부 모아 한 번에 던진다"는 규약을 따르기 때문인데, 게이트웨이가 `detail` 을 문자열로 가정하면 여기서 깨진다.

## 입력 형태

`/verify` 와 `/report` 는 `bl` 을 **평범한 dict** 로 받는다. F1 이 뽑은 값이든 S3 편집기에서 사람이 고친 값이든 같은 형태다.

두 경로를 가르면 '편집 후 재검증'이 다른 코드 경로를 타게 되고, 그쪽에만 있는 버그가 생긴다.

`as_of` 는 제시기간 계산의 기준 시각이다. 생략하면 현재 시각을 쓰지만, 테스트·시연에서는 넣어야 결과가 고정된다.

## 룰 카탈로그는 기동 시 1회 로드

요청마다 읽으면 YAML 파싱이 응답 시간에 들어가고, 카탈로그 오류를 기동이 아니라 첫 요청에서 발견하게 된다. lifespan 핸들러에서 검증하므로 **룰이 깨졌으면 서버가 뜨지 않는다.**

같은 핸들러가 하자 예측 모델의 적재 여부도 기동 시 확정한다. 첫 요청에서 알게 되면 그때는 이미 `rules-v1` 로 산출된 응답이 나간 뒤다.

**F2 용어사전도 같은 핸들러가 읽는다.** 다만 룰과 다른 점이 하나 있다 — **모든 버전을 검증하고, 인덱스는 실제로 쓰이는 버전만 지연 빌드한다.** 기본 버전만 검증하면 옛 버전이 조용히 썩다가 과거 판정을 재현하라는 요청이 들어온 날에야 깨진 것이 드러난다. 검증은 조용한 실패를 막는 일이고 인덱스는 성능이므로 시점이 다르다.

기동 시 찍히는 경고는 모두 **조용히 값만 달라지는 실패**를 드러내기 위한 것이다.

```
[aiService] 룰 카탈로그 로드 완료: 29건
[aiService] 경고: 조문 인용 미검증 29건 / 29건 — 실무 검증 필요
[aiService] 경고: 학습된 하자 예측 모델이 없습니다 — 위험 점수를 룰 가중치로 대체합니다.
[aiService] 경고: REPORT_SHARE_SECRET 미설정 — 공유 링크가 서버 재시작 시 무효가 됩니다.
[aiService] 용어사전 로드 완료: 186건 / 별칭 572건 (버전 std-2026.1)
[aiService] 경고: 출처 미검증 용어 186건 / 186건 — 실무 검증 필요
```

`TERMS_LLM_SELECT=true` 인데 키가 없거나 `changeme` 그대로면 한 줄이 더 찍힌다. 죽이지 않는다 — ⑤가 없어도 캐스케이드는 `requires_choice` 로 정상 동작하기 때문이다. 다만 **"켰다고 생각했는데 실제로는 안 켜졌다"가 정확히 조용한 실패**라 기동 로그에서 시끄럽게 알린다.

마지막 줄이 조문 인용 경고와 **같은 문구인 것은 의도다.** 성격이 같은 잔여 작업이며, 사전 쪽이 더 위험하다 — 조문은 실무자가 읽으면 틀린 것이 보이지만 `KRPUS`/`KRBUS` 는 화면에서 이상해 보이지 않는다.

## LLM 설정

`.env.example` 의 `LLM_PROVIDER` 로 분기한다. 기획안 6.1 의 "동일 코드베이스에서 환경 설정으로 분기"(SaaS 클라우드 LLM / 폐쇄망 로컬 LLM)를 이 자리에서 구현한다.

```bash
LLM_PROVIDER=template     # 외부 호출 없음 (기본값)
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
```

**키가 없거나 `changeme` 면 조용히 템플릿으로 떨어진다.** 개발·시연 환경에서 키 없이도 리포트가 완성되어야 하기 때문이다.

어느 쪽을 썼는지는 응답의 `summary.narrative_source` 에 남는다. LLM 호출이 실패해 템플릿으로 떨어진 경우에도 정확히 `template` 로 표기된다 — 요약기 클래스 이름으로 판정하면 실패했는데도 'AI 생성 요약'이라고 표기하게 되고, 그 값이 PDF 각주에 그대로 찍힌다.

### F2 전용 설정

F2 의 ⑤단계(후보 선정)는 `report/llm_providers.py` 의 같은 프로바이더를 쓰되 **자기 스위치와 자기 예산**을 갖는다.

```bash
TERMS_LLM_SELECT=false        # ⑤단계 자체의 on/off (기본값: 꺼짐)
TERMS_GLOSSARY_VERSION=       # 기본 표준 사전 버전. 비우면 effective_date 최신판
TERMS_LLM_MAX_ITEMS=20        # 호출당 항목 수
TERMS_LLM_TIMEOUT=8           # 초. 결정론 경로(1.3ms)를 더해도 선적 10초 예산 안
LLM_MODEL=gemini-3.5-flash-lite   # ⑤ 전용 권고 모델 (아래)
```

**모델은 `gemini-3.5-flash-lite` 를 쓴다.** ⑤가 하는 일은 후보 5개 중 번호 하나 고르기라 무거운 모델이 필요 없고, 실측 지연이 결정적으로 갈린다 — `gemini-3.7-flash` 는 2.46~15.89초에 무료 하루 20건 한도라 선적 10초 예산을 넘겼고, `gemini-3.5-flash-lite` 는 선적 1건을 **989.6ms~1.17초**에 끝낸다(8회 전건 성공). `*-flash-lite-latest` 같은 **별칭은 쓰지 않는다** — `versions.llm_model` 이 판정 재현성의 재료인데 별칭은 가리키는 모델이 바뀐다.

`list_models()` 로 모델 존재를 판정하지 마라. 목록과 실제 호출 가능성이 어긋난다 — `gemini-2.5-flash` 는 목록에 있으나 404 다.

**`TERMS_LLM_SELECT` 기본값이 꺼짐인 것은 `LLM_STRUCTURED_EXTRACT=false` 의 선례를 따른다.** 꺼 두어도 **제안이 사라지는 것이 아니라 자동 선정만 사라진다** — 유사도 후보를 `requires_choice=true` 로 나열해 사용자가 직접 고르게 한다. 기획안 5.2 의 "임의 선택 금지"가 기본 상태에서도 그대로 지켜진다.

**`TERMS_LLM_TIMEOUT` 을 따로 두는 이유**는 기존 `LLM_TIMEOUT`(20초)이 **선적 1건 10초 예산보다 크기** 때문이다. 리포트 요약은 예산이 다르므로 그쪽 기본값을 바꾸지 않고 F2 전용 값을 둔다. 재시도는 없다 — 6초에 재시도를 붙이면 최악이 12초로 예산 밖이다.

**`TERMS_LLM_MAX_ITEMS` 를 넘으면 상위 N 건만 보내고 나머지는 `requires_choice=true` + `Notice(kind="not_covered")` 다.** 조용히 자르면 "LLM 이 판단했다"와 "예산 때문에 못 물었다"가 구분되지 않는다. 앞은 판정이고 뒤는 미판정이며, 사용자에게는 완전히 다른 정보다.

**`TERMS_GLOSSARY_VERSION` 은 기본값만 정한다.** 요청이 `glossary_version` 을 실으면 그쪽이 이긴다. 어느 쪽이 쓰였는지는 응답 `versions.glossary_version` 에 남는다 — `summary.narrative_source` 와 같은 자리이며, 같은 이유로 **설정이 아니라 실제로 답을 낸 것**을 싣는다.

`.env` 는 기동 시 `load_dotenv()` 로 읽는다. 이 호출이 없으면 `.env.example` 이 설명하는 설정이 하나도 적용되지 않으며 **그 실패는 조용하다.** 이미 설정된 환경변수는 덮지 않는다 — 컨테이너·CI 가 주입한 값이 파일보다 우선해야 하기 때문이다.

## 실행

```bash
cd aiService
pip install -r requirements.txt
uvicorn api.main:app --port 5000 --reload
```

문서: <http://localhost:5000/docs>

### 동작 확인 기록

```
$ curl -s http://127.0.0.1:5099/health
{"status":"ok","rules_loaded":29,"env":"development"}
```

```
$ curl -X POST .../verify -d '{"bl":{...},"lc":{...},"as_of":"2026-06-10T00:00:00"}'
 확률 1.0 | 심각도 {'critical': 6, 'warning': 1, 'info': 0} | 평가 18 | 미검사 3
   D003  선적항이 L/C 지정 항구와 다릅니다. (서류 SHANGHAI, CHINA / L/C BUSAN)
   D005B Consignee 가 L/C 지정과 다릅니다. (서류 WRONG CO. / L/C DHHJ FRANCHISING CO., LTD.)
   D006  화물 명세에 L/C 요구 키워드가 없습니다. (누락 SPARE PARTS)
   D013  분할선적 금지 조건인데 분할선적 표시가 있습니다. (PARTIAL SHIPMENT)
```

```
$ curl -X POST .../report -d '{...}'
 등급 높음 | 산출 rules-v1 | 요약출처 template
 헤드라인: 제출 전 정정이 필요한 치명 하자 6건이 발견되었습니다.
 기한: 2026-06-22 | 남은일수 12
 미제출: ['요구 서류: COMMERCIAL INVOICE', '요구 서류: PACKING LIST']
 예상: 하자 통보 및 재제출 요구 예상
```

```
$ curl -X POST .../report/pdf -o out.pdf
content-type: application/pdf
content-disposition: attachment; filename="BL_Copilot_Report_HG290309.pdf"
  10,295 bytes | 3쪽 | 한글 1077자
```

#### F2 — 표준 용어 교정 (2026-08-16)

`GEMINI_API_KEY` 없이 측정했다. ⑤단계(LLM 후보 선정)는 `TERMS_LLM_SELECT=false` 가 기본이라
돌지 않았고, 응답의 `stats.llm_path` 가 `not_called` 로 그 사실을 싣는다. **아래는 전부
결정론 경로의 값이다.**

```
$ cd aiService && python -m uvicorn api.main:app --port 5099
[aiService] 용어사전 로드 완료: 186건 / 별칭 572건 (버전 std-2026.1)
[aiService] 경고: 출처 미검증 용어 186건 / 186건 — 실무 검증 필요
```

```
$ curl -s localhost:5099/health
{"status":"ok","rules_loaded":29,
 "rule_catalog":{"version":"1","digest":"169cdada5d17","label":"v1+169cdada5d17"},
 "env":"development","glossary_version":"std-2026.1","glossary_terms":186}

$ curl -s localhost:5099/glossary
{"catalog_version":"std-2026.1","effective_date":"2026-01-01",
 "terms":186,"aliases":572,"unverified_term_count":186,
 "by_class":{"transport_doc":12,"delivery":6,"party_suffix":20,"qty_unit":12,
             "volume_unit":6,"price_term":11,"practice_phrase":25,"hs_code":29,
             "container_no":13,"port":52},
 "available_versions":["std-2026.1"]}
```

`unverified_term_count` 가 `terms` 와 같다 — 인용한 출처(UN/LOCODE·ISBP 745·UN/ECE Rec 20·
ISO 6346)를 실무자가 원문과 대조한 항목이 **하나도 없다**는 뜻이다. `GET /rules` 의
`unverified_source_count` 와 같은 규약이며, 화면이 이 값을 숨기면 미검증 출처가 검증된
것처럼 인용된다.

```
$ curl -s -X POST localhost:5099/normalize -H 'Content-Type: application/json' -d '{"bl":{
    "port_of_loading":"부산","port_of_discharge":"PORTLAND",
    "gross_weight":"1,234.50 KGS","shipper":"GAE WOON CO.,LTD",
    "description_of_goods":"SAW MACHINE MSKU 123456 5 freight prepaid"}}'
HTTP 200 · 0.117s

 제안 6건 · 안내 0건 · 미판정 0건
   port_of_loading       '부산'             → 'KRPUS'            0.95 alias      UN/LOCODE
   port_of_discharge     'PORTLAND'        → null               0.95 similarity UN/LOCODE  [사용자 선택]
   gross_weight          'KGS'             → 'KGM'              0.95 alias      UN/ECE Rec 20
   shipper               'CO.,LTD'         → 'Co., Ltd.'        0.90 pattern    상호 표기 정규화 규칙
   description_of_goods  'MSKU 123456 5'   → 'MSKU1234565'      0.97 pattern    ISO 6346
   description_of_goods  'freight prepaid' → 'FREIGHT PREPAID'  0.92 format     ISBP 745

 versions: {"glossary_version":"std-2026.1","cascade_version":"f2-cascade-1",
            "rules_catalog_version":"1","llm_model":null,"ranker":"ngram-dice-3"}
 stats:    {"by_stage":{"alias":2,"format":1,"pattern":2,"similarity":1},
            "llm_path":"not_called","llm_calls":0,"elapsed_ms":115}
```

읽을 점 셋.

- `port_of_discharge` 의 `to_be` 가 `null` 이다. PORTLAND 는 미국 오리건(`USPDX`)과 호주
  빅토리아(`AUPTL`)에 다 있고 값·인접 필드·L/C 어디에서도 국가를 좁히지 못했다.
  **임의로 고르지 않고** 후보만 실어 사용자에게 넘긴다(기획안 §5.2 "임의 선택 금지").
- `gross_weight` 의 `as_is` 가 `'KGS'` 이지 `'1,234.50 KGS'` 가 아니다. span 이 단위 토큰만
  가리키므로 **수치는 구조적으로 보존된다** — `apply` 가 숫자를 건드릴 수 없다.
- `stats.by_stage` 의 합(6)이 제안 수와 같다. 어긋나면 이 서비스가 보고하는 수치를 믿을 수 없다.

```
$ curl -s -X POST localhost:5099/normalize/apply -H 'Content-Type: application/json' \
    -d '{"documents":[{"doc":"선하증권","fields":{…위와 같은 값…}}],
         "suggestions":[…위 응답의 suggestions 그대로…],
         "scope":"field","decided_by":"ethan","decided_at":"2026-05-25T00:00:00"}'
HTTP 200

  port_of_loading       'KRPUS'
  port_of_discharge     'PORTLAND'                                  ← 손대지 않음
  gross_weight          '1,234.50 KGM'                              ← 수치 보존
  shipper               'GAE WOON Co., Ltd.'                        ← 본체 바이트 보존
  description_of_goods  'SAW MACHINE MSKU1234565 FREIGHT PREPAID'   ← 두 조각 모두 적용

  corrections: 5
  unapplied:   ["사용자 선택이 필요한 제안입니다"]
```

`description_of_goods` 한 필드에 span 제안이 둘 걸렸는데 오프셋이 어긋나지 않았다 — 치환을
start 내림차순(뒤에서부터) 하기 때문이다. `requires_choice` 제안은 `scope="all"` 이어도
적용되지 않는다.

**제안을 변조하면 적용하지 않는다.**

```
$ (위 요청에서 제안 1건의 to_be 를 'HACKED' 로 바꿔 전송)
HTTP 200
  unapplied: ["제안이 변조되었거나 사전 버전이 다릅니다", …]
  해당 필드 값: '부산'   ← 원본 그대로
```

전부 변조면 400, 일부면 200 + 그 건만 `unapplied` 다. 사전 버전이 올라가면 배치 전체의 id 가
한 번에 무효가 되므로 "전부 변조"는 실제로는 버전 불일치인 경우가 흔하다.

**서류를 못 찾으면 무엇을 찾다 실패했는지 말한다.**

```
  unapplied: ["제안이 가리키는 서류를 요청에서 찾을 수 없습니다:
               doc='선하증권' doc_id=None (요청에 실린 서류: [('선하증권', 'D1')])"]
```

`/normalize` 를 `bl` 로 부르면 제안이 `doc_id=None` 을 가리킨다. `/normalize/apply` 에
`doc_id` 를 붙여 보내면 전 제안이 미적용으로 떨어지는데, 일반적인 문구만 돌려주면 연동하는
쪽은 원인을 알 수 없다(없는 `glossary_version` 에 가용 목록을 붙이는 것과 같은 논리).
이 전사를 만드는 과정에서 실제로 밟은 자리이고, 그래서 메시지를 고쳤다.

```
$ curl -s -X POST localhost:5099/normalize/reject -d '{"suggestions":[…],
    "reason":"in_house","note":"사내 관행","decided_by":"ethan","decided_at":"2026-05-25T00:00:00"}'
HTTP 200
  {"decision":"rejected","reason":"in_house","note":"사내 관행",
   "decided_by":"ethan","decided_at":"2026-05-25T00:00:00","impact":[]}
```

`decided_at` 은 요청이 싣는다 — 서버가 `now()` 를 부르지 않는다.

**오류 경로.**

```
$ curl -s -X POST localhost:5099/normalize -d '{"bl":{"port_of_loading":"부산"},"glossary_version":"nope-9999"}'
HTTP 400  {"detail":"알 수 없는 용어사전 버전입니다: 'nope-9999' (가용: std-2026.1)"}

$ curl -s -X POST localhost:5099/normalize -d '{}'
HTTP 400  {"detail":"documents 와 bl 이 모두 비어 있습니다. 둘 중 하나는 있어야 합니다."}

$ curl -s -X POST localhost:5099/normalize/reject -d '{…,"reason":"아무거나",…}'
HTTP 422
```

```
$ curl -s -X POST localhost:5099/glossary/validate -H 'Content-Type: application/json' -d '{
   "id":"org-42","version":"org-2026.3",
   "terms":[{"term_id":"ORG.BAD","canonical":"X","category":"port"},
            {"term_id":"ORG.BAD","canonical":"Y","category":"nope","lang":"xx",
             "authority":"조직 사전","version":"org-2026.3","effective_date":"2026-01-01"}]}'
HTTP 400
  - ORG.BAD: 필수 항목 'lang' 누락
  - ORG.BAD: 필수 항목 'authority' 누락
  - ORG.BAD: 필수 항목 'version' 누락
  - ORG.BAD: 필수 항목 'effective_date' 누락
  - ORG.BAD: category 가 port 인데 country 가 없습니다
  - ORG.BAD: lang 'xx' 은 ko|en|code 중 하나여야 합니다
  - ORG.BAD: term_id 가 중복입니다 (#0 와)
  - ORG.BAD: 알 수 없는 category 'nope' (등록된 것: container_no, delivery, goods,
    hs_code, party_name, party_suffix, port, practice_phrase, price_term, qty_unit,
    transport_doc, volume_unit)

$ (정상 조직 사전)
HTTP 200  {"ok":true,"catalog_version":"org-2026.3","terms":1,"aliases":1,"tier":"organization"}
```

**문제를 전부 모아 한 번에** 돌려준다 — 첫 오류에서 끊으면 편집자가 고치고 다시 부르기를
여덟 번 반복해야 한다. 게이트웨이가 조직 사전을 **저장하기 전에** 이걸 부르면 깨진 사전이
DB 에 들어가지 않는다.

#### F2 측정

```
$ cd aiService && python -m pytest
4 failed, 633 passed, 2 skipped in 2.54s

$ python -m terms.evaluate
코퍼스: f2-corpus-1 · 210건 · ⑤LLM: 끔(기본)
전체  정밀도 0.9910  재현율 0.9910  choice비율 0.0238
      확정 제안 111건 중 110건 정답 · 정답 필요 111건 중 110건 재현 · choice 5/210(적중 5/5)
클래스별 — practice_phrase 0.9167 을 제외한 전 클래스 1.0000
불일치 (1건):
  PHR009  선하증권/marks  값='full set of original bills'
          기대=value:FULL SET  실제=value:FULL SET|ORIGINAL
[PASS] 정밀도 목표(0.9) — 실측 0.9910

$ python -m acceptance
F2  표준 용어 교정 — 필드 1건       2초 이하   최대 168µs (p95 103µs)  통과
F2  표준 용어 교정 — 선적 1건 일괄    10초 이하  최대 1.3ms (p95 1.3ms)  통과
F2  표준 용어 교정 — 냉시작          기준 없음   152.6ms                미측정
```

`requires_choice` 는 제안으로 세지 않는다 — 판정한 것이 아니라 사용자에게 넘긴 것이다. 이
구분을 빼면 애매한 건을 전부 `requires_choice` 로 밀어 정밀도를 1.0 으로 만들 수 있으므로
재현율과 choice 비율을 함께 찍는다.

**남은 불일치 1건은 코퍼스의 표현 한계이지 오교정이 아니다.** `FULL SET` 과 `ORIGINAL` 은 둘
다 실제 ISBP 관행 문구이고 카탈로그에 있는데, 코퍼스가 한 필드에 제안 1건만 기대하는
형식이라 어긋난다. **수치를 맞추려 라벨을 고치지 않았다.** 다만 이 케이스가 드러낸 한계는
따로 있다 — `'full set of original bills'` 가 `'FULL SET of ORIGINAL bills'` 가 되어 표기가
뒤섞인다(§남은 것 참조).

선적 1건은 서류 3장(선하증권·상업송장·포장명세서) 34필드 기준이다. 목표 대비 네 자리 수
여유가 있는 이유는 결정론 경로가 사전 조회와 문자 3-gram 계산뿐이고 임베딩도 네트워크도
없기 때문이다. **⑤단계를 켜면 여기에 Gemini 왕복이 더해진다 — 그 경로는 아직 실측하지
않았다.** 마이크로초 값은 실행마다 흔들리니 자릿수만 읽을 것.

## 테스트

```bash
cd aiService && python -m pytest        # 4 failed, 633 passed, 2 skipped
```

**실측 639건이다**(2026-08-16). 이 문서가 오래 적어 두었던 수치는 낡았다 — 그 사이 F2 5파일 207건과 F1·F3 쪽 증가분이 들어왔다.

수집되는 것은 **637건**이고(633 통과 · 4 실패), 여기에 모듈 단위 skip 2건이 더해져 639 로 보고된다. `test_defect_model.py`(XGBoost 미설치)와 `test_degrade.py`(numpy 미설치)는 모듈이 통째로 건너뛰어 수집 수에 들어가지 않는다.

| 파일 | 개수 | |
|---|---:|---|
| `test_rule_engine.py` | 73 | |
| `test_terms_validators.py` | 51 | **F2** |
| `test_terms_cascade.py` | 48 | **F2** |
| `test_api.py` | 41 | |
| `test_field_parser.py` | 38 | |
| `test_terms_glossary.py` | 36 | **F2** |
| `test_draft.py` | 30 | |
| `test_mt700.py` | 30 | |
| `test_llm_extract.py` | 29 | |
| `test_terms_apply.py` | 29 | **F2** |
| `test_extractor.py` | 28 | **4건 실패 중** |
| `test_report.py` | 26 | |
| `test_cross_doc.py` | 25 | |
| `test_corpus.py` | 22 | |
| `test_terms_api.py` | 20 | **F2** |
| `test_doc_types.py` | 17 | |
| `test_excel_email.py` | 17 | |
| `test_terms_llm.py` | 17 | **F2** |
| `test_acceptance.py` | 16 | |
| `test_llm_providers.py` | 15 | |
| `test_uncalibrated_layout.py` | 12 | |
| `test_review_sheet.py` | 11 | |
| `test_terms_evaluate.py` | 6 | **F2** |
| `test_defect_model.py` | — | 모듈 skip (XGBoost) |
| `test_degrade.py` | — | 모듈 skip (numpy) |
| **계** | **637** | F2 소계 **207** |

**실패 4건은 F2 착수 전부터 있던 것이다.** `test_extractor.py::TestOCR입력_축소` 4개 케이스로, 이 환경의 PNG DPI 처리가 달라 `_downscale_for_ocr` 가 다른 크기를 돌려준다. F1 소관이며 F2 범위에서 고치지 않았다 — 고치면 F2 변경에 무관한 diff 가 섞이고, 그 자체가 `remaining-work.md` 가 경계하는 "변화의 원인을 추적할 수 없게 만드는" 패턴이다.

PaddleOCR·DB 없이 전부 돈다. FastAPI 미설치 시 `test_api.py`·`test_terms_api.py` 는 자동으로 건너뛴다. **F2 는 PaddleOCR·XGBoost·numpy 중 무엇도 쓰지 않는다.**
