# F2 진행 상태

> 설계와 계약은 [`HANDOFF.md`](HANDOFF.md). 이 파일은 **어디까지 됐는지**만 담는다.
> 태스크를 끝낼 때마다 갱신한다. **수치는 실제로 돌려 보고 적는다 — 지어내지 않는다.**
> (`docs/ai-service/remaining-work.md` 규약)

- 브랜치: `feature/f2-standard-language` (base `fe6364f`, `origin/main`)
- 최종 갱신: 2026-08-16 · **T0~T21 완료** (구현·테스트·측정·문서·출처 검증·Gemini 실연동).
  남은 것은 **실무자 출처 검토 16건 · ⑤ 켬/끔 정책 결정 · 코드 정리**(§다음에 할 일)

> **갱신 규칙**: 이 파일은 **오케스트레이터만** 고친다. 서브에이전트는 자기 보고에
> 적고, 반영은 오케스트레이터가 한다 — 병렬 태스크가 같은 파일을 동시에 쓰면
> 상태표가 조용히 어긋난다.

---

## 상태 요약

| # | 태스크 | 상태 | 모델 | 산출물 |
|---|---|---|---|---|
| T0 | 클론·브랜치·의존성·기준선·인수인계 문서 | ✅ 완료 | — | `docs/f2/HANDOFF.md`, `docs/f2/PROGRESS.md` |
| T1 | 설계 문서 `f2-standard-terms.md` | ✅ 완료 | Opus | `docs/ai-service/f2-standard-terms.md`(844L) |
| T2 | `terms/keys.py` · `terms/types.py` | ✅ 완료 | Sonnet | `terms/keys.py`(104L), `terms/types.py`(449L), `terms/__init__.py`(빈 파일, T12 몫) |
| T3 | `terms/policy.py` | ✅ 완료 | Sonnet | `terms/policy.py`(376L) |
| T4 | `terms/glossary.py` | ✅ 완료 | Sonnet | `terms/glossary.py`(712L) + `catalogs/_sample/`(20건 표본) |
| T5 | `catalogs/std-2026.1/locode.yaml` | ✅ 완료 | Haiku → **Fable 감사** | 63건 → **52건** (교정 14·삭제 12·추가 3) |
| T6 | `catalogs/std-2026.1/glossary.yaml` · `manifest.yaml` | ✅ 완료 | Haiku → **Fable 감사** | 162건 → **134건** (삭제 28·display 교정 다수) |
| T7 | `terms/validators.py` | ✅ 완료 | Sonnet | `terms/validators.py`(497L) — 체크디지트 독립 교차검증 통과 |
| T8 | `terms/similarity.py` | ✅ 완료 | Sonnet | `terms/similarity.py`(177L) — 동음이의 경로 확인 |
| T9 | `terms/cascade.py` | ✅ 완료 | Opus→Sonnet | `terms/cascade.py`(1850L+) |
| T10 | `terms/llm_select.py` | ✅ 완료 | Sonnet | `terms/llm_select.py`(432L) — 11개 주입·실패 검증 통과 |
| T11 | `terms/apply.py` | ✅ 완료 | Sonnet | `terms/apply.py`(446L) |
| T12 | `terms/__init__.py` · `api/main.py` 배선 | ✅ 완료 | Sonnet | `terms/__init__.py`(256L) + `api/main.py` +630L (5 엔드포인트) |
| T13 | 테스트 6파일 | ✅ 완료 | Sonnet ×2 | `tests/test_terms_*.py` **207건** |
| T14 | `terms/eval/corpus.yaml` | ✅ 완료 | Sonnet | **210건** (음성 44.8%) — 구현 결함 2종 검출 |
| T15 | `terms/evaluate.py` | ✅ 완료 | Sonnet | 정밀도 CLI + `test_terms_evaluate.py`(6건) |
| T16 | `acceptance.py` 확장 | ✅ 완료 | Sonnet | F2 Result 2건 + 냉시작 분리 |
| T17 | 문서 마감 | ✅ 완료 | Opus | `f2-standard-terms.md`(1,856L)·`api.md`·`api-spec.md`·`remaining-work.md` |
| T18 | 회귀 검증 | ✅ 완료 | 오케스트레이터 직접 | `api.md` "동작 확인 기록" 에 실제 전사 |
| T19 | `PORT_SYNONYMS` 이관 *(별도 브랜치 권고)* | 🔲 보류 | Opus+Fable | — |
| T20 | **사전 출처 검증** | ✅ 완료 | Sonnet ×2 *(Fable 한도 초과)* | 미검증 186 → **16**. 오류 12건 정정 |
| T21 | **실제 Gemini 호출 확인** | ✅ 완료 | 오케스트레이터 직접 | `gemini-3.7-flash` 지연 2.5~15.9초 · 무료 하루 20건 소진 |
| T21d | **무료 모델 재선정** | ✅ 완료 | 오케스트레이터 직접 | **`gemini-3.5-flash-lite`** 1.1초 → 기획안 10초 안. 예산 재협상 철회 |
| T21e | ⑤ 켠 정밀도 실측 | ✅ 완료 | 오케스트레이터 직접 | **0.9561~0.9909 (실행마다 다름)** — 트레이드오프 확인 |
| T21f | 테스트 네트워크 격리 | ✅ 완료 | 오케스트레이터 직접 | `conftest.py` autouse — 633 passed 2.8초 안정 |

범례: ✅ 완료 · ⏳ 진행 · ⬜ 대기 · 🔲 보류 · ❌ 막힘

---

## 실측 수치

### 착수 기준선 (T0, 2026-08-16)

```
$ cd aiService && <venv>/bin/python -m pytest
4 failed, 426 passed, 2 skipped in 1.81s
```

- **426 passed / 4 failed / 2 skipped** — 이것이 F2 착수 전 상태다.
- 실패 4건은 **전부 사전 존재하며 F2 와 무관**하다:
  `tests/test_extractor.py::TestOCR입력_축소` 의 4개 케이스.
  PNG DPI 처리가 이 환경에서 다르게 동작해 `_downscale_for_ocr` 가 3000×4000 대신
  1654×2340 을 돌려준다. **F2 작업 중 이 4건이 계속 실패해도 정상이며, 고치려 들지
  마라** — 별개 이슈다. 대신 **총 통과 수가 426 아래로 떨어지면 F2 가 회귀를
  일으킨 것**이다.
- `docs/ai-service/api.md` 가 적어 둔 "349건" 은 낡은 수치다. 실측이 432건(수집 기준)이다.
- PaddleOCR·XGBoost 미설치 상태에서 잰 값이다(skipped 2건이 그것).

### F2 실측 수치 (T18, 키 없이)

| 지표 | 목표 | **실측** | 측정 방법 |
|---|---|---|---|
| 테스트 총 통과 | 426 + α | **633 passed** (426 기준선 + **207** F2) | `python -m pytest` |
| 교정 제안 정밀도 | ≥ 0.90 | **0.9909** | `python -m terms.evaluate` (LLM 끔) |
| 재현율 | 참고값 | **0.9909** | 동상 |
| `requires_choice` 비율 | 참고값 | **0.0238** (5/210, 적중 5/5) | 동상 |
| 필드 1건 응답 | ≤ 2.0s | **최대 168µs** (p95 103µs) | `python -m acceptance` (최댓값) |
| 선적 1건 일괄 | ≤ 10.0s | **최대 1.3ms** (p95 1.3ms) | 동상 (서류 3장 · 34필드) |
| 냉시작 | 기준 없음 | **152.6ms** | 사전 로드 + 인덱스 빌드 + 지연 캐시 예열 |
| 사전 canonical / 별칭 | 182 / ~660 | **185 / 572** | `GET /glossary` |
| 출처 미검증 용어 | 전건 | **16 / 185** (T20 검증 후) | 기동 로그 |

시간 예산은 목표 대비 **4자리 수 여유**가 있다. 결정론 경로가 순수 파이썬 사전 조회와
3-gram 계산뿐이고 임베딩·네트워크가 없기 때문이다(④단계를 n-gram 으로만 두기로 한 결정의
직접적 결과). ⑤단계(Gemini)를 켜면 여기에 네트워크 왕복이 더해지므로 이 수치는
**LLM 을 안 태운 경로**의 값이다 — `acceptance` 가 `note` 에 그 사실을 남긴다.

### 정밀도 0.9909 의 유일한 불일치 — `PHR009`

```
'full set of original bills'  →  'FULL SET of ORIGINAL bills'
```

`practice_phrase` 카탈로그의 `FULL SET` 과 `ORIGINAL` 이 **각각** 매치되어 둘 다 제안된다.
코퍼스는 `FULL SET` 하나만 기대했다. 시스템 동작 자체는 틀리지 않았고(둘 다 실제 ISBP
관행 문구다), **코퍼스가 한 필드에 제안 1건만 기대하는 표현 한계**다.

