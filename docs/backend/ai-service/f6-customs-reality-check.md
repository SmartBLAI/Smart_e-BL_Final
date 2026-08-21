# F6 — 통관·운송 현실 대조

> 기획안 5.6: "서류가 서류끼리는 맞아도 실제 통관·운송 기록과 어긋나면 지연이거나 사고다. 관세청·선사 이벤트를 서류 내용과 같은 시간축에 놓고 대조해 모순을 심각도별로 경보한다."

이번 구현은 그 시간축의 **한 조각**만 만든다 — 울산항 VTS 관제 기록.

## 1. 범위 결정

| 원안 데이터 소스 | 이번 | 왜 |
|---|---|---|
| 관세청 UNI-PASS 화물통관진행정보 (A등급) | **제외** | 발급·계약 필요. 세관 이벤트가 없으면 C-QTY-01/02·C-REL-01·C-TIME-03 은 **근거 데이터 자체가 없다** |
| 선사 DCSA Track & Trace (B등급) | **제외** | 동상 — 선사 계약 |
| 사용자 입력 기록 (L/G·Telex Release·원본회수, C등급) | **제외** | 입력·저장이 게이트웨이 몫인데 아직 빈 스캐폴딩이다 |
| 서류 이벤트 (내부) | **제외** | 동상. 이력을 남길 곳이 없다 |
| **울산항만공사 항만 내 선박 운항정보** | **채택** | 인증키만 있으면 되는 유일한 실접근 가능 공공데이터 |

**이건 세관 데이터가 아니다.** VTS 관제 기록 — 한 항구 안에서의 배 움직임(입항/접안/이안/이선/투묘/양묘/출항)이다. 이번에 대조하는 것은 **선박 이동 시간축**뿐이며, 화면 문구도 그렇게 써야 한다. "세관 기록과 대조했다"고 표기하면 **하지 않은 검증을 했다고 말하는 것**이 된다 — F3 의 `skipped` 를 감추면 안 되는 것과 같은 자리다.

### 커버리지 한계 — 울산항 밖은 보이지 않는다

이 API 가 관제하는 것은 울산항 **안에서의** 움직임뿐이다. 양륙항이 울산이 아니면 그 항의 이벤트는 애초에 존재하지 않는다. 따라서 **매칭 실패는 '기록과 어긋남'이 아니라 '볼 수 없음'** 이고, 반드시 `not_evaluated`(경보 아님)로 나가야 한다. 이걸 위반으로 두면 울산과 무관한 정상 B/L 전건에 경보가 뜬다.

### 무상태 — DB·폴러·해제 상태는 이번에 만들지 않는다

`api/main.py` 머리말이 규약이다: 저장 책임은 게이트웨이에 있고, 여기서 DB 를 잡으면 AI 모듈이 스키마 변경에 묶인다. 그래서 F6 은 **순수 매칭 함수를 HTTP 로 노출한다** — 요청이 B/L 초안을 통째로 싣고 오고(`/verify` 와 같은 형태), 응답은 그 자리에서 계산한 경보다. `shipment_id` 로 조회하지 않는다.

**나중에 게이트웨이가 더해야 할 것 (여기 없는 것):**
- 이벤트 스냅샷 영속화 (`customs_events` 류) — 지금은 매 요청 재조회
- 폴링 주기·스케줄러 — "이벤트 수집 지연" 수용 기준은 폴러가 있어야 잴 수 있다
- 경보 해제(dismiss)·화이트리스트 상태 — 같은 입력이면 같은 경보가 매번 나온다. 껐다는 사실은 저장할 곳이 있는 쪽이 기억해야 한다
- 실행 간 경보 중복 제거

## 2. C-* 규칙 실행가능성 판정

> 원안 5.6 표의 규칙 문구는 소스별 이벤트 목록에서 복원한 것이다. ID 는 추적성을 위해 그대로 쓴다.

