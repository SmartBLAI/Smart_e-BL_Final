# F2 표준 용어 교정 — 인수인계 문서

> **이 문서를 읽는 사람에게.** 이 작업은 여러 LLM 세션에 걸쳐 진행된다. 지금 이어받았다면
> 이 문서로 **무엇을 왜 만드는지**를, [`PROGRESS.md`](PROGRESS.md) 로 **어디까지 됐는지**를
> 파악하라. 두 문서만으로 이어받을 수 있어야 하며, 그렇지 않다면 그건 문서의 결함이다.

- **브랜치**: `feature/f2-standard-language` (`origin/main` 기준, base `fe6364f`)
- **작업 트리**: `feature:f2-standard-language/Smart_e-BL_Backend/`
- **원본 기획안**: `docs/BL_Copilot_기획안_v2.docx` §5.2 (저장소 루트의 `docs/` 가 아니라
  상위 디렉터리 `Smart_e-BL_Backend/docs/` 에 있다)

---

## 0. 무엇을 만드는가

무역 서류 하자의 상당수는 내용 오류가 아니라 **표기 불일치**에서 나온다 —
`부산`/`Pusan`/`PUS`, `KGS` vs `KGM`, `MSKU 123456 5` vs `MSKU1234565`.

F2 는 F1 이 추출한 값을 국제 표준 표기로 정렬해 하자를 원천 차단하고, 동시에
F3(하자 예측)·F6(현실 대조)의 **입력 품질과 매칭 키**를 끌어올리는 전처리다.
처리 흐름 `F1 → F2 → F3 → F4` 중 유일하게 비어 있던 칸이다.

착수 시점 상태: 저장소 전체에서 F2 참조는 `aiService/ruleEngine/checks.py:27-28` 의
주석 한 줄뿐이었다 — *"UN/LOCODE 로 정규화하기 전의 임시 테이블이며 F2(표준 용어
교정)가 들어오면 그쪽으로 옮긴다"*. UN/LOCODE 표·ISO 6346 체크디지트·UN/ECE Rec 20
코드는 어디에도 없었다. 완전 그린필드.

---

## 1. 설계 1원칙 — 이 기능의 실패 방향

`docs/ai-service/remaining-work.md` 가 최우선 결함 유형으로 지목한 것이
**"조용히 틀린 답을 확신을 담아 내놓는" 실패**다. 용어 교정기는 정확히 그 모양의
위험이다. `MSKU1234565` 를 그럴듯하게 만들어 주고, 그 값이 사람 승인을 거쳐 서류에
박히면, 틀렸다는 사실은 은행에서야 드러난다.

전 설계를 아래 세 줄에 종속시킨다. **이 셋과 충돌하는 변경은 하지 마라.**

1. **제안하지 않는 것이 틀리게 제안하는 것보다 낫다.**
   완료 기준이 "재현율보다 정밀도 우선"이다. 신뢰도 `MIN_CONFIDENCE = 0.60` 미만은
   제안을 만들지 않고 `Unevaluated` 에 사유와 점수를 남긴다 — 룰엔진이
   `not_evaluated` 를 1급 상태로 두는 것과 같은 이유다.
2. **결정론으로 판정 가능한 것에 LLM 을 태우지 않는다.**
   컨테이너 번호·단위 코드·상호 접미·HS 형식은 ⑤단계 진입 자체를 금지한다.
   한 번이라도 태우면 "오류 검출률 100%" 를 주장할 수 없다.
3. **어느 경로로 나온 값인지가 값을 따라다닌다.**
   `Summary.source`(`report/narrative.py:29-32`)·`DraftField.source`·`Prediction.model`
   규약을 승계해 `Evidence.stage` 에 `exact|alias|pattern|format|similarity|llm` 을 싣는다.

---

## 2. 확정된 결정 사항

사용자가 직접 고른 것이다. **뒤집지 마라. 다시 물어보지도 마라.**

| 항목 | 결정 | 왜 |
|---|---|---|
| 범위 | **10개 클래스 전부** | 기획안 §10.1 컷라인은 4개지만 사용자가 전체를 택했다 |
| ④ 유사도 | **순수 파이썬 문자 3-gram Dice만** | 의존성·네트워크 0. 2초 예산 안전. 임베딩은 `Ranker` Protocol seam 만 열어둠 |
| ⑤ 후보 선정 | **Gemini API** · 권고 모델 **`gemini-3.5-flash-lite`** (`.env` 의 `LLM_MODEL` 로 지정) | 기존 `report/llm_providers.py` 의 `build_completion`/`GeminiCompletion` **재사용**. 새 프로바이더 코드 금지. 모델은 **실측으로 골랐다** — 어댑터 기본값 `gemini-3.7-flash` 는 지연 2.5~15.9초에 무료 하루 20건이라 예산을 넘겼고, lite 는 선적 1건을 1초 안팎에 끝낸다(§PROGRESS T21d). **`*-latest` 별칭은 쓰지 마라** — `versions.llm_model` 이 재현성의 재료다. **코드에 모델명을 박지 마라**: 초안이 `gemini-2.5-flash` 로 적었다가 낡았고(그 모델은 404 다) 어댑터 기본값도 이미 한 번 바뀌었다 |
| 영속성 | **무상태 유지** | `docs/ai-service/api.md` 규약. accept/reject 는 순수 함수, 조직 사전·선적 예외는 요청 본문 `overrides` 로 주입 |
| 작업 위치 | 신규 클론 + `origin/main` 기준 브랜치 | F1/F4 트리와 격리 |

### 모델 라우팅 (사용자 지정)

| 종류 | 모델 | 무엇을 맡나 |
|---|---|---|
| **설계** | Opus | 구조 판단, 계약 문서, 캐스케이드 정책, LLM 프롬프트 설계 |
| **코딩** | Sonnet | 모듈 구현, 테스트 작성, API 배선 |
| **기계** | Haiku | YAML 카탈로그 전사, 코퍼스 라벨링, 보일러플레이트 |
| **검증** | Fable | 회귀 실행, 정밀도·성능 실측, 전사 기록, 리뷰 |

§7 태스크 표에 종류가 붙어 있다. 새 에이전트에 넘길 때 "먼저 읽을 것" 열을 그대로
프롬프트에 실어라 — 대화 맥락 없이도 착수할 수 있게 쓰여 있다.