**코퍼스 라벨을 고쳐 1.0000 을 만들지 않았다.** 수치를 예쁘게 만들려고 정답지를 손보는
것이 정확히 이 프로젝트가 금하는 일이고, 서브에이전트들에게도 같은 지시를 했다.

다만 적용 결과가 남긴 진짜 문제는 따로 있다 — **조각만 대문자가 되어 표기가 뒤섞인다.**
ISBP 표준형은 `FULL SET OF ORIGINAL BILLS OF LADING` 전체가 대문자인데, F2 는 카탈로그에
있는 조각만 고칠 수 있어 `of`·`bills` 는 소문자로 남는다. 안전 문제는 아니고(사람이 카드를
개별 승인한다) 정밀도에도 안 잡히지만, **화면에서 어색하게 보인다.**
근본 원인은 `Original B/L` 결함(§T14 결함 B)과 같은 계열이다 — 더 긴 표준 문구의 일부를
독립 문구로 인식한다. 그때는 값 전체가 canonical 이라 막을 수 있었지만 여기는 아니다.
T17 이 `f2-standard-terms.md` §남은 것에 한계로 명시했다. 후속은 "긴 문구 우선 매칭".

---

## 개발 환경

**작업 트리 경로에 `:` 가 있어 `python -m venv` 가 거부한다.**

```
Error: Refusing to create a venv in .../feature:f2-standard-language/...
because it contains the PATH separator :.
```

venv 를 저장소 밖에 만들어야 한다. 이 세션이 쓴 경로:

```
/private/tmp/claude-501/-Users-ethanyang-Documents-Smart-e-BL-Backend/7ec480ee-2b15-4f9b-b638-874d5b3f1480/scratchpad/f2venv
```

Python 3.12(`/usr/local/bin/python3.12`, `requirements.txt` 선언 버전).
설치한 것: `pydantic PyYAML fastapi uvicorn[standard] python-multipart python-dotenv
pytest httpx2 reportlab PyMuPDF openpyxl`.
**PaddleOCR·paddlepaddle·xgboost·scikit-learn 은 설치하지 않았다** — 무겁고 플랫폼을
타며, 테스트가 `importorskip` 으로 건너뛴다. F2 는 이들 중 무엇도 쓰지 않는다.

시스템 기본 `python3` 는 3.14.5 이고 필요한 패키지가 없다. 위 venv 를 쓸 것.

---

## 판단이 갈렸던 지점 (기록)

이어받는 세션이 "왜 이렇게 안 했지" 하고 다시 뜯지 않도록 남긴다.

### T0

1. **venv 위치** — 저장소 안에 못 만든다(경로의 `:`). scratchpad 에 두었다.
   저장소를 `.gitignore` 로 오염시키지 않는 부수 효과도 있다.
2. **기준선 테스트 4건 실패를 고치지 않았다** — F1 OCR 입력 축소 로직의 환경 의존
   이슈로, F2 범위 밖이다. 고치면 F2 커밋에 무관한 변경이 섞이고, 그 자체가
   `remaining-work.md` 가 경계하는 "변화의 원인을 추적할 수 없게 만드는" 패턴이다.
3. **`docs/f2/` 를 새로 팠다** — `docs/ai-service/` 는 기능 설계 문서 자리이고
   (`f1-intake.md`·`f3-defect-prediction.md`·`f4-report.md`), 인수인계·진행 상태는
   성격이 다르다. F2 설계 문서 자체는 규약대로
   `docs/ai-service/f2-standard-terms.md` 에 간다.

### T2·T3

1. **T1(`f2-standard-terms.md`) 이 미완인 채로 착수했다** — 원래 순서는
   `T1 → T2/T3` 지만, 이번 세션은 `HANDOFF.md` 자체를 계약서 삼아 명시적으로
   T2+T3 를 지시받았다. `HANDOFF.md` §4.1·§4.2·§4.5·§6.2 가 이미 dataclass
   필드·허용 단계표·신뢰도 상수를 구체적으로 못박고 있어 착수는 가능했다.
   **다음 세션이 T1 을 쓸 때**: 여기서 내린 판단(특히 `GlossaryTerm`/
   `Evidence` 의 `tier` 의미, `FIELD_CLASS`/`FIELD_SCAN_CLASSES` 구조)을
   `f2-standard-terms.md` 에 역으로 반영해야 문서와 코드가 어긋나지 않는다.
2. **`FIELD_CLASS`/`FIELD_SCAN_CLASSES` 를 코드에서 처음 도입했다** —
   `HANDOFF.md` 는 "자유서식 필드는 FIELD_SCAN_CLASSES 같은 별도 매핑이
   필요하다"고만 적었지 이름·형태를 정하지 않았다. `terms/policy.py` 가
   `FIELD_CLASS`(필드 전체 → 클래스 1개)와 `FIELD_SCAN_CLASSES`(자유서식
   필드 → 스캔할 클래스 목록)로 나눠 정의했다. T9(캐스케이드)가 이 두 표를
   그대로 쓸 것을 전제한다.
3. **실제 필드명을 전수 확인한 결과, `container_no`/`hs_code`/
   `transport_doc`/`delivery` 4개 클래스가 전용 필드를 갖지 못했다** —
   자세한 내용은 아래 "다음에 할 일" 참고. F1 필드 확장이나 T9 의 자유서식
   스캔 범위 조정이 필요할 수 있다.
4. **`marks_and_numbers` 는 존재하지 않는 필드명이다** — `HANDOFF.md` T3
   절이 예시로 든 필드명이지만, 실제 `ocr/doc_types.py:_PACKING_LIST.fields`
   의 필드명은 `marks` 다. `policy.py` 는 `marks` 를 썼다. `f2-standard-terms.md`
   작성 시 이 오탈자를 바로잡아야 한다.
5. **`GlossaryTerm`/`Evidence` 의 `tier` 를 "이 항목이 3계층(표준/조직/선적)
   중 어디서 왔는지"로 해석했다** — `HANDOFF.md` 본문이 `tier` 를 명시적으로
   정의하지 않아 내린 판단이다. `GlossaryStack`(T4)이 조회 시 이 필드를
   채워 넣는다는 전제로 설계했다. T4 가 이 전제와 다르게 설계하면
   `types.py`/`policy.py` 양쪽의 주석을 함께 고쳐야 한다.

### T2·T3 — 필드 매핑에서 드러난 것

계획서가 필드명을 **추측**했고 세 군데가 틀렸다. 실제 `BL_FIELD_NAMES`·`SPECS` 를 확인한 결과:

1. 포장명세서의 자유서식 필드는 `marks_and_numbers` 가 아니라 **`marks`** 다.
2. **`container_no`·`hs_code` 를 담는 전용 필드가 저장소 어디에도 없다.** 두 클래스는
   `description_of_goods`/`marks` 안의 span 스캔이 유일한 진입 경로다.
3. `transport_doc`·`delivery`·`practice_phrase` 도 전용 필드가 없다. 이름만 보면
   `total_freight` 가 답 같지만 아니다 — `ocr/field_parser.py:408` 이 그 자리에 금액만
   넣는다(`f"${amount.group(1)}"`). 관행 문구가 들어올 수 없는 필드다.

3번을 미매핑으로 두면 세 클래스가 **사전만 있고 절대 발동하지 않는 죽은 코드**가 되므로
`FIELD_SCAN_CLASSES` 에 넣어 진입 경로를 열었다. 전용 필드를 F1 이 뽑게 되면 그때
`FIELD_CLASS` 로 옮긴다. 현재 12개 클래스 전부 진입 경로가 있다(자동 검사로 고정).

### T5 — 전사 결과를 그대로 받지 않았다

Haiku 전사본 63건 중 **52건에 작성자 스스로 `note: 코드 미확인`** 을 달았고, 실제로 확인해
보니 상당수가 틀렸다.

- **공항 코드를 해항 코드로 씀** — `MYKUL`(KUL 은 공항, 항구는 Port Klang), `IDCGK`
  (수카르노하타 공항), `JPHND`(하네다), `USSJC`(산호세 CA 는 애초에 항구가 아님)
- **항구 아닌 내륙 도시** — 산티아고(칠레, 항구는 발파라이소), 산호세(코스타리카),
  발렌시아(베네수엘라)