| ID | 원안 취지 | 이 데이터로 | 이유 | 이번 |
|---|---|---|---|---|
| **C-TIME-01** | 서류 이벤트가 물리 이벤트보다 **이르다** (본선적재일 < 실제 입항) | **가능** | `jobDt` 로 입항 실측 시각이 나온다 | ✅ critical |
| **C-TIME-02** | 서류 이벤트가 물리 이벤트보다 **늦다** (본선적재일 > 실제 출항) | **가능** | 동상. 배가 떠난 뒤 적재는 물리적 모순 | ✅ critical |
| **C-TIME-03** | 세관 신고 순서 역전 (반입 전 수리, 반출 전 납부 등) | **불가능** | 세관 신고 이벤트가 없다 | ❌ |
| **C-TIME-04** | 예정 대비 실제 지연 이상 | **부분가능** | ETA/ATA 대비가 아니라 **체류시간 분포 이탈**만. `ptentDt`/`dfptDt` 는 예정이 아니라 그 항차의 입·출항 실측과 같은 값이다(115/115 확인) — 즉 이 API 에 '예정 vs 실제' 축은 없다 | ✅ warning (결정론 임계) |
| **C-QTY-01** | 세관 신고 수량 ↔ 서류 수량 | **불가능** | 수량 필드가 없다 | ❌ |
| **C-QTY-02** | 분할 반출 누계 ↔ 서류 수량 | **불가능** | 동상 | ❌ |
| **C-REL-01** | 원본회수·L/G ↔ 세관 반출 | **불가능** | 인도 이벤트도 세관 이벤트도 없다 | ❌ |
| **C-ROUTE-01** | 양륙항·선적항 불일치 | **부분가능** | 울산이 POL 또는 POD 인 건만. 그 외는 커버리지 밖 → `not_evaluated` | ✅ critical |
| **C-VSL-01** | 선명·항차 불일치 | **부분가능** | 선명은 대조 가능(조인 키). **항차번호는 불가능** — `vyg` 는 울산항 연번(2025년 001~115)이지 선사 항차번호가 아니다 | ✅ warning (동명이선만) |
| **C-STAT-01** | 이벤트 상태 진행 순서 이상 | **가능** | 관제 시퀀스 문법으로 판정된다 | ✅ info |
| **C-ANOM-01** | Isolation Forest 이상탐지 | **가능하나 무의미** | §4 | ❌ |

**11개 중 6개 구현, 커버리지 45%.** 이 숫자를 발표에서 숨기지 않는다.

## 3. 이벤트 정규화와 매칭 키

### 3.1 event_type 매핑

| `ioprtVtsType` | `ioprtVtsNm` | 내부 `event_type` |
|---|---|---|
| 3 | 입항 | `ARRIVAL` |
| 4 | 접안 | `BERTH` |
| 5 | 이안 | `UNBERTH` |
| 6 | 이선 | `SHIFT_BERTH` |
| 7 | 투묘 | `ANCHOR` |
| 8 | 양묘 | `WEIGH_ANCHOR` |
| 9 | 출항 | `DEPARTURE` |

- **판정에 쓰는 시각은 `jobDt` 하나다.** `ptentDt`/`dfptDt` 는 항차 전체의 기준값이라 이벤트별 시각이 아니고, `updtDt` 는 레코드 갱신 시각이라 사건 시각이 아니다.
- **모르는 코드를 버리지 않는다.** `UNKNOWN` + 원본 코드로 남기고 C-STAT-01 이 info 로 알린다. 조용히 버리면 이벤트가 줄어 시간창이 넓어지고, 그 결과는 '경보 없음'으로 읽힌다.
- 항차 그룹 키는 `(callsgn, ptentVtsYr, vyg)`, 정렬은 `comCnt`.
- `fcltSpecCd == "WAM"` 이면 정박지, 그 외(`MBU`/`MLJ`/`MDU`/`MBJ`/`MQP`)는 계류시설. C-STAT-01 이 이 구분을 쓴다.

### 3.2 매칭 키 — callsgn 을 못 쓴다

**콜사인이 1급 키인데 B/L 에는 콜사인 칸이 없다.** `ocr/types.py:BLFields` 에도 없고 실물 서식에도 없다. 그래서 이름으로 조인할 수밖에 없고, 이름 매칭은 취약하다:

- `vslEngNm` 은 `"OSUNG"` 인데 B/L 은 `"M/V OSUNG"`·`"OSUNG HO"` 로 온다 → 접두(`M/V`·`MV`·`MT`·`SS`)와 접미(`HO`)를 제거
- B/L `vessel` 에 항차가 붙어 오는 일이 흔하다(`"MSC BIANCA V.112"` — `tests/conftest.py` 픽스처가 그 예) → `V.\d+` 류 꼬리 제거
- **동명이선**이 실재한다. 이름이 여러 `callsgn` 에 걸리면 조인이 틀린 배를 고른다