---

## 3. 모듈 배치 — `aiService/terms/`

패키지명이 `standardTerms` 가 아닌 이유: 3계층 중 둘(조직 사전·선적 예외)은 정의상
**비표준**이고, 그 둘을 표준과 구분해 표기하는 것이 이 기능의 핵심 요건이다.
이름에 "standard" 를 박으면 오버라이드 경로가 부수적으로 읽힌다.

```
aiService/terms/
  __init__.py      ~70 L   정렬된 __all__ 재노출 (ruleEngine/__init__.py 형태)
  keys.py          ~90 L   normalize_key/loose_key. 의존성 re·unicodedata 뿐
  types.py        ~260 L   Suggestion·GlossaryTerm·Evidence·Candidate·Correction·
                           NormalizeResult·Notice·Unevaluated·FieldRef·Versions·Stats
  policy.py       ~180 L   클래스 정의, 필드→클래스 매핑, 허용 단계표, 신뢰도 상수
  glossary.py     ~300 L   카탈로그 로드·전수 검증·GlossaryStack·인덱스 빌드
  validators.py   ~330 L   ISO 6346 / UN/ECE Rec 20 / Incoterms 장소 / HS·HSK / LOCODE
  similarity.py   ~130 L   3-gram Dice + Ranker Protocol (임베딩 seam)
  cascade.py      ~400 L   Normalizer — 6단계 본체. 이 패키지의 engine.py
  llm_select.py   ~280 L   ⑤단계. LLMSelector/프롬프트/JSON 파싱/주입 방어
  apply.py        ~170 L   accept·reject 순수 함수, suggestion_id 파생, span 치환
  evaluate.py     ~200 L   정밀도·재현율 CLI (mlModel/evaluate.py 형태)
  catalogs/std-2026.1/{manifest,glossary,locode}.yaml
  eval/corpus.yaml
```

대응 관계: `glossary.py`↔`ruleEngine/engine.py`, `catalogs/*.yaml`↔`rules.yaml`,
`cascade.py`↔`checks.py`. 룰엔진을 읽어 본 사람이 처음 보는 파일에서 무엇이 어디
있는지 짐작할 수 있어야 한다.

**requirements.txt 를 바꾸지 마라.** `hashlib`·`unicodedata`·`re`·`json`·
`collections.Counter` 는 표준 라이브러리, PyYAML 은 이미 있다. 새 의존성은 폐쇄망
온프레미스 프로파일(기획안 3.1 ③)을 깬다.

---

## 4. 핵심 설계

### 4.1 6단계 캐스케이드

| 단계 | 이름 | 하는 일 | 신뢰도 |
|---|---|---|---|
| 0 | `format` | 이미 표준인데 대소문자·공백만 다름 (NFKC·공백 축약) | 0.92 |
| ① | `exact` | `normalize_key(값)` == canonical 키 | 0.99 |
| ② | `alias` | 별칭 인덱스 조회 | 0.95 |
| ③ | `pattern` | 클래스별 정규식·번호 체계 규칙 | 0.97 (결정론 검증 통과) / 0.90 |
| ④ | `similarity` | 클래스 후보 풀에서 3-gram Dice 상위 5 | min(0.88, 0.55+0.35·s) |
| ⑤ | `llm` | 후보 중 선택 (Gemini) | min(**0.85**, 0.55+0.30·s) |
| ⑥ | — | 제안 카드 생성 · 영향 범위 · id | — |

⑤ 상한 0.85 가 `format`(0.92)보다도 낮은 것은 **의도**다 — LLM 이 결정론 경로를
신뢰도로 이기는 상황을 구조적으로 막는다.

**정지 조건**
- ①②③ 은 맞으면 즉시 종결. 다음 단계로 내려가지 않는다.
- `to_be == as_is` 면 제안을 만들지 않는다. 무의미한 카드가 목록을 채우면 사람이
  카드를 읽지 않게 되고, 그 순간 승인 게이트가 형식이 된다.
- ④ 최고 점수 < `SIMILARITY_FLOOR=0.55` → 제안 없음, `Unevaluated` 에 사유와 점수.
- ④ 후보 정확히 1건이고 점수 ≥ `SINGLE_CANDIDATE_FLOOR=0.85` → ⑤ 건너뛰고 종결.
- ④ 후보 2건 이상 → ⑤로. ⑤ 금지 클래스거나 LLM 미설정/실패면 `requires_choice=True`.
- 최종 신뢰도 < `MIN_CONFIDENCE=0.60` → 제안 없음.

### 4.2 클래스별 허용 단계 — ⑤ 금지가 핵심

| 클래스 | format | ① | ② | ③ | ④ | ⑤ LLM |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| `port` 항구·지명 | O | O | O | O | O | O *(동음이의 판별만)* |
| `transport_doc` 운송서류 용어 | O | O | O | O | O | O |
| `delivery` 인도 관련 | O | O | O | O | O | O |
| `practice_phrase` 관행 문구 | O | O | O | O | O | O |
| `price_term` 가격조건 | O | O | O | O | O | O *(장소 병기 판별만)* |
| `party_suffix` 당사자 상호 | O | — | — | **O만** | — | **금지** |
| `qty_unit` 수량 단위 | O | O | O | O | — | **금지** |
| `volume_unit` 용적 단위 | O | O | O | O | — | **금지** |
| `container_no` 컨테이너 번호 | — | — | — | **O만** | — | **금지** |
| `hs_code` 품목 분류 | — | — | — | **O만** | — | **금지** |
| `party_name`/`goods` 고유명사·품명 | **O만** | — | — | — | — | **금지** |

`qty_unit`/`volume_unit` 이 ④까지 막힌 이유: Rec 20 코드 집합은 **닫혀 있다**.
사전에 없으면 "비슷한 단위"가 아니라 **모르는 단위**이고, 답은 추측이 아니라
`Notice(kind="not_covered")` 다.