- **코드 오류** — 오리건 포틀랜드는 `USPOP` 이 아니라 **`USPDX`**(설계 문서의 동음이의
  테스트가 참조하는 코드다), 암스테르담 `NLDOA`→`NLAMS`, 뉴캐슬(영국) `GBNEW`→`GBNCL`,
  텐진 `CNTZN`→`CNTSN`, 다롄 `CNDZH`→`CNDLC`, 포항 `KRPNK`→`KRKPO`, 울산 `KRULM`→`KRUSN`,
  마산 `KRMPU`→`KRMAS`, 광양 `KRKTW`→`KRKAN`
- **존재하지 않는 항목** — `KRBOK (Pohang Back)`, `KRKHW (Kampho)` 등

**`verified: false` 로 덮을 수 있는 문제가 아니다.** 그 플래그는 "authority 원문과 대조하지
않았다"는 뜻이지 "코드를 지어내도 된다"는 뜻이 아니다. 사전이 그대로 나가면 F2 가 정확히
설계가 막으려던 실패 — 틀린 값을 확신을 담아 제안 — 를 한다.

→ Fable 감사 패스를 붙였다. 지시의 핵심은 **건수보다 정확성**: 60건을 채우려 애매한 항목을
남기지 말고 확신 없으면 지울 것, 동음이의 쌍은 **양쪽이 다 실제 해항**인 것만 남길 것
(3쌍만 살아남아도 된다).

**감사 결과 (63 → 52)**

- 교정 14건: `KRPNK`→`KRKPO`(포항) · `KRULM`→`KRUSN`(울산) · `KRMPU`→`KRMAS`(마산) ·
  `KRKTW`→`KRKAN`(광양) · `KRDON`→`KRTGH`(동해) · `KRJEJ`→`KRCHA`(제주) ·
  `KRSGN`→`KRSHO`(속초) · `CNTZN`→`CNTSN` · `CNDZH`→`CNDLC` · `JPKOB`→`JPUKB`(고베) ·
  `USPOP`→`USPDX` · `CAYVR`→`CAVAN`(YVR 은 공항) · `AUNEW`→`AUNTL` · `AUPPT`→`AUPTL` ·
  `NLDOA`→`NLAMS` · `GBNEW`→`GBNCL` · `MYKUL`→`MYPKG`(Port Klang) ·
  `IDCGK`→`IDTPP`(Tanjung Priok) · `CLSAP`→`CLVAP`(발파라이소)
- 삭제 12건: 항구 아님(JPHND·USSJC·CRSJC·VEVAL·DOSJD·CNHGH) · 존재하지 않음
  (KRBOK·KRKHW·KRYNG) · 코드 미상(KRJIN·KRSAM·KRGAN·JPSZK·JPFKS·JPKUM)
- 추가 3건: `JPTYO`·`NLRTM`(로테르담이 빠져 있었다)·TRIPOLI 쌍
- 별칭에서 **공항 코드 전량 제거**. 3자리 약어는 `PUS`(부산)·`NYC`(뉴욕)만 유지

**동음이의 4쌍 생존** — PORTLAND(`USPDX`/`AUPTL`, 설계 문서 지정 코드 그대로) ·
NEWCASTLE(`GBNCL`/`AUNTL`) · VICTORIA(`CAVIC`/`SCVIC`) · TRIPOLI(`LYTIP`/`LBKYE`, 신규).
VALENCIA·SANTIAGO·SAN JOSE 쌍은 한쪽이 항구가 아니라 깨졌다.

**아직 확신이 낮은 항목 (다음 사람 실무 검증 목록)**
- `SCVIC` vs `SCPOV`(Port Victoria) — 세이셸에서 실무가 어느 쪽을 쓰는지. 우선순위 최상
- `KRCHA`(제주) — locode.info 2019-2 데이터셋으로만 확인, UNECE 최신판 미대조
- `CNWUH` — 코드는 맞으나 양쯔강 하천항이라 해상 B/L 적합성 확인 필요
- `DEBRE`(브레멘) — 코드는 맞으나 컨테이너 물동량 주력은 브레머하펜 `DEBRV`
- `USSFO` — 코드는 맞으나 실제 컨테이너 항만은 오클랜드 `USOAK`

### T7 — 체크디지트를 오케스트레이터가 다시 쟀다

체크디지트는 잘못 짜면 **조용히 전부 틀리는** 종류의 코드라 보고를 믿지 않고 직접 확인했다.
ISO 6346 표준 예제 `CSQU3054383` → 3 (일치). 장비 구분자가 `U|J|Z` 가 아닌 `MSKA1234565` 는
추측하지 않고 `matched=False` 로 물러난다. `(sum%11)%10` 접힘 사각지대도 구현자가 경험적으로
입증해 주석에 남겼다.

### T4 — `GlossaryTerm` 에 필수 4필드가 빠져 있었다 (오케스트레이터가 수정)

T4 구현자가 발견했다. `lang`·`authority`·`version`·`effective_date` 가 dataclass 에 없어
`from_dict` 가 조용히 버리고 있었다 — **카탈로그 YAML 에는 있는데 런타임에는 없는** 상태다.

`authority` 가 특히 치명적이다. 제안 카드의 근거가 `Evidence.authority` 인데 그게 **항목마다**
다르다: 같은 `qty_unit` 이라도 `KGM` 은 UN/ECE Rec 20 이고 포장 단위는 업계 관행이며,
조직 사전 오버라이드는 `조직 사전` 이다. T4 는 우회책으로 `policy.CLASSES[cls]` 의 클래스
기본값을 쓰라고 제안했지만, 그러면 **오버라이드가 표준과 같은 출처를 인용**하게 되고 그건
리포트가 출처를 지어내는 것과 같다. 네 필드를 `types.py` 에 추가했다.

덤으로 잡힌 버그: PyYAML 이 따옴표 없는 `2026-01-01` 을 `datetime.date` 로 파싱해
`to_dict()` 가 JSON 직렬화 불가 객체를 내보내고 있었다. `from_dict` 에서 문자열로 고정했다 —
카탈로그 편집자가 따옴표를 붙이는지에 판정 재현성이 걸리게 둘 수는 없다.

**T13 에 회귀 테스트를 넣을 것**: 적재한 term 의 `authority` 가 YAML 값과 같은지,
`effective_date` 가 `str` 인지, `to_dict()` 가 `json.dumps` 를 통과하는지.

### 실제 카탈로그 적재 확인 (T6 감사 전 시점)

```
항목 214 / 별칭 596 / 미검증 214
클래스별 {'transport_doc': 12, 'delivery': 6, 'party_suffix': 20, 'qty_unit': 12,
          'volume_unit': 6, 'price_term': 11, 'practice_phrase': 25,
          'hs_code': 30, 'container_no': 40, 'port': 52}
```

T6 감사가 `container_no`·`hs_code` 를 줄이면 이 수치는 내려간다. **줄어드는 것이 정상이다.**

### T6 감사 — 전사본에서 나온 것

162건 → **134건** (`container_no` 40→13, `hs_code` 30→29, 나머지 7클래스는 별칭만 정리).
카탈로그 전체는 214 → **186 항목 / 572 별칭**.

가장 위험했던 것 — **`STRAIGHT_BL`(기명식 선하증권)의 별칭에 `지시식 선하증권` 이 들어
있었다.** 정확히 반대 개념이다. 그대로 나갔으면 F2 가 "지시식 선하증권"을 보고 기명식으로
교정을 제안했을 것이고, 그건 서류의 **법적 성질을 바꾸는** 오교정이다. `ORDER_BL` 로 옮겼다.

같은 종류의 오류들:
- `SEA_WAYBILL` 의 별칭에 `해상선하증권`·`선하증권` — 해상화물운송장은 선하증권이 아니다
- `CTR.MSCU` display 가 **Maersk** 로 되어 있었다(MSCU 는 MSC 접두)
- `EGHU`→Egyship(허구, 실제 Evergreen), `TCNU`→Torm(허구, 실제 Triton), `SUDU`→Seatrade(허구, 실제 Hamburg Süd)
- HS display 오류 10건: `2711.21`(LNG→기체 천연가스, LNG 는 2711.11) · `4011.20`(항공기용→버스·트럭용) ·
  `7907.00`(아연 스크랩→기타 아연 제품) · `3301.30`(정유→레지노이드) 등
- `HS.9406_00` 삭제 — HS2017 부터 9406.10/20/90 으로 분할되어 현행 HS 에 없다
- `party_suffix`: `INC` 의 별칭 `유한회사` 제거(Inc ≠ 유한회사)

**남은 확인 필요 항목**: 삭제한 CTR 중 `SITU`·`SEKU`·`BEAU`·`GLDU` 는 실재 가능성이 있어
BIC 레지스터 대조 시 복원 후보. `CTR.CSNU` 의 COSCO 귀속은 2016 합병 이력 기반 추정.