**결정한 폴백 순서:**
1. 요청에 `call_sign` 이 있으면 그것만 쓴다 (게이트웨이가 선사 정보를 갖게 되면 이 경로가 정상 경로가 된다)
2. 없으면 `normalize_key(vessel)` 로 `vslEngNm`·`vslKornNm` 대조. **정규화는 `from terms import normalize_key` 로 F2 와 같은 함수를 쓴다** — 다른 정규화를 쓰면 매칭이 조용히 어긋난다(`docs/f2/HANDOFF.md` §6 이 이걸 위해 노출해 둔 것이다)
3. 후보 `callsgn` 이 2개 이상 → **C-VSL-01 warning 을 내고 나머지 룰은 전부 `not_evaluated`.** 틀린 배로 시간역설을 판정하는 것보다 판정하지 않는 편이 낫다
4. 후보 0개 → 전 룰 `not_evaluated`("울산항 관제 기록에서 이 선박을 찾지 못했습니다"). **위반이 아니다** (§1 커버리지 한계)

**실 API 소스는 call_sign 없이 fetch 자체가 안 된다** — 위 폴백은 이미 받아온 레코드 안에서 후보를 고르는 얘기고, 울산항 VTS 는 `callsgn` 없이 호출하면 그 전에 `EventSourceError` 다(위 표). 그래서 `api/main.py` 는 fetch 전에 한 단계를 더 끼운다: 요청에 `call_sign` 이 없고 소스가 fixture 가 아니면 `resolve_call_sign(vessel_name)`(해양수산부_선박제원정보, `SicsVsslManp3/Info3`)으로 먼저 콜사인을 찾는다. 이것도 실패하면(동명이선·미등록·API 오류 등 — 전부 `None`) 네트워크를 아예 타지 않고 `records=[]` 로 떨어뜨린다 — 여기서도 "특정 못 함"은 오류가 아니라 위 4번과 같은 정상 미매칭이다.

**항차 선택은 날짜로 한다.** `on_board_date`(없으면 `date_of_issue`)를 `[ARRIVAL.jobDt, DEPARTURE.jobDt]` 창에 넣어 고른다. 어느 창에도 안 들어가면 가장 가까운 항차를 **인접 항차**로 골라 C-TIME-01/02 가 그 어긋남을 말하게 하되, 거리 **7일**을 넘으면 후보 없음으로 본다(실측 최대 체류 82시간 ≈ 3.4일 — 7일이면 인접 항차까지 덮는다).

## 4. C-ANOM-01 (Isolation Forest) — 이번에 넣지 않는다

**지금 필요한가?** 아니다.

1. **학습 표본이 없다.** 샘플은 선박 1척·1년·115항차다. 1척으로 학습한 이상탐지는 "이 배의 평소와 다른가"만 답하며, 그건 임계 하나로 되는 일이다. 모델을 얹으면 F3 에서 이미 확인된 것 — **룰 단독이 최고 성능, 모델 기여가 음수** — 이 재현될 뿐이다.
2. **이상치 라벨이 없다.** 무엇을 잡았는지 검증할 방법이 없으므로 오탐률을 잴 수 없고, 잴 수 없는 오탐은 기획안 9절이 든 리스크 그대로다.
3. **대체 수단이 있다.** C-TIME-04 를 체류시간 IQR 임계(> Q3 + 1.5·IQR)로 낸다. 결정론이라 왜 걸렸는지 사용자에게 설명된다.

**언제 넣나:** 다중 선박 이벤트가 쌓이고(최소 수백 척), C-TIME-04 의 오탐률이 실측된 뒤. 그때 넣더라도 F3 와 같은 규약이다 — **판정은 룰, 순위는 모델.**

## 5. 코드 레이아웃

`backend/aiService/reality/` (형제 모듈 `ruleEngine/`·`terms/`·`report/` 와 같은 층위)