> **이 표는 `policy.py` 안의 상수(코드)다. YAML 이 아니다.**
> `rules.yaml` 을 데이터로 둔 근거는 "화면·리포트가 조문을 인용해야 한다"였다 —
> 인용 대상이다. 반면 "컨테이너 번호는 LLM 에 보내지 않는다"는 **안전 불변식**이다.
> YAML 이면 사전 편집자가 한 줄 고쳐 컨테이너 번호를 Gemini 로 보낼 수 있고 리뷰 없이
> 배포된다. 코드면 diff 에 남고 테스트가 지킨다.

대신 로더가 상호 검증한다: 카탈로그의 모든 `category` 는 `policy.CLASSES` 에 있어야
하고, `policy.CLASSES` 중 사전이 필요한 클래스는 카탈로그에 항목이 있어야 한다.

### 4.3 유사도 — 문자 3-gram Dice

```python
NGRAM_N, SIMILARITY_FLOOR, SINGLE_CANDIDATE_FLOOR, TOP_K = 3, 0.55, 0.85, 5

def _grams(key, n=3):
    """앞뒤 공백 1개씩 패딩 — 어두·어말이 신호가 되어
    'BUSAN'과 'PUSAN'이 'USAN'만으로 붙지 않는다."""
    padded = f" {key} "
    return Counter(padded[i:i+n] for i in range(len(padded)-n+1))

def dice(a, b):
    A, B = _grams(a), _grams(b)
    return 2*sum((A & B).values()) / (sum(A.values()) + sum(B.values()) or 1)
```

**다중집합(`Counter`)** 이다 — 집합이면 `AAA` 와 `AAAAAA` 가 1.0 이 된다.
질의 키는 `loose_key`, 풀은 canonical + 전 별칭의 `loose_key`, term 당 점수는 최대값.
풀의 gram Counter 는 카탈로그 로드 시 1회 계산해 인덱스에 캐시한다(룰 카탈로그를
기동 시 1회만 읽는 것과 같은 이유).

`Ranker` Protocol + `Normalizer(ranker=...)` 주입, `Versions.ranker` 가 어느 것이
돌았는지 싣는다. 임베딩 구현이 들어올 자리는 이 Protocol 뿐이며, 그때도 의존성은 그
구현 파일 안에만 들어간다.

### 4.4 ⑤단계 Gemini — 주입 방어가 구조에 산다

`report/llm_providers.py` 를 **그대로** 쓴다. 새 프로바이더 코드를 쓰지 않는다.
JSON 규율은 호출부에 산다(`ocr/llm_extract.py` 와 동일) — `_FENCE`/`_parse_json_object`
는 그 파일에서 **복사**한다(임포트하지 않는다: `ocr`↔`terms` 결합을 만들지 않기 위해.
20줄 중복이 패키지 간 결합보다 싸다).

**응답은 후보 인덱스만 담는다.**

```json
{"selections":[{"item_id":"f3","choice":1,"abstain":false,"reason":"인접 양하항이 한국"}]}
```

이것이 주입 방어의 **본체**다. 자유 문자열 `to_be` 를 받지 않으므로, 주입이 100%
성공해도 모델이 할 수 있는 최대치는 "우리가 이미 만든 후보 5개 중 잘못된 것 고르기"
이고 그건 사람 승인 게이트가 잡는다. 파싱 후 `1 <= choice <= len(candidates)` 를
검사해 어긋나면 그 항목을 폐기한다.