**미해결 — `MTR`·`FOT`·`INH` 가 `volume_unit` 분류**: 미터·피트·인치는 길이 단위지 용적이
아니다. 감사자가 "category 는 policy 매핑과 얽혀 감사 범위를 넘는다"고 판단해 두었다.
교정 자체(`FT`→`FOT`)는 옳고 클래스 이름만 부정확하므로 실해는 낮다. **T17 에서 클래스
설명을 "용적·치수 단위"로 정리하거나 별도 클래스로 분리할지 결정할 것.**

### `container_no`·`hs_code` 는 사전을 타지 않는다

`policy.allows()` 를 실제로 조회해 확인한 사실:

```
container_no   허용단계=['pattern']
hs_code        허용단계=['pattern']
```

두 클래스는 설계상 `pattern` 단계만 돈다. 교정은 ISO 6346 체크디지트와 자릿수 정규화가
하고 **사전 조회 경로가 없다.** 즉 선사 접두 40건과 HS 30건은 캐스케이드가 한 번도 읽지
않는 데이터다. 그래서 T6 감사에 "확신하는 것만 남기고 지워라 — 5건·10건만 남아도 좋다"고
지시했다. 지어낸 접두를 남겨 두면 나중에 누가 이 클래스에 `alias` 단계를 열었을 때
존재하지 않는 선사명이 사용자 화면에 인용된다.

### T9~T11 — 오케스트레이터가 직접 고친 3건

서브에이전트 보고가 "전부 통과"였는데도 직접 돌려 보고 잡은 것들이다. **보고를 그대로
믿지 말 것.**

**1. span 계약 모순 (오케스트레이터가 만든 결함)**

T9 마무리 지시에서 `to_be` 를 "단위 토큰만 바뀐 전체 값", `span` 을 "단위 토큰 span" 이라고
동시에 요구했다. 둘은 양립할 수 없다. 그대로 뒀으면 `1,234.50 KGS` 승인 시
`1,234.50 1,234.50 KGM` 이 된다 — **수치가 복제된 채 사람 승인을 통과해 서류에 박히는**
경로다. 계약을 하나로 고정하고 [`HANDOFF.md`](HANDOFF.md) §4.5 에 사례와 함께 못박았다.

**2. `Correction` 이 기획안 §5.8 을 두 군데 못 맞춤**

기획안은 `correction` 을 "변경 필드, 이전 값, 새 값, **영향 항목**, **승인자**, 시각"으로
정의하고 F2·F5 가 공유한다고 했는데 `impact`·`decided_by` 가 없었다. 구현자는 "승인자
영속화는 게이트웨이 몫"이라 판단했지만, 게이트웨이가 저장하려면 **우리가 돌려줘야** 한다.
무상태는 "저장하지 않는다"이지 "받은 사실을 잃어버린다"가 아니다.
`impact` 는 **실제로 함께 바뀐 자리만** 담는다 — 제안 시점 후보 목록을 그대로 옮기면
`scope="field"` 로 한 자리만 고쳤는데도 여러 자리가 바뀐 것처럼 기록되고, F5 가 그걸
시작점으로 없는 변경을 따라간다.

**3. 영향 범위가 span 제안에서 조용히 비었음 (1번 수정의 부작용)**

`_attach_impact` 는 `run.occurrences` 를 `as_is` 로 조회하는데 `occurrence()` 는 **필드 값
전체**로 등록한다. `as_is` 가 조각(`'CO.,LTD'`)이 되면서 `'GAE WOON CO.,LTD'` 로 등록된
자리를 못 찾았다. 영향 범위가 비면 화면은 "이 값은 여기에만 쓰였다"로 읽고 **일괄 적용이
근거를 잃는다.** 조각일 때는 전 필드를 뒤지고, 찾은 자리마다 **그 필드에서의 오프셋**을
span 으로 달게 했다(같은 조각이 필드마다 다른 위치에 있다).

검증: 같은 `CO.,LTD` 가 `선하증권/shipper`(9,16)와 `상업송장/seller`(14,21)에 있을 때
`scope="all"` 한 번으로 둘 다 제자리만 갈리고 `ACME`·`LIMITED` 등 주변 문자열은 보존된다.

### T14 — 코퍼스가 구현 결함 2종을 잡았다

라벨을 동작에 맞춰 고치지 않고 **사양 편에 세운** 덕분에 나온 결과다. 둘 다 오케스트레이터가
직접 고쳤다.

**결함 A — Incoterms 교정이 멱등이 아니었다** (`validators.parse_price_term`)

```
'FOB BUSAN'                    -> 'FOB Busan (Incoterms 2020)'                    (정상)
'FOB Busan (Incoterms 2020)'   -> 'FOB Busan (Incoterms 2020) (Incoterms 2020)'   ✗
```
`format_price_term` 이 붙인 병기를 다시 장소의 일부로 읽었다. 게이트웨이 재검증·사용자
재실행은 **정상 경로**이고, 거기서 F2 가 **자기가 만든 값을 자기가 부순다.**
→ 장소 파싱 전에 `\(\s*incoterms\s*\d{4}\s*\)$` 꼬리를 제거. 연도를 고정하지 않은 이유는
Incoterms 개정판(2010·2020)이 붙은 값도 장소로 오인하면 안 되기 때문이다.

**결함 B — 이미 표준인 값 안에서 다른 클래스 조각을 찾았다** (`cascade._process_field`)

`'Original B/L'` 은 `transport_doc` 의 canonical 이라 고칠 게 없는데, `practice_phrase` 의
canonical `'ORIGINAL'` 이 그 안의 `'Original'` 에 걸려 대문자 교정을 제안했다. 서류에 아무
문제가 없는데 카드가 뜬다. **이런 카드가 쌓이면 사람이 카드를 읽지 않게 되고, 그 순간 승인
게이트가 형식이 된다.**
→ 값 전체가 어떤 클래스의 canonical 과 같으면(`_is_canonical_value`) 조각 스캔을 건너뛴다.
값 전체 경로(`FIELD_CLASS`)는 막지 않는다 — 표기 정리는 여전히 필요할 수 있다.

### 오케스트레이터 자신의 검증 오류 (기록용)

코퍼스 재검증에서 `LC008`(47A 자유서식 L/C 우선) 1건이 불일치로 나와 구현 결함을 의심했으나,
**원인은 내 검증 스크립트가 `lc_raw_tags` 를 안 넘긴 것**이었다. 코퍼스와 구현은 둘 다
옳았다. 없는 결함을 기록할 뻔했다 — 불일치를 보면 **하네스부터 의심할 것.**

### 정밀도 1.0000 을 그대로 믿지 말 것

```
전체 210건 / 불일치 0건
정밀도 1.0000  재현율 1.0000  (TP=111 FP=0 FN=0, requires_choice 5건)
```

**이 수치는 상한이지 실력이 아니다.** 이유:

1. **코퍼스가 독립 정답지가 아니다.** 작성한 에이전트가 구현을 읽고 썼다. 사양과 동작이
   갈리는 자리에서 사양 편에 서라고 지시했고 실제로 결함 2종을 잡았지만, 그래도 실무자가
   만든 진짜 서류에서 뽑은 것이 아니다.
2. **애매한 케이스가 의도적으로 빠졌다.** 작성자가 제외를 명시한 것들이 정확히 정밀도를
   떨어뜨렸을 케이스다(아래 미해결 항목 참조).
3. 실서류 기준 정밀도는 **T18 이나 실무 검토에서 다시 재야 한다.**

### 미해결 — `party_suffix` 에 진실의 원천이 둘이다

T14 작성자가 라벨할 수 없다며 제외한 케이스들이 같은 원인을 가리킨다.
`validators._SUFFIX_CANON` 과 `glossary.yaml` 의 canonical 이 **서로 다른 표준형**을 말한다:

| 입력 | `validators` | `glossary.yaml` |
|---|---|---|
| `AG`/`SA`/`BV`/`NV` | `AG`/`SA`/`BV`/`NV` | `A.G.`/`S.A.`/`B.V.`/`N.V.` |
| `PTE LTD` | `Pte., Ltd.` (쉼표) | `Pte. Ltd.` (쉼표 없음) |
| `LIMITED`/`COMPANY` | `Limited`/`Company` (재케이싱) | `Ltd.`/`Co.` (축약) |

게다가 `PLC`·`LLP`·`K.K.`·`SARL`·`SPA`·`EURL`·`OHG` 는 `_LEGAL_SUFFIXES` 에 없어서
**`party_suffix` 가 허용하는 유일한 단계(pattern)로는 절대 도달하지 못한다** — 사전에만
있고 죽어 있는 항목이다.