| 파일 | 책임 |
|---|---|
| `__init__.py` | 공개 심볼 재노출. `ruleEngine/__init__.py` 와 같은 형태 |
| `types.py` | `PortEvent`·`Voyage`·`VesselMatch`·`EVENT_TYPES` 매핑. **`Severity` 를 정의하지 않는다** — `from ruleEngine.types import Severity` |
| `adapter.py` | `EventSource` Protocol + `FixtureSource`(로컬 JSON) + `UlsanVtsSource`(HTTP, `serviceKey`). 실 엔드포인트: `{base_url}/getVtsBaseVslNvgtInfo`(`docs/endpoint screen shot.png` 참고). `callsgn`+`ptentVtsYr` 없이는 호출 불가(실측 — 게이트웨이가 HTTP_ERROR) — call_sign 을 모르면(선명만으로 매칭하는 경로) 실 소스는 조회할 수 없고 즉시 `EventSourceError`. 여기에 `resolve_call_sign(vessel_name)` 도 같이 있다 — 해양수산부_선박제원정보(`https://apis.data.go.kr/1192000/SicsVsslManp3/Info3`, XML, `serviceKey` 는 `ULSAN_VTS_SERVICE_KEY` 재사용 — 공공데이터포털 일반인증키는 계정 단위라 승인된 다른 API 에도 그대로 쓰인다)에서 선명으로 콜사인을 역으로 찾는다. `vsslNm` 검색이 부분일치라 `vsslEngNm`/`vsslKorNm` 정확일치만 인정하고, 0건이거나 동명이선으로 하나로 안 좁혀지면 예외 없이 `None`(§3.2 하단). |
| `normalize.py` | 원시 레코드 → `PortEvent` 목록 → `(callsgn, 연도, vyg)` 별 `Voyage` 로 그룹·정렬 |
| `matcher.py` | B/L → `VesselMatch`. §3.2 폴백 순서 구현 |
| `checks.py` | 검사 레지스트리. **`CheckOutcome`·`passed`·`violated`·`not_evaluated` 는 `ruleEngine.checks` 에서 import** (`cross_doc.py` 가 하는 것과 같다). 시그니처만 다르다: `(bl, voyage, rule) -> CheckOutcome` |
| `engine.py` | `RealityEngine`. 카탈로그 로드 + 전수 검증 + `Verdict` 조립. `fingerprint_of`·`RuleCatalogError` 를 `ruleEngine.engine` 에서 import |
| `reality_rules.yaml` | 룰 6건. `version: 1` |
| `fixtures/ulsan_vts_2025.json` | `docs/관제기반 선박운항정보.json` 사본(214KB). 패키지 안에 둔다 — Dockerfile 이 `aiService` 만 COPY 하므로 밖을 가리키면 컨테이너에서 소스가 사라진다 |

**출력 타입을 새로 만들지 않는다.** `ruleEngine.types.Verdict`/`Violation`/`SkippedRule` 을 그대로 쓰고 `model="reality-v1"`, `catalog=fingerprint.to_dict()` 을 싣는다. 기획안 5.8 이 "심각도 3단계 정의는 F3·F6 이 공유한다"로 못박았고, S4 가 이미 이 구조를 그린다. 병렬 타입을 만들면 화면이 두 벌 필요해진다.

### 룰 카탈로그

| id | title | severity | check | 발화 조건 |
|---|---|---|---|---|
| C-TIME-01 | 본선적재일이 실제 입항보다 이르다 | critical | `date_within_voyage` (`bound: arrival`) | `on_board_date` < `ARRIVAL.jobDt` |
| C-TIME-02 | 본선적재일이 실제 출항보다 늦다 | critical | `date_within_voyage` (`bound: departure`) | `on_board_date` > `DEPARTURE.jobDt` |
| C-TIME-04 | 항내 체류시간 이상 | warning | `stay_duration_outlier` | 체류시간 > Q3 + 1.5·IQR (같은 선박 전 항차 기준) |
| C-ROUTE-01 | 서류 항구가 관제 항구와 무관 | critical | `port_matches_source` | POL·POD 어느 쪽도 울산이 아닌데 매칭 성립 |
| C-VSL-01 | 동명이선 — 선박을 특정할 수 없다 | warning | `vessel_uniquely_matched` | 이름 후보 `callsgn` ≥ 2 |
| C-STAT-01 | 관제 이벤트 순서 이상 | info | `event_sequence_valid` | 아래 문법 위반 |

**C-STAT-01 문법** (실측 115 항차 **전건 통과** 확인 — 여기서 위반이 뜨면 서류가 아니라 데이터·매칭을 의심해야 한다):
- 항차는 `ARRIVAL` 로 시작하고 `DEPARTURE` 로 끝난다
- `jobDt` 가 `comCnt` 순서로 단조증가한다
- `UNBERTH` 앞에는 계류 상태가 있어야 한다 (`BERTH`/`SHIFT_BERTH`, 또는 계류시설 `ARRIVAL`)
- `WEIGH_ANCHOR` 앞에는 묘박 상태가 있어야 한다 (`ANCHOR`, 또는 `fcltSpecCd == "WAM"` 인 `ARRIVAL`)
- `UNKNOWN` 이벤트가 섞여 있다