보조 3중:
- **구획** — 서류 유래 값은 전부 `<<< >>>` 로 감싸고, 값 안의 `<<<`/`>>>` 는 제거
- **탐지 → Info 경보** — `_INJECTION_MARKERS` (`ignore previous`, `disregard`,
  `system:`, `assistant:`, `무시하`, `당신은 이제`, `` ``` ``, `<|`, `‮`) 를
  값에서 찾으면 `Notice(kind="injection", severity="info")`.
  **처리를 중단하지 않는다** — 정상 화물 명세에 우연히 걸릴 수 있고, 중단하면 주입
  시도가 곧 서비스 거부가 된다.
- **크기 상한** — 값당 200자, 인접 필드 4개, 항목당 후보 5개, 호출당 20항목

**배치: 선적 1건당 호출 1회.** 필드당 부르면 8건 × 2초 = 16초로 10초 예산을 넘긴다.
묶으면 lite 모델 기준 1초 안팎. `TERMS_LLM_TIMEOUT=8` 을 별도로 둔다(`LLM_TIMEOUT=20` 은
10초 예산보다 크다). 재시도 없음(어댑터가 원래 안 한다).
20건을 넘으면 상위 20건만 보내고 나머지는 `requires_choice=True` + `Notice(not_covered)`
— 조용히 자르면 "LLM 이 판단했다"와 "예산 때문에 못 물었다"가 구분되지 않는다.

**실패 시**: 200 유지, 결정론 제안은 살아 나가고 해당 항목만 `requires_choice=True`.
`evidence.stage` 는 `"llm"` 이 **아니라** `"similarity"` 로 남는다 — `LLMNarrator`
폴백이 `source="template"` 를 남기는 것과 같은 이유. 클래스 이름으로 출처를 판정하면
실패했는데도 'AI 판정'이라고 표기하게 되고, 그 값이 화면에 그대로 찍힌다.
`stats.llm_path` 가 `not_called|called|failed` 를 싣는다.
기본값 **꺼짐**(`TERMS_LLM_SELECT=false`, `LLM_STRUCTURED_EXTRACT=false` 선례).

### 4.5 제안 카드 — 기획안 §5.2 에 1:1

```python
@dataclass
class Suggestion:
    suggestion_id: str            # 결정론적 파생 (§4.7)
    field: FieldRef               # doc, field, doc_id, span
    as_is: str
    to_be: Optional[str]          # requires_choice 면 None
    term_class: str
    evidence: Evidence            # authority, term_id, glossary_version, tier,
                                  # stage, verified=False, diverges_from_standard
    confidence: float
    impact: List[FieldRef]        # 영향 범위
    candidates: List[Candidate] = field(default_factory=list)
    requires_choice: bool = False
    message: str = ""
```

**`requires_choice=True` 일 때 `to_be` 는 반드시 `None`.** 상위 후보를 넣어 두면 UI 가
그걸 기본값으로 적용해 버리고, 기획안이 못박은 "판별 불가 시 후보 나열하여 사용자
선택(**임의 선택 금지**)"이 그 지점에서 깨진다. 값을 비우면 UI 는 선택 없이 적용할 수
없다. `requires_choice` 제안은 `scope="all"` 일괄 적용에서도 **제외**한다 — 금지가
일괄에서 뚫리면 금지가 아니다.

`FieldRef.span` 은 처음부터 넣는다. 관행 문구·컨테이너 번호·HS 코드는 필드 전체가
아니라 **자유서식 안의 조각**이라, span 없이는 적용 자체가 불가능하고 나중에 `apply`
를 통째로 다시 써야 한다.

#### span 계약 — 하나뿐이고 예외가 없다

> **`span` 이 있으면 `as_is` 는 그 자리의 부분 문자열이고, `to_be` 는 그 자리만 대신한다.**
> `apply` 가 하는 일은 `value[:start] + to_be + value[end:]` 뿐이다.
> `span` 이 `None` 이면 `as_is` 는 필드 값 전체이고 `to_be` 가 전체를 대신한다.

불변식: `span` 이 있을 때 항상 `value[start:end] == as_is`. 테스트로 고정한다.

이 계약을 흔들면 조용히 값이 망가진다. 실제로 한 번 깨졌었다 — 단위 경로가 `span` 은
단위 토큰(`"KGS"`)을 가리키면서 `to_be` 에는 필드 값 전체(`"1,234.50 KGM"`)를 담아,
치환 결과가 `"1,234.50 1,234.50 KGM"` 이 됐다. **수치가 복제된 채로 사람 승인 화면까지
갔을 것이다.**

화면 표기가 불친절해 보인다는 이유로(카드에 `KGS → KGM` 만 뜬다) 계약을 바꾸지 마라.
그건 UI 가 `field` 이름과 함께 렌더링해서 풀 문제다. 반대로 계약을 지키면 **수치가 구조적으로
보존된다** — span 이 숫자를 덮지 않으므로 `apply` 가 잘못 짜여도 수치를 건드릴 수 없다.
`party_suffix` 가 상호 본체를 지키는 것과 같은 논리다: 규칙으로 막는 것과 구조로 막는 것은
다르다.

### 4.6 용어사전 — 3계층을 무상태로

`rules.yaml` 규약 승계: `version`(파일 스키마) + `catalog_version`(판정 재현성 도장) +
`effective_date` 헤더. 로더는 **문제를 전부 모아 한 번에** 던진다:
필수 키 누락 · `term_id` 중복 · **정규화 키 충돌** · 모르는 `category` ·
`deprecated_by` 미존재 · `catalog_version`↔디렉터리명 불일치 · 별칭 중복.

> 키 충돌 검사가 핵심이다 — 별칭 하나가 조용히 다른 항목을 가리면 결과는 예외가
> 아니라 **틀린 교정**이다. 항구 클래스만 동음이의로 허용하되 `country` 가 양쪽 다
> 채워져 있어야 한다(없으면 오류).

주입 seam: `Glossary(terms=[...])` 가 리스트를 직접 받는다 — `RuleEngine(rules=[...])`
와 같은 이유로, 테스트가 파일을 건드리지 않는다.

3계층은 요청 본문이 싣고 온다:

```json
"overrides": {
  "organization": {"id":"org-42","version":"org-2026.3","terms":[...]},
  "shipment":     {"id":"SHP-2026-0417","terms":[...]}
}
```

`GlossaryStack([standard, organization, shipment])` 은 **가장 구체적인 계층부터**
조회하고, 표준에도 같은 키가 있고 canonical 이 다르면 `Evidence.diverges_from_standard`
에 표준 값을 적는다 — "하위가 상위를 덮어쓰되 표준과 다름을 리포트에 표기" 요건이다.
오버라이드는 표준과 **같은 검증기**를 타되, 깨지면 400 이지 서버가 죽지는 않는다
(요청 오류 vs 서버 구성 오류).

**판정 재현성**: 카탈로그 **여러 버전을 빌드에 동봉**(`catalogs/std-2026.1/`,
`std-2026.2/` …), 요청의 `glossary_version` 으로 선택. 기동 시 **모든** 버전을
검증한다(기본 버전만 검증하면 옛 버전이 조용히 썩는다). 인덱스 빌드는 실제 쓰이는
버전만 지연 수행. `manifest.yaml` 의 `deprecates:` 로 계보를 남긴다.

**`verified: false` 가 기본**(`rules.yaml` 머리말 규약 상속). 전파 경로:
YAML → `GlossaryTerm.verified` → `Evidence.verified` → `Suggestion.message` 끝에
`" (출처 미검증)"` → `GET /glossary` 의 `unverified_term_count` → 기동 로그.
`GET /rules` 의 `unverified_source_count` 와 완전히 같은 모양이다.

**적재량 — Stage A(이번 브랜치) ~660 별칭 / 182 canonical.** "1,000건"은 Stage B
목표로 명시한다. 항구 품질은 건수가 아니라 동음이의 커버리지에서 나오기 때문이다.

| 클래스 | canonical | 별칭 계 |
|---|---:|---:|
| port (UN/LOCODE) | 60 | 240 |
| practice_phrase (ISBP) | 25 | 75 |
| party_suffix | 20 | 80 |
| qty_unit / volume_unit (Rec 20) | 18 | 90 |
| transport_doc / delivery | 18 | 72 |
| price_term (Incoterms) | 11 | 44 |
| hs_code (예시) | 30 | 60 |
| container_no (선사 접두) | — | 40 |
| **계** | **182** | **~660** |

항구 60건: 한국 15 · 중국 10 · 일본 8 · 동남아 7 · 미주 10 · 유럽 10.
**동음이의 6쌍**(PORTLAND·VICTORIA·VALENCIA·NEWCASTLE·SANTIAGO·SAN JOSE)은 상대
항구를 반드시 함께 넣는다 — 사전에 후보가 하나뿐이면 동음이의 처리 경로가 절대
발동하지 않고, 그 코드는 테스트 없는 죽은 코드가 된다.

### 4.7 `suggestion_id` — 저장 없는 결정론적 파생

```python
SUGGESTION_ID_PREFIX = "sg1"   # share.py 의 VERSION = "v1" 과 같은 이유

def suggestion_id(s) -> str:
    payload = json.dumps([s.evidence.glossary_version, CASCADE_VERSION,
                          s.field.doc, s.field.doc_id or "", s.field.field,
                          list(s.field.span or ()), normalize_key(s.as_is),
                          s.to_be or "", s.evidence.term_id or "",
                          s.evidence.stage, s.term_class],
                         ensure_ascii=False, separators=(",", ":"))
    return f"{SUGGESTION_ID_PREFIX}_{hashlib.blake2s(payload.encode(), digest_size=12).hexdigest()}"
```

- **HMAC 이 아니라 순수 해시다.** `share.py` 의 서명키는 프로세스마다 달라질 수 있어
  (`secret_is_ephemeral`) 재현성이 깨진다. 목적은 위조 방지가 아니라 **같은 입력에
  같은 이름**이다. 표준 라이브러리 `hashlib` 만 쓴다.
- 카탈로그 버전이 해시에 들어가므로 사전을 올리면 id 가 **전부 바뀐다** — 옛 결정이
  새 제안에 조용히 재사용되지 않고 시끄럽게 깨진다. 그 쪽이 옳다.
- `impact` 는 해시에 **넣지 않는다** — 요청에 실린 서류 수에 따라 달라진다.
- `/normalize/apply` 는 받은 제안에서 id 를 재파생해 대조하고, 어긋나면 **400**
  ("제안이 변조되었거나 사전 버전이 다릅니다"). `share.py` 가 서명 깨짐을 404 로
  내는 것과 자리가 다르다 — 여기는 본문 불일치라 요청 오류다.

### 4.8 엣지 케이스

**동음이의 항구** — 먼저 맞는 것에서 멈춘다:
1. 값 안의 국가 신호 (`PORTLAND, USA` / `PORTLAND, OR` / `PORTLAND, AUSTRALIA`).
   국가명·ISO2·미국 주 약어 표를 `locode.yaml` 에 함께 싣는다.
2. **인접 필드의 국가** — 상대 항구·`place_of_issue`·`shipper`/`consignee` 주소에서
   국가를 뽑아 후보 중 **다른** 국가인 것을 남긴다(같은 국가로 좁히는 게 아니라 반대 —
   선적항과 양하항이 같은 나라인 경우가 오히려 드물다). 후보를 1개로 못 줄이면
   적용하지 않는다.
3. L/C 44E/44F 가 지정한 항구의 국가.
4. ⑤ LLM 에 후보와 인접 필드를 넘겨 고르게 한다.
5. 그래도 안 되면 `requires_choice=True`, `to_be=None`, `candidates=[...]`.

**L/C 문언 우선** — 해당 필드에 대응하는 L/C 값이 **존재하면** 사전 기반 교정
(①②③④⑤)을 하지 않고 `format` 만 허용,
`Notice(kind="lc_wording", severity="info")` 로 안내만 표시.
L/C 는 세 경로로 안다: 요청의 `lc` → `LCTerms.from_dict`(`/verify` 와 완전히 같은
형태) · `lc_raw_tags` → `ruleEngine/mt700.parse`(47A 자유서식이 `unmapped` 로 온다) ·
필드별 매핑표(`port_of_loading`↔44E, `port_of_discharge`↔44F, `consignee`,
`notify_party`, `description_of_goods`↔45A, `incoterms`).

> 이렇게까지 보수적인 이유: 기획안이 "교정 제안하지 않고 'L/C 문언 준수' 안내만
> 표시"라고 못박았고, 서류 값이 L/C 와 어긋나는지는 **이미 F3 의 `match_place`**
> (`checks.py`)가 잡는다. F2 가 같은 자리에 다른 판단을 내면 화면에 서로 모순되는
> 두 카드가 뜬다.

**고유명사·품명 절제** — `party_name`(shipper·consignee·notify_party 의 **본체**)과
`goods`(description_of_goods·marks 의 품명 부분)는 `format` 단계만.
허용: 연속 공백 축약, 앞뒤 공백 제거, NFKC, `_LEGAL_SUFFIXES` 접미 표준화.
금지: 사전 조회·유사도·LLM·철자 교정·약어 확장.
`party_suffix` 규칙은 `span` 이 **접미 토큰 위치만** 가리키므로 `apply` 가 본체를
건드릴 수 없다 — **구조로 막는다**.
예: `"GAE WOON CO.,LTD"` → span=(9,16)만 `"Co., Ltd."` 로, `"GAE WOON"` 은 바이트
단위 보존.

### 4.9 결정론 검증기 — 100% 를 주장할 수 있는 것과 없는 것

| 항목 | 100% | 조건 |
|---|:-:|---|
| 단위 토큰의 Rec 20 소속 여부 | **O** | 집합 조회 |
| HS 코드 형식(자릿수·구분자) | **O** | 형식만 |
| LOCODE 코드 형식 | **O** | 형식만. 실재 여부는 사전 커버리지 |
| 컨테이너 체크디지트 | **조건부 O** | ISO 6346 의 `(sum%11)%10` 접힘 사각지대 명시 |
| 항구 판별 | **X** | 문맥 의존 |
| Incoterms 장소 적정성 | **X** | 장소 **누락** 검출은 O, 장소가 **옳은지**는 X |
| 상호 표기 | **X** | 접미 정규화만 결정론 |

**ISO 6346**: `total = Σ value(ch) · 2^i`, `check = (total % 11) % 10`,
형식 `^[A-Z]{3}[UJZ]\d{6}\d$`, 문자값은 11의 배수(11·22·33)를 건너뛴다
(A=10, B=12, …, K=21, L=23, …, U=32, V=34, W=35, X=36, Y=37, Z=38).
장비 구분자가 `U|J|Z` 가 아니면 컨테이너 번호가 아니다 → 클래스 오판이므로 제안하지 않는다.

> **정직하게 적어 둘 것**: 마지막 `% 10` 때문에 나머지 10과 0이 같은 체크디지트로
> 접힌다. ISO 6346 자체의 알려진 사각지대이며, 단일 문자 오류 검출률은 100% 가 아니라
> 그 사각지대만큼 못 미친다. `f2-standard-terms.md` 에 명시한다 — 100% 라고 써 놓고
> 아닌 것이 이 프로젝트가 가장 싫어하는 실패 방향이다.

**Rec 20 핵심 6개**: `KGM`(KG/KGS/K.G.S/킬로) · `TNE`(MT/M.T./톤) · `LBR` ·
`MTQ`(CBM/M3/M³/입방미터) · `LTR` · `MTR`.
포장 단위(`CT` carton, `PK` package, `BX` box, `PCE` piece)는 Stage A 에 넣되 전부
`verified: false` 이고 별칭에 흔한 오표기(`CTN`·`CTNS`·`PKG`·`PCS`)를 포함한다.

**Incoterms 2020** 은 **장소 병기 필수**. `FOB BUSAN` → `FOB Busan (Incoterms 2020)`
(장소는 Title Case, 조건은 대문자). 장소 누락 시 **지어내지 않고** `_PLACE_SIDE`
표(EXW/FCA/FAS/FOB→`port_of_loading`, CFR/CIF/CPT/CIP/DAP/DPU/DDP→`port_of_discharge`)가
가리키는 인접 필드에서 후보 1건을 만들어 `requires_choice=True`. 인접 필드도 비었으면
`Notice(kind="not_covered", severity="warning")`.

**HS/HSK**: 국제 6단위 `nnnn.nn` 형식 검증만. HSK 10단위 `nnnn.nn-nnnn` 은
**관세율표 미적재로 뒤 4자리를 만들어내지 않는다** → `Notice(not_covered, info)`.

---

## 5. API 표면 — 평면 라우트 유지

기존 라우트는 전부 평면(`/verify`·`/report`·`/rules`·`/lc/mt700`)이고 기획안의
`/api/v1` 프리픽스와 이미 어긋나 있다. F2 만 프리픽스를 붙이면 같은 서비스에 두
규약이 생긴다. **평면을 따르고 어긋남을 `api-spec.md` 에 명시한다** — 프리픽스는
게이트웨이가 정한다.

| 메서드 | 경로 | 기능 | 화면 |
|---|---|---|---|
| POST | `/normalize` | 필드 배열 → 제안 배열 | S3 초안 편집기 |
| POST | `/normalize/apply` | 승인 반영 (순수 함수) | S3 |
| POST | `/normalize/reject` | 거절 사유 기록용 Correction 생성 | S3 |
| GET | `/glossary` | 적재 사전 요약·버전·미검증 건수 | S11 설정 |
| POST | `/glossary/validate` | 조직 사전 후보 검증 (게이트웨이가 저장 전 호출) | S11 |

**상태 코드**
- **200** — 정상. **LLM 실패도 200 이다** (결정론 제안은 살아 나간다)
- **400** — `documents`/`bl` 둘 다 빔 / 없는 `glossary_version`(가용 목록을 detail 에
  나열) / `suggestion_id` 불일치 / 조직 사전 형식 오류
- **422** — Pydantic 스키마 불일치 (`scope`·`reason` enum 포함)
- **503 은 없다** — F2 에 선택 의존성이 없다. PyYAML 은 이미 필수이고, 카탈로그가
  깨지면 기동이 죽는다. LLM 미설정은 정상 경로다.

`ApplyResponse.unapplied` 가 필요한 이유: 사람이 S3 에서 값을 고친 뒤 오래된 제안을
승인하면 `as_is` 가 더 이상 문서에 없다. 조용히 건너뛰면 사용자는 적용된 줄 안다.

### 기획안을 그대로 못 맞추는 것 — 게이트웨이 계약

| 기획안 요구 | aiService 가 하는 것 | 게이트웨이가 해야 하는 것 |
|---|---|---|
| `POST /api/v1/glossary` (사전 등록) | `/glossary/validate` 로 검증만 | 조직 사전 저장·버전 관리 |
| `/normalize/{id}/accept\|reject` | `/normalize/apply`·`/reject` 가 본문으로 받음 | id→제안 조회 후 본문 전달 |
| 거절 사유 **기록** | `Correction` 객체 생성해 반환 | 저장 |
| 영향 범위 = 선적 전체 | 요청에 실린 서류 안에서만 계산 | 선적의 전 서류를 한 요청에 실을 것 |
| 판정 재현성 (3버전 저장) | 응답 `versions` 3종 + `ranker` | 저장 + 재현 시 되쏨 |
| 조직 사전·선적 예외 | `overrides` 로 주입받음 | 저장·주입 |
| 과거 버전 재현 | 카탈로그 여러 버전 동봉 | 이미지에서 옛 버전 디렉터리를 지우지 말 것 |

> **LLM 경로는 재현되지 않는다.** 모델이 비결정론이다. 대응: (a) LLM 을 탄 제안은
> `evidence.stage == "llm"` 으로 표시, (b) 게이트웨이는 그 제안의 후보 목록 전체를
> 저장, (c) 재현 요청은 "당시 후보와 당시 선택"을 되읽는 것이지 LLM 재호출이 아니다.

---

## 6. 기존 코드와의 관계 — 두 가지는 **건드리지 않는다**

### 6.1 `PORT_SYNONYMS` 이관 보류

`checks.py:27-28` 주석이 "F2 가 들어오면 옮긴다"고 쓰고 있지만 **이번 브랜치에서
옮기지 않는다.** `_tokens_match`(`checks.py:523-537`)가 `PORT_SYNONYMS` 로 토큰을
확장하는데, 사전 기반으로 갈면 동의어가 9쌍 → 60+ 집합으로 커진다 → `match_place` 가
관대해진다 → **위반이 줄어든다** → `remaining-work.md` 가 보고하는 룰엔진 단독
F1 0.9210 이 움직인다. 그 변화가 F2 커밋에 묻히면 원인 추적이 안 되고, "룰이 조용히
관대해져 하자를 놓치는" 것은 이 프로젝트가 최악으로 치는 실패 방향이다.

대신 **정합성 테스트**를 넣는다 —
`test_terms_glossary.py::Test기존_동의어표와의_정합성::test_checks_PORT_SYNONYMS_는_전부_사전이_덮는다`.
이관은 T19 로 분리하고 착수 조건에
`python -m mlModel.evaluate --count 2000 --seed 42..46` 의 이관 전/후 수치 기록을 넣는다.

### 6.2 세 `_normalize` 통합 보류

| 위치 | 정규식 | 남기는 것 | 왜 |
|---|---|---|---|
| `ocr/doc_types.py:212` | `[^A-Z0-9가-힣 ]` | 한글 | `"선하증권"` 이 서류 종류 판별 키워드다 |
| `ocr/field_parser.py:_locate_anchor` | `[^A-Z0-9/ ]` | `/` | `"B/L NO"` 앵커가 슬래시를 쓴다 |
| `ocr/draft.py:_normalize` | `[^A-Z0-9 ]` | 둘 다 버림 | 라벨 어휘 대조 |

셋이 다른 건 **버그가 아니라 서로 다른 요구**다. 통합하면 최소 두 호출부의 동작이
바뀌는데 그건 F1 의 가장 뜨겁고 가장 잘 테스트된 경로다. 얻는 것 3줄, 잃는 것 F1
회귀 위험. 남는 장사가 아니다.

그리고 **F2 는 통합해도 자기 키가 필요하다** — `normalize_key` 는 한글(`부산`·`서렌더`)과
점(`8471.30`·`F.O.B`)을 둘 다 남겨야 한다. 셋 중 어느 것도 아니다.

```python
def normalize_key(text):    # 비교용. 한글·숫자·점을 남긴다
    s = unicodedata.normalize("NFKC", text or "").upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9가-힣.]+", " ", s)).strip()