`party_suffix` 는 `pattern` 전용이라 사전을 조회하지 않으므로 **지금은 오답이 나가지는
않는다.** 다만 어느 쪽이 표준형인지 정해 한쪽으로 모아야 하고, 그때까지는 사전의 접미
항목이 실제로 쓰이지 않는다는 사실을 알고 있어야 한다. **T17 에서 결정할 것.**

### T13a — 테스트가 결함 1건 + 커버리지 격차를 드러냈다

**결함 C — 겹침 해소가 자기 docstring 과 달랐다** (`apply._apply_group`)

docstring 은 "겹치면 **원본 목록 순서**로 먼저 온 것이 이긴다"인데, 실제로는 겹침 판정이
`start 내림차순` 정렬 루프 안에 있어 **문서 안 위치가 뒤인 쪽**이 이겼다. 사용자가 먼저
고른 제안이 문서 위치 때문에 밀린다.
→ 두 단계로 분리했다. ① 겹침 해소는 목록 순서로 ② 치환은 start 내림차순(뒤에서부터).
둘은 서로 다른 관심사이고, 한 루프에서 처리해서 생긴 결함이다.

**`PORT_SYNONYMS` 커버리지 — 9쌍 중 3쌍만 덮는다**

덮는 것: `BUSAN/PUSAN` · `INCHEON/INCHON` · `GUANGZHOU/CANTON`.
못 덮는 것: 인도 3곳(`MUMBAI/BOMBAY`·`CHENNAI/MADRAS`·`KOLKATA/CALCUTTA`) ·
`TROMSOE/TROMSO`(노르웨이) · `JEDDAH/JEDDA`(사우디) · `BEIJING/PEKING`(**애초에 해항이
아니다** — 톈진이 그 역할).

테스트를 그냥 실패로 두지 않고 **격차를 상수로 고정**했다(`PORT_SYNONYM_GAPS`).
영구히 빨간 테스트가 있으면 사람이 빨강을 무시하게 되고 그때 진짜 회귀가 묻힌다.
대신 격차가 **줄어도 늘어도** 테스트가 알려 준다. T19(이관)의 착수 조건은 이 목록이 비는 것.

진짜 위험은 "안 덮는 것"이 아니라 **한쪽만 덮는 것**이다(`BUSAN`→`KRPUS` 인데 `PUSAN` 은
어디로도 안 가는 상태). 그건 별도 테스트로 막는다.

### T13b — 설계 문서가 거짓말을 하는 자리 2곳

코드 결함은 아니다. **문서에 있는데 실제로는 절대 나오지 않는 값**이라 T17 에서 문서를
고쳐야 한다. 지금 고치지 않고 남긴 이유는, 둘 다 **안전한 방향으로 어긋나** 있어서
서둘러 코드를 바꿀 이유가 없기 때문이다.

**① `exact`(0.99) 단계는 도달 불가다.**

```
'krpus'      -> 'KRPUS'  stage=format  conf=0.92
'  KRINC  '  -> 'KRINC'  stage=format  conf=0.92
```
`normalize_key(값) == canonical 키` 라는 것은 **정의상 대소문자·공백만 다르다**는 뜻이므로,
exact 히트는 언제나 미용 변경(`_is_cosmetic_change`)으로 판정되어 `format` 으로 강등된다.
설계표의 `CONF_EXACT = 0.99` 는 영원히 나오지 않는 숫자다.

어긋남의 방향은 안전하다 — 신뢰도를 **낮게** 잡는다. 정밀도 우선 시스템에서 옳은 방향이다.
T17 에서 단계표를 실제에 맞추거나, `exact` 를 별도 단계로 유지할 근거를 적어야 한다.

**② `MIN_CONFIDENCE = 0.60` 도 정상 경로로는 도달 불가다.**

④의 `SIMILARITY_FLOOR`(0.55)를 통과한 후보의 신뢰도 하한과 ⑤의 하한이 이미 0.60 을
넘는다. 즉 이 상수는 **한 번도 발동하지 않는 안전망**이다. 안전망 자체는 남길 가치가
있으나(단계 상수가 바뀌면 되살아난다), 문서가 이걸 실제로 쓰이는 게이트처럼 설명하면 안 된다.

### 테스트 현황 (실측)

```
$ cd aiService && <venv>/bin/python -m pytest
4 failed, 633 passed, 2 skipped in 2.62s

$ <venv>/bin/python -m pytest tests/test_terms_*.py
207 passed in 1.07s
```

**426(기준선) + 207(F2) = 633.** 정확히 일치 — 회귀 없음.
실패 4건은 착수 전부터 있던 `test_extractor.py::TestOCR입력_축소` 다.

| 파일 | 건수 |
|---|---:|
| `test_terms_validators.py` | 51 |
| `test_terms_cascade.py` | 48 |
| `test_terms_glossary.py` | 36 |
| `test_terms_apply.py` | 29 |
| `test_terms_api.py` | 20 |
| `test_terms_llm.py` | 17 |
| `test_terms_evaluate.py` | 6 |
| **계** | **207** |

> **수치를 두 번 틀렸다.** 오케스트레이터가 "F2 213건"으로 T17 에 넘겼는데
> 213 = 639 − 426 이고 426 은 **통과 수**라, 착수 전 실패 4건과 skip 2건이 F2 몫으로
> 딸려 들어간다. T17 이 `pytest tests/test_terms_*.py` 를 직접 돌려 **207** 로 정정했다.
> 파일별 합(51+48+36+29+20+17+6)도 207 이다.
> 교훈: **합계에서 빼서 구한 수는 실측이 아니다.** 세고 싶은 것을 직접 세라.

### T18 — 회귀 검증에서 결함 1건 추가로 나왔다

`curl` 전사를 만들다 밟았다. `/normalize` 를 `bl` 로 부르면 제안이 `doc_id=None` 을
가리키는데 `/normalize/apply` 에 `doc_id` 를 붙여 보내면 **전 제안이 200 과 함께 조용히
미적용**으로 떨어졌다. 사유는 "적용 대상 서류 또는 필드를 찾을 수 없습니다" 한 줄뿐이라
연동하는 쪽이 무엇을 고쳐야 할지 알 수 없었다.

```
이전: 적용 대상 서류 또는 필드를 찾을 수 없습니다
이후: 제안이 가리키는 서류를 요청에서 찾을 수 없습니다:
      doc='선하증권' doc_id=None (요청에 실린 서류: [('선하증권', 'D1')])
```

없는 `glossary_version` 에 가용 목록을 붙인 것과 같은 논리다 — 실패는 어차피 나지만
받은 쪽이 원인을 알 수 있어야 한다. 오케스트레이터의 요청 구성 실수가 드러낸 것이지만,
게이트웨이 연동자가 똑같이 밟을 자리였다.

**T18 로 확인한 것 전부** (키 없이, ⑤단계 미사용):

| 확인 | 결과 |
|---|---|
| 전체 회귀 | 633 passed / 4 failed(착수 전) / 2 skipped |
| 정밀도·재현율 | 0.9910 · 0.9910 (목표 0.90) |
| 필드 1건 / 선적 1건 | 최대 168µs / 1.3ms (목표 2초 / 10초) |
| 서버 기동 로그 | 사전 186·572 적재 + 미검증 186 경고 |
| `/normalize` 왕복 | 200, 제안 6건, `llm_path: not_called` |
| 적용 결과 | 수치·상호 본체 보존, 두 span 조각 모두 적용 |
| 변조 탐지 | 일부 변조 → 200 + 그 건만 `unapplied`, 값 보존 |
| 없는 사전 버전 | 400 + 가용 목록 |
| `bl`·`documents` 둘 다 없음 | 400 |
| 잘못된 `reason` | 422 |
| `/glossary/validate` | 깨진 사전 → 400 + **문제 8건 전부**, 정상 → 200 |

### T20 — 출처 검증에서 오류 12건이 더 나왔다

**두 차례 감사를 이미 거친 사전이었다.** 그런데 UNECE 공식 디렉터리와 전수 대조하니 또
나왔다. 감사와 출처 대조는 다른 일이라는 뜻이다 — 앞선 감사는 "눈에 띄는 것"을 걸렀고,
이번은 **한 건씩 원문과 맞춰 봤다.**

**중국 항구 8건이 전부 공항 코드였다.** UNECE 상 `Function: ---4----`(항공 전용) —
같은 3자리 IATA 코드를 쓰는 국제공항이다.

```
CNSHA → CNSHG (상하이)   CNTSN → CNTXG (톈진 신강)   CNNGB → CNNBG (닝보)
CNTAO → CNQDG (칭다오)   CNXMN → CNXMG (샤먼)        CNDLC → CNDAG (다롄)
CNCAN → CNGZG (광저우)   CNWUH → CNWHG (우한)
```