**빠뜨린 것 (의도):** "적재일에 접안 상태가 아니었다"(정박지에만 있었음) 룰. 상태 구간 계산이 한 겹 더 필요한데 C-TIME-01/02 가 대부분 덮는다. C-TIME-01/02 오탐률이 측정된 뒤에 넣는다.

## 6. API

기존 관례를 따른다 — **평면 경로, `/api/v1` 프리픽스 없음**(프리픽스는 게이트웨이가 정한다), Pydantic 모델은 `main.py` 에 같이 두고, 카탈로그·이벤트 소스는 **기동 시 1회** 만든다(`engine()`/`normalizer()` 와 같은 지연 싱글턴).

| 메서드 | 경로 | 기능 |
|---|---|---|
| POST | `/reality/check` | 현실 대조 |
| GET | `/reality/rules` | C-* 룰 카탈로그 (`/rules` 와 같은 형태) |

`/health` 에 `reality_catalog`(fingerprint)·`reality_source`(`fixture` \| `ulsan`) 를 더한다. 어느 소스로 판정했는지가 응답이 달라질 때 제일 먼저 봐야 하는 값이다.

### POST `/reality/check`

**Request** (`RealityCheckRequest`)

| 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `bl` | `Dict[str, Optional[str]]` | **Y** | `/verify` 와 같은 형태. `vessel`·`voyage_no`·`port_of_loading`·`port_of_discharge`·`on_board_date` 를 쓴다. 비면 400 |
| `call_sign` | `str` | N | 있으면 이름 매칭을 건너뛴다 (§3.2 1순위) |
| `as_of` | `datetime` | N | 기준 시각. 생략 시 현재. 테스트·시연에서는 넣어야 결과가 고정된다 |
| `events` | `List[Dict[str, Any]]` | N | 게이트웨이가 이미 수집한 **원시** 레코드. 있으면 어댑터를 호출하지 않는다 — 재현 요청과 폐쇄망 프로파일용 |

**Response 200** (`RealityCheckResponse`)

| 이름 | 타입 | 설명 |
|---|---|---|
| `shipment_id` | `str\|null` | `bl.bl_no` 그대로 (`/verify` 와 같다) |
| `source` | `object` | `{adapter, port, records, fetched_at}`. `adapter` 가 `fixture` 면 **실 데이터가 아니다** — 화면이 이걸 감추면 안 된다 |
| `match` | `object` | `{matched, strategy, call_sign, vessel_name, voyage, window:{arrival,departure}, candidates, reason}`. `matched=false` 면 `reason` 이 왜 못 찾았는지 말한다 |
| `verdict` | `object` | `Verdict.to_dict()`. `model="reality-v1"`, `violations`·`skipped`·`counts` 구조가 `/verify` 와 동일 |

**`matched=false` 도 200 이다.** 커버리지 밖은 오류가 아니라 판정 결과이고, 그 사실은 `verdict.skipped` 에 전건으로 남는다.

**Error**

| 코드 | 조건 |
|---|---|
| 400 | `bl` 이 비었거나 입력 형 오류 |
| 422 | `bl` 키 자체가 없음 |
| 503 | 어댑터가 `ulsan` 인데 인증키 미설정·상류 응답 실패. **빈 이벤트 목록으로 200 을 내지 않는다** — 그 응답은 '경보 없음'으로 읽힌다 |

### `.env.example` 추가분

```bash
# F6 현실 대조 — 항만 이벤트 소스.
# fixture = 패키지 안 샘플 JSON(기본). ulsan = 공공데이터포털 실 API.
# 기본이 fixture 인 이유는 외부 API 호출이기 때문이다 — 켜는 것은 명시적
# 결정이어야 한다(TERMS_LLM_SELECT·LLM_STRUCTURED_EXTRACT 와 같은 규약).
REALITY_EVENT_SOURCE=fixture
# fixture 어댑터가 읽을 파일. 패키지 안 상대 경로다 — 밖을 가리키면
# 컨테이너에서 파일이 사라지고, 그 실패는 '이벤트 0건'으로 조용히 읽힌다.
REALITY_FIXTURE_PATH=./reality/fixtures/ulsan_vts_2025.json
# 울산항만공사 항만 내 선박 운항정보 Open API.
# 오퍼레이션명(getVtsBaseVslNvgtInfo)까지 붙여야 한다.
# 예: https://apis.data.go.kr/B551938/VslNvgtInfoService/getVtsBaseVslNvgtInfo
ULSAN_VTS_BASE_URL=
# data.go.kr 인증키. changeme 이거나 비어 있으면 ulsan 어댑터는 503 을
# 낸다 — 조용히 fixture 로 떨어지면 샘플 데이터를 실측으로 착각한다.
ULSAN_VTS_SERVICE_KEY=changeme
# 상류 타임아웃(초). 선적 1건 10초 예산 안에 들어가야 한다(기획안 5.3).
ULSAN_VTS_TIMEOUT=8
```