def loose_key(text):        # 유사도용 뼈대. 'F.O.B' == 'FOB'
    return re.sub(r"[^A-Z0-9가-힣]+", "", normalize_key(text))
```

두 보류 모두 사유와 재검토 조건을 `keys.py` docstring 과 `remaining-work.md` 에 남긴다.

### 6.3 배선

`api/main.py` 에 지연 싱글턴 `glossary()` 추가(기존 `engine()`/`predictor()` 형태),
`lifespan` 에 로드 로그 + 미검증 건수 경고 + `TERMS_LLM_SELECT=true` 인데 LLM 미설정
시 경고. `/health` 에 `glossary_version`·`glossary_terms` 추가(기존
`test_룰_적재_수를_보고한다` 는 `rules_loaded >= 20` 만 보므로 안전).

`_env_flag` 는 `ocr/pipeline.py:27` 에 이미 있지만 **임포트하지 말고** `terms/policy.py`
에 같은 3줄을 둔다(패키지 간 결합보다 3줄 중복이 싸다는 §4.4 와 같은 판단).

`.env.example` 4줄 추가 — 기존 규약대로 **비워 뒀을 때의 실패 모드**를 주석으로:

```bash
# F2 표준 용어 교정 — ⑤단계(LLM 후보 선정)를 켠다.
# 기본이 꺼짐인 이유는 외부 API 호출이기 때문이다. 꺼 두면 유사도 후보를
# 사용자에게 나열해 직접 고르게 한다 — 제안이 사라지는 것이 아니라
# 자동 선정만 사라진다.
TERMS_LLM_SELECT=false
# 판정에 쓸 표준 사전 버전. 비우면 effective_date 가 가장 최신인 것을 쓴다.
TERMS_GLOSSARY_VERSION=std-2026.1
# ⑤ 전용 권고 모델. 후보 5개 중 번호 하나 고르는 일이라 lite 로 충분하고,
# 무거운 모델은 무료 할당량(3.7-flash 는 하루 20건)과 지연에서 막힌다.
# `*-latest` 별칭은 쓰지 말 것 — versions.llm_model 이 재현성의 재료다.
LLM_MODEL=gemini-3.5-flash-lite
# ⑤단계 한 번에 묶어 물을 항목 수. 늘리면 선적 10초 예산이 위험해진다.
TERMS_LLM_MAX_ITEMS=20
# ⑤단계 타임아웃(초). LLM_TIMEOUT(20)을 그대로 쓰면 선적 10초 예산을 넘긴다.
TERMS_LLM_TIMEOUT=8
```

**F6 을 위해** `terms/__init__.py` 의 `__all__` 에 `normalize_key`·`loose_key`·
`canonical_of` 를 **명시 노출**한다. F6 은 HTTP 를 타지 않고
`from terms import canonical_of` 로 같은 코드를 쓴다 — 두 기능이 다른 정규화를 쓰면
매칭이 조용히 어긋난다.

---

## 7. 태스크 표

경로는 전부 `feature:f2-standard-language/Smart_e-BL_Backend/` 기준.
상태는 [`PROGRESS.md`](PROGRESS.md) 에 있다.

| # | 태스크 | 종류(모델) | 크기 | 의존 | 먼저 읽을 것 |
|---|---|---|---|---|---|
| **T0** | 클론 + 브랜치 + 의존성 + pytest 기준선 + 이 문서들 | 기계(Haiku) | S | — | 계획서 |
| **T1** | **설계 문서 선작성** — `docs/ai-service/f2-standard-terms.md` (API·테스트 절 제외). **T2~T12 의 계약서** | 설계(Opus) | L | T0 | `f3-defect-prediction.md`, `api.md`, `remaining-work.md`, `ruleEngine/rules.yaml` 머리말 |
| **T2** | `terms/keys.py` + `terms/types.py` — §4.5 dataclass 전부 + `to_dict()` + `__all__` | 코딩(Sonnet) | M | T1 | `ruleEngine/types.py`, `ocr/types.py`, `ocr/draft.py`, T1 |
| **T3** | `terms/policy.py` — 클래스 상수, 필드→클래스 매핑, **허용 단계표**, 신뢰도 상수, `_env_flag` | 설계+코딩 | M | T2 | T1 §허용 단계표, `ocr/types.py:BL_FIELD_NAMES`, `ocr/doc_types.py:SPECS` |
| **T4** | `terms/glossary.py` — 로더·전수 검증·`GlossaryStack`·인덱스. **표본 20건**으로 동작시킨다 | 코딩(Sonnet) | L | T2,T3 | `ruleEngine/engine.py` 전문 |
| **T5** | `catalogs/std-2026.1/locode.yaml` — UN/LOCODE **60건 전사**. 국가 배분·동음이의 6쌍 필수·`verified` 전부 생략 | 기계(Haiku) | L | T4 | T4 스키마. 자기 검사: `python -c "from terms import load_glossary; load_glossary()"` |
| **T6** | `catalogs/std-2026.1/glossary.yaml` — 나머지 9클래스 + `manifest.yaml` | 기계(Haiku) | L | T4 | 동상 + 기획안 §5.2 표 |
| **T7** | `terms/validators.py` — ISO 6346·Rec 20·Incoterms 장소·HS/HSK·LOCODE 형식 | 코딩(Sonnet) | M | T2,T3 | `ruleEngine/checks.py`(`parse_quantity`·`INCOTERMS`), T1 §결정론 검증기 |
| **T8** | `terms/similarity.py` — `Ranker` Protocol + `NGramRanker` + 인덱스 캐시 | 코딩(Sonnet) | S | T2,T4 | T1 §유사도 |
| **T9** | `terms/cascade.py` — `Normalizer`. **판단이 가장 많이 드는 파일** | 설계+코딩 | XL | T3,T4,T7,T8 | T1 전문, `ruleEngine/engine.py:verify`, `checks.py`, `types.py:LCTerms`, `mt700.py` |
| **T10** | `terms/llm_select.py` — 프롬프트·배치·JSON 파싱·후보 외 폐기·주입 탐지·실패 폴백 | 설계+코딩 | L | T9 | `report/llm_providers.py` 전문, `ocr/llm_extract.py` 전문, `report/narrative.py` |
| **T11** | `terms/apply.py` — `suggestion_id`·변조 대조·accept/reject·일괄 적용·span 치환 | 코딩(Sonnet) | M | T2,T9 | `report/share.py:1-60`, T1 §제안 ID |
| **T12** | `terms/__init__.py` + `api/main.py` 배선 — 5개 엔드포인트·`lifespan`·`/health`·`.env.example` | 코딩(Sonnet) | L | T9,T10,T11 | `api/main.py` 전문, `ruleEngine/__init__.py` |
| **T13** | 테스트 5파일. 한국어 명명·`importorskip`·`clean_env` autouse·전송 계층 모킹 | 코딩(Sonnet) | XL | T12 | `tests/test_llm_providers.py`, `test_api.py`, `test_rule_engine.py`, `conftest.py` |
| **T14** | `terms/eval/corpus.yaml` — 200건 라벨, **음성 사례 ~45%**, 클래스별 최소 12건 | 기계→검증 | L | T5,T6 | T1 §정밀도, T5·T6 카탈로그 |
| **T15** | `terms/evaluate.py` — 정밀도·재현율·`requires_choice` 비율 CLI + 임계값 테스트 | 코딩(Sonnet) | M | T13,T14 | `mlModel/evaluate.py` |
| **T16** | `acceptance.py` 확장 — F2 Result 2건, 냉시작 분리, `--llm` 분기 | 코딩(Sonnet) | S | T12 | `acceptance.py` 전문, `tests/test_acceptance.py` |
| **T17** | 문서 마감 — f2 문서 완성 + `api.md` + `api-spec.md` + `remaining-work.md` | 설계(Opus) | L | T15,T16 | T1 초안, `f3-defect-prediction.md`, `api-spec.md` |
| **T18** | **회귀 검증** — 전체 pytest·`terms.evaluate`·`acceptance`·`curl` 전사. **수치를 지어내지 않는다** | 검증(Fable) | M | T17 | `api.md` "동작 확인 기록" 기존 형식 |
| **T19** | *(별도 브랜치 권고)* `PORT_SYNONYMS` 이관 + F1-score 전/후 재측정 | 설계+검증 | M | T18 | `checks.py:27-41,523-542`, `mlModel/evaluate.py` |

**병렬 가능**: T5·T6 은 T4 완료 즉시 T7·T8 과 병렬. T14 는 T13 과 병렬.
**직렬 임계 경로**: T1 → T2/T3 → T4 → T9 → T10/T11 → T12 → T13 → T15 → T17 → T18.
T5·T6·T14 는 순수 전사라 Haiku 로 빼면 임계 경로에서 완전히 빠진다.

---

## 8. 개발 환경 주의

**작업 트리 경로에 `:` 가 들어 있어 `python -m venv` 가 거부한다**
(`Refusing to create a venv ... because it contains the PATH separator :`).
venv 는 저장소 밖에 만들어야 한다. 이 세션이 쓴 것:

```
/private/tmp/claude-501/-Users-ethanyang-Documents-Smart-e-BL-Backend/<session>/scratchpad/f2venv
```

Python 3.12 기준(`requirements.txt` 선언). PaddleOCR·XGBoost 는 설치하지 않아도
테스트가 `importorskip` 으로 건너뛴다.

```bash
cd aiService && <venv>/bin/python -m pytest
```

---

## 9. 검증 기준

- **정밀도 ≥ 0.90** — `terms/eval/corpus.yaml` ~200건 중 **음성 사례 ~45%**.
  정밀도는 "틀린 제안을 안 하는가"이므로 제안해서는 안 되는 입력(이미 표준·L/C 고정
  필드·고유명사·판별 불가 동음이의)이 없으면 측정 자체가 안 된다.
  `requires_choice` 는 **제안으로 세지 않는다**(판정한 게 아니라 사용자에게 넘긴 것) —
  이 구분을 빼면 애매한 건을 전부 `requires_choice` 로 밀어 정밀도를 1.0 으로 만들 수
  있으므로 재현율과 `requires_choice` 비율을 별도 열로 함께 찍는다.
- **응답 시간** — 필드 1건 2초 / 선적 1건 10초. **pytest 에 박지 않고** `acceptance.py`
  에서 **최댓값으로** 판정(평균 10초는 절반이 넘긴다는 뜻), 냉시작 분리, LLM 은
  `--llm` 으로만 포함.
- **결정론 항목 오류 검출률** — §4.9 표의 범위 안에서만 주장한다.

---

## 10. 이 문서를 갱신할 때

설계가 바뀌면 **여기를 먼저 고치고** 코드를 고쳐라. 코드만 바뀌고 이 문서가 남아
있으면 다음 세션이 틀린 계약서를 읽는다. 진행 상태·실측 수치는 여기가 아니라
[`PROGRESS.md`](PROGRESS.md) 다.