앞선 감사가 `MYKUL`·`IDCGK`·`JPHND` 를 같은 이유로 걷어냈는데 **중국 전체가 남아 있었다.**

더 나쁜 것 둘:
- **`AUPTL` 은 빅토리아주 포틀랜드가 아니라 퀸즐랜드의 "Port Alma"** 였다. 동음이의
  `PORTLAND` 쌍의 호주측이 **통째로 다른 항구**를 가리키고 있었다 → `AUPTJ`
- **`ESVAL` 은 발렌시아가 아니라 갈리시아의 소도시 "Valga"**(항만 기능 없음) → `ESVLC`

**용어사전 쪽 정정**: `CTR.APLU` (APL → CMA CGM, 2016 인수) · `CTR.SUDU` (Hamburg Süd →
Maersk, 2017 인수) · HS display 6건을 표제(heading) 설명에서 세번(subheading) 정밀 문언으로 ·
`SFX.AG`/`SA`/`BV`/`NV` 를 ISO 20275 근거로 무점 표기(`A.G.` → `AG`)로 — 이로써
`validators` 와 카탈로그가 말하던 **두 표준형 중 하나가 정리됐다.**

### T20 — 즉시 조치한 안전 문제: `UOM.PF`

검증자가 **현행 Rec 21 에서 `PF` = "Pen"(가축우리)이고 팔레트는 `PX`** 라는 소견을 냈다.
과거 EANCOM 에는 `PF` = pallet 로 등재돼 있어 두 등록이 어긋난다.

```
이전: '100 PALLETS' → 'PF'   근거 "UN/ECE Rec 20"     ← 값과 근거가 동시에 틀린다
이후: '100 PALLETS' → 제안 없음 + Notice(not_covered)
```

**`validators.py` 와 카탈로그 양쪽에서 뺐다.** `verified: false` 로 두는 것으로 부족하다고
판단한 이유: 그 플래그는 "대조하지 않았다"는 뜻인데, 여기는 **틀렸을 수 있다는 적극적
증거**가 나온 경우다. 포장명세서의 "100 PALLETS" 를 가축우리로 바꾸면서 틀린 출처까지
인용하는 것은 `STRAIGHT_BL` 과 같은 등급이다.

팔레트를 정규화하지 못해 잃는 것은 편의뿐이고, 틀리게 정규화해 잃는 것은 서류의 의미다.
표준을 확인하면 `PX` 로 되살릴 것. **이 매핑은 T7 사양(오케스트레이터)이 처음부터 잘못
지시한 것이다.**

### T20 — 코퍼스를 두 번 고쳤다 (그리고 한 번은 안 고쳤다)

| 대상 | 고쳤나 | 왜 |
|---|:-:|---|
| 항구 코드 8곳 (`CNSHA`→`CNSHG` 등) | **○** | 정답지가 틀렸다. UNECE 원문 대조로 카탈로그가 정정됐으니 정답지가 따라가는 게 맞다 |
| `UNIT016` 팔레트 (`expect: PF` → `expect_none`) | **○** | 사전에서 뺀 항목이라 기대값이 존재하지 않는다 |
| `PHR009` (`FULL SET` vs `FULL SET\|ORIGINAL`) | **×** | 시스템 동작이 옳고 코퍼스 표현 한계다. **수치를 위해 정답지를 손보는 것**이라 안 고쳤다 |

세 번째와 앞의 둘을 가르는 기준: **정답지가 틀렸으면 고치고, 정답지가 좁으면 놔둔다.**
카탈로그 정정 직후 정밀도가 0.9910 → 0.9369 로 떨어졌는데, 그건 시스템이 **더 정확해졌는데**
정답지가 옛 코드를 들고 있었기 때문이다.

### T20 — 남은 미검증 16건 (정직하게)

| 항목 | 왜 확신 못 하나 |
|---|---|
| `UOM.CT`·`PK`·`BX`·`BG`·`DR`·`PCE` (6) | 실제로는 Rec **20** 이 아니라 Rec **21**(포장코드) 소속이고 현행 병합리스트는 `X` 접두를 요구한다(`XCT`…). `PCE` 는 현행 리스트에 아예 없다. **`authority` 문자열이 틀렸다** |
| `PHR.*` 5건 | ISBP 원문(ICC 유료)을 못 봤다. UCP 600 조문으로 근거를 못 찾은 것들 |
| `SFX.PTE_LTD`·`KK`·`SARL`·`EURL` (4) | ISO 20275 에서 정확히 대조 안 됨. `PTE_LTD` 는 ISO 등록(`Pte Ltd`, 점·쉼표 없음)이 코드·카탈로그 **양쪽 모두와 다르다** |
| `CTR.EITU` | BIC 등록사가 "Gaining Enterprise S.A."(파나마) — Evergreen 계열인지 독립 확인 못 함 |

**`ISBP 821` vs `745` 결론**: ISBP 821 은 **실재하는 2023년 개정판**이고 745(2013)를 대체한
현행판이다. 즉 `policy.py`/`rules.yaml` 의 "ISBP 821" 이 맞고 카탈로그의 "ISBP 745" 가
낡았다. 검증자가 코드·카탈로그를 고치지 않고 결론만 보고했다 — **후속 정리 대상.**

### T20 — 라우팅 이탈 기록

지시된 검증 모델은 Fable 인데 **세션 한도(21:40 리셋)로 두 번 실패**해 Sonnet 으로 돌렸다.
Fable 이 풀린 뒤 **같은 대상을 재검증하면 값어치가 있다** — 특히 위 미검증 16건과,
`verified: true` 를 단 169건 중 표본을 다른 모델이 다시 보는 것.

### T21 — 실제 Gemini 호출 확인: **⑤단계는 10초 예산과 양립하지 않는다**

키를 넣고 처음으로 실호출했다. 여태 "미검증"으로 남겨 둔 구간이고, **재 보니 예산을
못 맞춘다.**

**막았던 것은 코드가 아니라 SSL 이었다.** venv(macOS python.org 3.12)에 CA 번들이 없어
`CERTIFICATE_VERIFY_FAILED` 가 났다. `python -m pip install certifi` 후
`SSL_CERT_FILE=$(python -c "import certifi;print(certifi.where())")` 로 해결.
(`f2venv/bin/pip` 이 엉뚱하게 3.14 로 해석되므로 **`python -m pip` 를 쓸 것.**)

**모델**: `gemini-3.7-flash` 로 실호출 성공(`{"ok":true}`). `gemini-2.5-flash` 는 404 —
`remaining-work.md:311` 기록대로다. 다만 **`list_models()` 는 3.7 계열을 목록에 넣지
않는다**(37개 중 없음). 목록과 실제 호출 가능성이 어긋나므로 `list_models()` 로 모델
존재를 판정하지 마라 — `llm_providers.py:35` 주석이 반대 방향의 같은 현상을 이미 적고 있다.

**실측 지연 (5회, timeout 60초)**

```
1: 2.46s   2: HTTP 503   3: HTTP 503   4: 15.89s   5: 11.67s
최소 2.46s · 최대 15.89s · 평균 10.01s · 503 비율 2/5
```

**결론: `TERMS_LLM_TIMEOUT=6` 으로는 대부분 실패한다.** 결정론 경로가 1.3ms 라 ⑤에 남는
여유는 9.9초인데, **한 번 호출이 15.89초까지 간다.** 타임아웃을 늘리면 기획안의 "선적 1건
10초"를 깨고, 안 늘리면 ⑤가 거의 항상 폴백한다. 재시도는 답이 아니다 — 예산을 더 먹고,
어댑터가 재시도를 안 하는 것도 의도다.

**설계의 폴백이 실제 실패로 검증됐다.** 모킹이 아니라 진짜 타임아웃에서:

```
llm_path: 'failed' · evidence.stage: 'similarity'(‘llm’ 아님) · to_be: None
requires_choice: True · versions.llm_model: None · 결정론 제안 2건 생존
```

`stage` 가 `'llm'` 으로 남지 않는 것이 핵심이다 — 실패했는데 'AI 판정'으로 표기되면 그
값이 화면에 그대로 찍힌다. 17건의 모킹 테스트가 지키려던 규약이 실물에서도 지켜졌다.

**그래서 지금 상태**: ⑤단계는 **안전하지만 실효가 낮다.** 동음이의 항구는 대개 사용자
선택으로 내려간다(그게 틀린 답보다 낫다). 기본값이 `TERMS_LLM_SELECT=false` 인 것이
결과적으로 옳았다.

**선택 3(예산 재협상)을 택했다 — 그리고 재 보니 진짜 병목은 지연이 아니었다.**