## 7. 테스트

기존 관례를 따른다 — 한국어 테스트 이름, `tests/conftest.py` 의 합성 데이터 팩토리, 네트워크 차단.

`conftest.py` 에 더할 것: `vts_records(...)` — 한 항차의 원시 레코드 목록을 만드는 팩토리(`complete_bl_bboxes()` 와 같은 자리). 이벤트 시각·시설코드를 테스트가 직접 통제해야 실패 원인이 분명하다.

| 파일 | 검증 |
|---|---|
| `test_reality_normalize.py` | 코드 7종 전수 매핑 · `jobDt` 파싱 · 항차 그룹핑과 `comCnt` 정렬 · **모르는 코드가 버려지지 않고 `UNKNOWN` 으로 남는다** |
| `test_reality_match.py` | `M/V`·`HO`·`V.112` 제거 · `call_sign` 우선 · 동명이선 → C-VSL-01 + 나머지 `not_evaluated` · 미발견 → 전건 `not_evaluated`(위반 0) · 7일 밖 항차는 후보 아님 |
| `test_reality_rules.py` | 카탈로그 전수 검증(중복 id·모르는 check·모르는 severity·weight 범위) · 룰 6건 각각의 발화/미발화 · **`Severity` 가 `ruleEngine.types.Severity` 와 같은 객체** · fingerprint 가 룰 변경에 반응 |
| `test_reality_api.py` | `/reality/check` 200/400/422 · `matched=false` 가 200 이고 `skipped` 가 채워진다 · 키 없는 `ulsan` 어댑터가 503 · `/reality/rules` · `/health` 에 `reality_source` |

**전 룰이 실측 데이터에서 침묵하는 것을 확인하는 테스트가 하나 있어야 한다** (아래 오탐 기준). 룰 6건을 넣고 아무도 발화하지 않는 상태를 검사하지 않으면, 오탐이 있어도 합성 케이스만 통과해 보인다.

## 8. 수용 기준 (축소 범위 재정의)

원안 5.6 기준: 모순 탐지 재현율 0.90 · 오탐률 10% 이하 · 이벤트 수집 지연 N분 이내.

### 이번에 측정 가능

| 기준 | 값 | 재는 법 |
|---|---|---|
| 시간역설 재현율 | **1.00** | 실측 115 항차에서 파생한 정상 B/L 의 `on_board_date` 를 창 밖으로 밀어 넣은 50건. 결정론 룰이므로 1.00 이 아니면 버그다 — 0.90 은 확률 모델의 기준이라 여기 맞지 않는다 |
| 오탐률 | **0%** (기준 ≤5%) | 실측 115 항차에서 파생한 정상 B/L 115건에 위반 0건. C-STAT-01 이 115/115 통과하는 것은 확인했다 |
| 매칭 성공률 | **≥0.95** | 위 115건. **샘플이 1척뿐이라 상한이 있는 지표다** — 동명이선·표기 흔들림이 실제로 얼마나 나는지는 이 데이터로 알 수 없다 |
| 응답 시간 | **≤0.2초** | fixture 소스, 1건. 실 API 경로는 `ULSAN_VTS_TIMEOUT` 이 상한이다 |
| 규칙 커버리지 | **6/11 (45%)** | §2 판정표. 숨기지 않고 그대로 보고한다 |

### 이번에 측정 불가 (그 사실을 적는다)

- **이벤트 수집 지연** — 폴러가 없다(무상태). 게이트웨이가 폴링을 잡은 뒤에 잴 수 있다
- **세관 이벤트 기반 모순 재현율** (C-QTY-01/02·C-REL-01·C-TIME-03) — 근거 데이터가 없다
- **실 API 지연·가용성** — 인증키 미발급. `ULSAN_VTS_BASE_URL` 이 빈 상태로 머지된다
- **울산항 외 커버리지** — 데이터가 없다. 실제 서비스에서 이 값이 몇 %인지는 다항 소스가 붙어야 나온다
- **오탐률의 일반화** — 위 0% 는 **선박 1척**에서 나온 값이다. F3 의 "Critical 오탐률 0.00%" 와 같은 함정이다 — 생성 데이터가 깨끗해서 나온 숫자일 수 있다