### T21b — 재협상 결과와, 그 과정에서 드러난 실제 병목

> **아래 재협상(25초)은 §T21d 에서 철회했다.** 모델을 `gemini-3.5-flash-lite` 로 바꾸니
> 기획안 10초 안에 들어서 예산을 올릴 이유가 없어졌다. 경위를 남겨 두는 것은, 같은
> 상황에서 "기준을 올리자"가 먼저 떠오르기 때문이다 — 그게 오답이었다.

**바꾼 것 (근거 기반, 기획안 §10.5 가 수치를 "확정된 값이 아니다"라고 명시)**

| 대상 | 이전 | 이후 | 근거 |
|---|---|---|---|
| `policy.llm_timeout()` 기본 | 6.0초 | **20.0초** | 관측된 최장 성공 15.89초를 담는다. `LLM_TIMEOUT` 기본값과도 같다 |
| 선적 예산 (⑤ 켬) | 기획안 10초 | **25초** (신규 상수) ← **§T21d 에서 철회됨** | 타임아웃 20초 + 결정론 1.3ms + 여유. 기획안 10초는 **LLM 왕복을 전제하지 않았다** |
| 선적 예산 (⑤ 끔) | 10초 | **10초 유지** | 1.3ms 로 통과한다. 기획안 값을 건드릴 이유가 없다 |

`acceptance.py` 가 **selector 가 실제로 붙었는지**로 기준을 가른다. `use_llm=True` 라도 키가
없으면 `default_selector()` 가 `None` 이므로, 의도가 아니라 실제로 붙었는가를 봐야 한다 —
안 붙은 실행에 25초 기준을 대면 기획안 기준으로 잰 척하게 된다.

**고친 함정 둘**

1. **선적 픽스처에 ⑤ 진입 경로가 없었다.** `port_of_discharge: "LOS ANGELES"` 라 동음이의가
   안 생겨 `--llm` 을 줘도 ⑤가 한 번도 안 돌았고, **25초 기준을 1.1ms 로 "통과"** 했다.
   그 수치는 아무것도 말하지 않는다. 국가를 안 붙인 `"PORTLAND"` 로 바꿨다.
2. **`acceptance.py`·`terms/evaluate.py` 가 `.env` 를 안 읽었다.** `--llm` 을 줘도
   `GEMINI_API_KEY` 를 못 봐 selector 가 `None` 이 됐다 — **LLM 을 안 태운 수치가 태운
   것처럼 보고되는** 구조였다. `api/main.py` 와 같이 `load_dotenv()` 를 넣었다.
   (`from __future__` 앞에 넣어 한 번 깨뜨렸다. `__future__` 는 파일 맨 앞이어야 한다.)

**⑤가 실제로 돌게 한 뒤의 실측**

```
선적 1건 일괄 (⑤ 켬, 표본 9): p50 247ms · p95 20.12초 · max 20.12초 → 25초 기준 통과
```

p50 이 247ms 인 이유가 핵심이다 — **대부분의 호출이 실패하고 빠르게 돌아온다.**
max 20.12초는 타임아웃 상한을 그대로 문 한 건이다.

### T21c — 진짜 병목: 무료 등급 할당량

실패 원인을 파 보니 **429 RESOURCE_EXHAUSTED** 였다.

```
Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests,
limit: 20, model: gemini-3.7-flash
```

**이 키는 무료 등급이고 `gemini-3.7-flash` 하루 20건이 상한이다.** 검증하는 동안 소진했다.
앞서 본 503 들도 상당수 이 계열이었을 것이다.

즉 **지연이 아니라 할당량이 ⑤단계의 실질 제약이다.** 예산 재협상은 그 자체로 옳았지만
(지연 근거가 실측으로 바뀌었다) 그것만으로는 ⑤가 돌지 않는다.

**연동 자체는 확인됐다.** 첫 호출에서 `{"ok":true}` 를 받았고, `gemini-2.5-flash` 는 404 —
`remaining-work.md:311` 기록대로다. `list_models()` 는 3.7 계열을 목록에 넣지 않으므로
**모델 존재를 목록으로 판정하지 마라.**

**설계의 폴백이 세 종류 실물 실패에서 검증됐다** — 타임아웃·503·429 전부에서
`llm_path='failed'`, `stage='similarity'`(‘llm’ 아님), `to_be=None`, 결정론 제안 생존.
모킹 17건이 지키려던 규약이 실물에서도 지켜졌다.

**⑤를 실제로 쓰려면**: 유료 등급으로 올리거나, 무료 할당량이 큰 모델을 찾아야 한다.
그때까지 `TERMS_LLM_SELECT=false` 가 기본값인 것이 옳다 — 동음이의는 사용자 선택으로
내려가고, 그게 틀린 답보다 낫다.

### T21d — 무료 모델 재선정: `gemini-3.5-flash-lite`. 예산 재협상은 되돌렸다

⑤가 하는 일은 **후보 5개 중 번호 하나 고르기**다. 무거운 모델이 필요 없다는 데서
출발해 무료 등급 후보를 전부 실측했다(각 1회).

| 모델 | 지연 | JSON | 비고 |
|---|---:|:-:|---|
| `gemini-flash-lite-latest` | 1.05s | O | 코드펜스로 감쌈 · **별칭이라 움직인다** |
| `gemini-3.1-flash-lite` | 1.14s | O | 깨끗한 JSON |
| **`gemini-3.5-flash-lite`** | **1.17s** | **O** | **깨끗한 JSON · 버전 고정 → 채택** |
| `gemini-3.5-flash` | 2.90s | O | |
| `gemini-3.6-flash` | 4.62s | O | 코드펜스 |
| `gemini-3.7-flash` (이전) | 2.46~15.89s | O | 무료 하루 20건 |

**`*-latest` 별칭을 고르지 않은 이유**: `versions.llm_model` 이 판정 재현성의 재료다.
별칭은 가리키는 모델이 바뀌므로, 저장해 둔 값으로 과거 판정을 되짚을 수 없다.

**캐스케이드 실측 (8회, `gemini-3.5-flash-lite`)**

```
llm_path: called 8/8 · ⑤ 확정: USPDX 8/8 (신뢰도 0.85) · 선적 지연 0.96~1.16초
```

`consignee`의 `"ACME TRADING, OR 97201"` 에서 `OR`(오리건)을 읽어 미국 포틀랜드를 골랐다 —
인접 필드로 동음이의를 가리라는 프롬프트 설계가 실물에서 동작했다.

**그래서 예산 재협상(25초)을 되돌렸다.** 1.1초는 기획안 10초 안에 9배 여유로 든다.
`TARGET_NORMALIZE_SHIPMENT_LLM_SECONDS` 와 기준 분기를 지우고 `TERMS_LLM_TIMEOUT` 을
8.0(10초 예산 안)으로 두었다. **기준을 올리는 것보다 모델을 바꾸는 것이 옳은 답이었다** —
잘못된 모델 선택을 예산 완화로 덮으려던 셈이다.

```
acceptance --llm (실제 Gemini): 선적 1건 최대 989.6ms / 목표 10초 — 통과
```

### T21e — ⑤를 켜면 정밀도가 흔들린다 (실행마다)

같은 코퍼스 210건을 ⑤ 켜고 두 번 돌렸다.

| 실행 | 정밀도 | 불일치 | port choice비율 |
|---|---|---|---|
| 1회 | **0.9561** | 5건 | 0.0048 (⑤가 답했다) |
| 2회 | **0.9909** | 1건 | 0.1316 (⑤가 폴백했다) |
| ⑤ 끔 | 0.9909 | 1건 | 0.0238 |

**설계 문서가 "LLM 판정은 재현되지 않는다"고 적어 둔 것이 그대로 나타났다.** ⑤가 답한
실행에서는 사용자 선택이 0.0238 → 0.0048 로 줄었지만(동음이의를 자동 해소) **정밀도가
0.9909 → 0.9561 로 떨어졌다** — 자동 해소한 것 중 일부가 틀렸다.

이것이 설계가 예상한 트레이드오프다. "제안하지 않는 것이 틀리게 제안하는 것보다 낫다"(§1)를
기준으로 보면 **⑤ 기본값을 꺼 두는 것이 맞다.** 켜는 것은 "사용자 선택을 줄이는" 선택이고,
그 대가가 정밀도다. 켤 때는 이 수치를 근거로 결정할 것.

**남은 문제**: ⑤ 켠 정밀도가 실행마다 달라 `test_terms_evaluate.py` 의 임계값 테스트를
LLM 경로에 걸 수 없다. 지금 그 테스트는 `llm=False` 로만 돈다(의도적이다).

### T21f — `.env` 를 만든 것이 테스트를 네트워크에 묶었다

`api/main.py` 가 임포트 시점에 `load_dotenv()` 를 한다. `.env` 에 실제 키와
`TERMS_LLM_SELECT=true` 가 들어가자 **API 테스트가 실제로 Gemini 를 호출했다** —
스위트가 5초 → 26초로 늘고 간헐 실패 1건이 생겼다. 실행마다 결과가 달라지는 테스트가
가장 나쁜 종류다.

`tests/conftest.py` 에 autouse 픽스처를 넣어 스위트 전체에서 LLM 환경변수를 지웠다.
LLM 경로 테스트는 `report.llm_providers._post_json` 을 직접 모킹하므로 영향이 없다.

```
3회 연속: 4 failed, 633 passed, 2 skipped in 2.68s / 2.83s / 2.81s
```

네트워크를 안 타니 원래(5.2초)보다도 빨라졌다.

`acceptance.py`·`terms/evaluate.py` 의 `load_dotenv()` 도 **`__main__` 블록 안으로**
옮겼다 — CLI 는 `.env` 를 읽어야 하지만 임포트만으로 읽으면 안 된다.
(처음에 `from __future__` 앞에 넣어 한 번 깨뜨렸다. `__future__` 는 파일 맨 앞이어야 한다.)

---

## 다음에 할 일

**구현·테스트·측정·문서·출처 검증·Gemini 실연동이 끝났다(T0~T21f).** 남은 것은 셋이다.

### 1. 실무자 출처 검토 — 남은 16건, 그리고 169건의 재확인

**출처 미검증 16 / 185.** T20 이 UNECE·BIC·GLEIF·HTS API 로 전수 대조해 169건을
확인했지만, **LLM 대조는 실무자 검토를 대체하지 못한다.** 실제로 그 한계가 드러난
사례가 있다 — `UOM.PF` 는 과거 EANCOM 등록엔 pallet, 현행 Rec 21 엔 Pen(가축우리)이라
어느 쪽도 확정하지 못해 사전과 코드에서 제거했다.

남은 16건: `UOM.CT`·`PK`·`BX`·`BG`·`DR`·`PCE`(Rec **21** 소속이라 `authority` 문자열이
틀렸다) · `PHR.*` 5건(ISBP 원문 유료) · `SFX.PTE_LTD`·`KK`·`SARL`·`EURL` · `CTR.EITU`.

**Fable 로 교차 검증할 여지가 남아 있다** — T20 은 Fable 세션 한도로 Sonnet 이 돌렸다.
`verified: true` 를 단 169건을 다른 모델이 표본 확인하면 값어치가 있다.
우선순위: 항구 52건 > 단위 18건 > 관행 문구 25건.

이 작업 중 특히 확인이 필요한 것으로 기록된 항목:
`SCVIC` vs `SCPOV`(세이셸) · `KRCHA`(제주) · `CNWUH`(하천항) · `DEBRE` vs `DEBRV` ·
`USSFO` vs `USOAK` · CTR 삭제분 중 `SITU`·`SEKU`·`BEAU`·`GLDU` 복원 여부.

### 2. ⑤단계 정책 결정 — 켤 것인가 (연동 확인은 끝났다)

**실연동은 T21~T21f 에서 확인했다**(§위). 남은 것은 구현이 아니라 **판단**이다.

현재 `.env` 는 `LLM_MODEL=gemini-3.5-flash-lite`, `TERMS_LLM_SELECT=true`,
`TERMS_LLM_TIMEOUT=8` 이고 **실제로 동작한다**(선적 1건 989.6ms ~ 1.17초, 기획안 10초 통과).

결정에 필요한 수치는 §T21e 에 있다:

| | 정밀도 | 사용자 선택 비율 |
|---|---|---|
| ⑤ 끔 | 0.9909 | 0.0238 |
| ⑤ 켬 (⑤가 답한 실행) | **0.9561** | 0.0048 |
| ⑤ 켬 (⑤가 폴백한 실행) | 0.9909 | 0.1316 |

**⑤는 사용자 선택을 줄이는 대신 정밀도를 깎는다.** "제안하지 않는 것이 틀리게 제안하는
것보다 낫다"(§1)가 이 기능의 1원칙이므로 **기본값을 꺼 두는 쪽이 원칙에 맞다.**
켜려면 이 트레이드오프를 감수한다는 결정이 있어야 하고, 그 결정은 코드가 아니라 사람이 한다.

**실행 환경 주의 (실제로 막혔던 것들)**

- **SSL**: venv(macOS python.org)에 CA 번들이 없어 `CERTIFICATE_VERIFY_FAILED` 가 난다.
  `python -m pip install certifi` 후
  `export SSL_CERT_FILE=$(python -c "import certifi;print(certifi.where())")`.
  **`f2venv/bin/pip` 은 엉뚱하게 3.14 로 해석되므로 `python -m pip` 를 쓸 것.**
- **`.env` 는 이미 있다.** `cp .env.example .env` 를 다시 하지 마라 — 켜 둔 토글과
  고정한 모델이 되돌아간다. 키만 바꾸면 된다.
- **무료 할당량은 모델별이다.** `gemini-3.7-flash` 는 하루 20건이라 검증 중 소진됐다.
  `*-flash-lite` 계열이 훨씬 넉넉하다.
- **`list_models()` 로 모델 존재를 판정하지 마라** — 목록과 실제 호출 가능성이 어긋난다.
  `gemini-2.5-flash` 는 목록에 있으나 404 다.

```bash
cd aiService && python -m terms.evaluate --llm
python -m acceptance --llm --count 5
```

### 3. 코드 정리 — 문서로 덮어 둔 것들

우선순위 순. 전부 `f2-standard-terms.md` §남은 것에 근거가 있다.

1. **`apply` 의 중복 `suggestion_id` 방어** — 한 요청에 같은 id 가 둘 이상 실리면
   적용되지 않은 쪽에도 `decision:"accepted"` correction 이 생긴다. 정상 경로에서는
   재현되지 않지만 **게이트웨이가 저장하는 것이 correction 이라** 문서로 덮을 성질이 아니다.
2. **`policy.CLASSES.default_authority` 3건이 카탈로그와 다른 출처를 말한다** —
   `transport_doc`·`delivery`·`practice_phrase` 가 `"ISBP 821"` 인데 카탈로그는 각각
   `"업계 관행 · DCSA"`·`"업계 관행"`·`"ISBP 745"` 다. 항목마다 `authority` 가 필수라
   기본값이 실제로 쓰이지는 않지만, **인용 출처를 두 곳이 다르게 말하는 것**은 아래
   `party_suffix` 와 같은 구조의 문제다.
3. **`party_suffix` 표준형 통일** — T17 이 `validators._SUFFIX_CANON` 쪽(점 없는 약어,
   축약하지 않음)으로 결정하고 근거를 적었다. `Pte., Ltd.` 한 건만 코드가 틀렸다.
   사전 20건 재적재 + `PTE`+`LTD` 예외 + 7개 접미(`PLC`·`LLP`·`K.K.`·`SARL`·`SPA`·
   `EURL`·`OHG`)를 `_LEGAL_SUFFIXES` 에 추가. **그때까지 사전의 접미 항목을 화면에
   인용하지 말 것.**
4. **`volume_unit` label 을 "용적·치수 단위"로** — T17 이 클래스 분리 대신 label 확장으로
   결정. 교정 결과는 한 글자도 안 바뀌고 `message` 가 미터를 "용적 단위"라 부르는 것만
   사라진다.
5. **긴 문구 우선 매칭** — `'full set of original bills'` → `'FULL SET of ORIGINAL bills'`
   처럼 조각만 대문자가 되어 표기가 뒤섞인다. `Original B/L` 오탐과 같은 계열이다.
6. **`exact`/`MIN_CONFIDENCE` 상수 정리** — 둘 다 도달 불가다(§T13b). 지금은 안전한
   방향으로 어긋나 있어 급하지 않다.

### 별도 브랜치 권고 — T19 `PORT_SYNONYMS` 이관

착수 조건: `test_terms_glossary.py::PORT_SYNONYM_GAPS` 가 비는 것(인도 3곳·노르웨이·
사우디 항구 적재). 이관 시 `python -m mlModel.evaluate --count 2000 --seed 42..46` 을
**전/후** 돌려 룰엔진 F1-score 변화를 기록하고, 0.9210 이 내려가면 되돌린다.

### Stage B — 별칭 1,000건

현재 572. 항구 canonical 을 52 → 300 으로 늘리는 것이 주된 몫이다. **건수를 채우려
확신 없는 코드를 넣지 말 것** — 이 브랜치에서 전사본의 절반이 지어낸 코드였고 감사로
걷어냈다(§T5·T6).
