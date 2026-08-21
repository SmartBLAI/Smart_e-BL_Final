"""F2 6단계 캐스케이드(`terms/cascade.py`) 테스트.

`docs/ai-service/f2-standard-terms.md` §"6단계 캐스케이드"·§"예외"·
§"결정론 검증기", `docs/f2/HANDOFF.md` §4 의 계약을 검사한다.

사전은 표본을 직접 주입한다(`Glossary(terms=[...])`) — 카탈로그가 바뀌어도
이 파일은 안 깨진다. `terms/cascade.py` 는 `datetime.now()` 를 부르지
않는다(경과 시간은 `time.perf_counter()` 로만 잰다) — 그래서 이 파일은
시각을 주입하지 않는다. 주입할 시계 자체가 코드에 없다.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pytest

from ruleEngine.types import LCTerms
from terms import policy
from terms.cascade import (
    DocumentInput,
    Normalizer,
    SelectionOutcome,
    _resolve_overlaps,
    _Decision,
    _Run,
)
from terms.glossary import Glossary, GlossaryStack
from terms.types import Evidence, FieldRef, GlossaryTerm, Suggestion


# ════════════════════════════════════════════════════════════════
# 표본 사전
# ════════════════════════════════════════════════════════════════


def _term(
    term_id: str,
    canonical: str,
    category: str,
    aliases: tuple = (),
    country: Optional[str] = None,
    bl_form: Optional[str] = None,
) -> GlossaryTerm:
    return GlossaryTerm(
        term_id=term_id,
        category=category,
        canonical=canonical,
        lang="en",
        authority="TEST",
        version="test-1",
        effective_date="2026-01-01",
        aliases=list(aliases),
        country=country,
        bl_form=bl_form,
    )


# 표준 표본 — 대부분의 테스트가 공유한다. 항구 동음이의 두 쌍을 함께 넣는다:
# PORTLAND(US/AU, 국가가 다름 — 값·인접 신호로 판별 가능) ·
# GANGHOEHANG(KR/KR, 국가가 같음 — 판별 불가로 후보 나열).
# bl_form 은 B/L 면에 실제로 인쇄되는 영문 항구명이다(canonical 은 코드일 뿐
# 이며 B/L 면에는 나오지 않는다) — 이게 없으면 제안이 나오지 않는다.
# 두 쌍 모두 **일부러** 후보 간 bl_form 을 다르게 둔다("PORTLAND"/
# "PORTLAND VIC", "GANGHOEHANG"/"GANGHOEHANG B") — 실제 카탈로그처럼 두
# 후보의 bl_form 이 완전히 같으면 `_build` 가 requires_choice 를 접어
# 단일 결정으로 확정해 버려(§선택 카드는 결과가 있어야 한다) 이 파일이
# 검사하려는 "판별 불가 → 후보 나열/⑤ 로 넘김" 분기 자체에 닿지 못한다.
_STANDARD_TERMS = [
    _term("PORT.KRPUS", "KRPUS", "port", aliases=("부산", "BUSAN", "BUSAN, KOREA"), country="KR", bl_form="BUSAN"),
    _term("PORT.USNYC", "USNYC", "port", aliases=("NEW YORK", "NEW YORK, USA"), country="US", bl_form="NEW YORK"),
    _term("PORT.USPDX", "USPDX", "port", aliases=("PORTLAND", "PORTLAND, USA", "포틀랜드"), country="US", bl_form="PORTLAND"),
    _term("PORT.AUPTL", "AUPTL", "port", aliases=("PORTLAND", "PORTLAND, AUSTRALIA", "포틀랜드"), country="AU", bl_form="PORTLAND VIC"),
    _term("PORT.KRAAA", "KRAAA", "port", aliases=("GANGHOEHANG", "강회항"), country="KR", bl_form="GANGHOEHANG"),
    _term("PORT.KRBBB", "KRBBB", "port", aliases=("GANGHOEHANG", "강회항"), country="KR", bl_form="GANGHOEHANG B"),
    _term(
        "PHR.SURRENDER",
        "Surrendered B/L",
        "practice_phrase",
        aliases=("SUR B/L", "SURR", "SUR"),
    ),
]


def _stack(terms: Optional[List[GlossaryTerm]] = None) -> GlossaryStack:
    payload = _STANDARD_TERMS if terms is None else terms
    glossary = Glossary(payload, catalog_version="test-1", effective_date="2026-01-01")
    return GlossaryStack([glossary])


def _doc(fields: Dict[str, Optional[str]], *, doc: str = "선하증권", doc_id: Optional[str] = None) -> DocumentInput:
    return DocumentInput(doc=doc, fields=fields, doc_id=doc_id)


class _SpySelector:
    """⑤ 호출을 가로채는 스파이. `Selector` Protocol 만 만족하면 된다."""

    def __init__(self, outcome: Optional[SelectionOutcome] = None) -> None:
        self.batches: List[list] = []
        self._outcome = outcome

    def select(self, items):
        self.batches.append(list(items))
        return self._outcome if self._outcome is not None else SelectionOutcome(
            choices={}, llm_path="called", llm_calls=1
        )


def _suggestion_ids(result) -> List[str]:
    return [s.suggestion_id for s in result.suggestions]


# ════════════════════════════════════════════════════════════════
# 단계별 정지 조건
# ════════════════════════════════════════════════════════════════


class Test단계별_정지조건:
    """①②③ 이 맞으면 즉시 종결하고, 확률 경로(④⑤)를 추가로 태우지 않는다."""

    def test_exact_단계_히트는_형식_정리로_강등된다(self):
        """①exact 은 `normalize_key(값) == canonical 키` 로 정의된다. 강등
        규칙(`_is_cosmetic_change`)은 **적용되는 값**(`to_be`)과 원본의
        차이가 대소문자·공백·구두점뿐일 때만 `format` 으로 내린다. 항구는
        이제 적용되는 값이 canonical(코드)이 아니라 `bl_form`(이름)이라 —
        `"KRPUS,"` → `"BUSAN"` — 글자 자체가 바뀌므로 더는 "코스메틱"이
        아니다. 그래서 exact 단계 매칭은 여기서도 그대로 살아남는다
        (CONF_EXACT). `" KRPUS "` → `"KRPUS"` 처럼 적용되는 값이 코드 그대로
        남는(non-port) 클래스에서는 강등이 여전히 일어난다."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"port_of_loading": "KRPUS,"})])

        [suggestion] = result.suggestions
        assert suggestion.to_be == "BUSAN"
        assert suggestion.evidence.stage == "exact"
        assert suggestion.confidence == pytest.approx(policy.CONF_EXACT)

    def test_alias_단계가_맞으면_거기서_종결한다(self):
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"port_of_loading": "부산"})])

        [suggestion] = result.suggestions
        assert suggestion.evidence.stage == "alias"
        assert suggestion.confidence == pytest.approx(policy.CONF_ALIAS)
        assert suggestion.to_be == "BUSAN"

    def test_결정론_검증_통과는_0_97이다(self):
        """③ pattern 이 결정론 검증(체크디지트)까지 통과하면 CONF_PATTERN_VERIFIED."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"description_of_goods": "MSKU 123456 5"})])

        [suggestion] = result.suggestions
        assert suggestion.term_class == "container_no"
        assert suggestion.confidence == pytest.approx(policy.CONF_PATTERN_VERIFIED)
        assert suggestion.to_be == "MSKU1234565"

    def test_형식만_맞고_결정론_검증이_없으면_0_90이다(self):
        """LOCODE 는 체크디지트 같은 이중 검증이 없어 형식만 맞으면 늘
        CONF_PATTERN(0.90) — CONF_PATTERN_VERIFIED(0.97) 와 구분되어야 한다.
        공백 때문에 exact/alias 를 놓치고 ③pattern 에서 정규화("kr pus" →
        "KRPUS")된 뒤 사전 역조회로 걸려야 한다 — 사전에 없는 코드
        (예: "kr xxx")는 이제 형식만 맞아도 제안하지 않는다(§③pattern 사전
        역조회, 아래 `test_사전에_없는_코드는_형식만_맞아도_제안하지_않는다`
        참고)."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"port_of_loading": "kr pus"})])

        [suggestion] = result.suggestions
        assert suggestion.to_be == "BUSAN"
        assert suggestion.evidence.stage == "pattern"
        assert suggestion.confidence == pytest.approx(policy.CONF_PATTERN)

    def test_사전에_없는_코드는_형식만_맞아도_제안하지_않는다(self):
        """③pattern — 형식은 LOCODE 규칙(`^[A-Z]{2}[A-Z2-9]{3}$`)을 통과해도
        사전 어디에도 없는 코드면 값을 지어내지 않는다. 예전에는 정규화된
        코드(`"KRXXX"`)를 그대로 `to_be` 로 냈다."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"port_of_loading": "kr xxx"})])

        assert result.suggestions == []
        assert any("사전에 없는 항구 코드" in u.reason for u in result.unevaluated)

    def test_이미_표준인_값은_제안하지_않는다(self):
        """`to_be == as_is` 면 무의미한 카드다 — 만들지 않는다. 항구는
        `bl_form`(BUSAN)이 이미 B/L 면 표기이므로 `"BUSAN"` 이 기준이다 —
        코드(`"KRPUS"`)는 더는 "이미 표준"이 아니다(코드는 B/L 면 표기가
        아니라서 오히려 BUSAN 으로의 교정 대상이다)."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"port_of_loading": "BUSAN"})])

        assert result.suggestions == []

    def test_유사도_최고점_미달이면_제안없이_유보에_점수와_함께_남는다(self):
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"port_of_loading": "ZZZZZQQQQQ"})])

        assert result.suggestions == []
        [unevaluated] = result.unevaluated
        assert unevaluated.score == pytest.approx(0.0)
        assert f"{policy.SIMILARITY_FLOOR}" in unevaluated.reason

    def test_유사도_후보_1건_충분점수면_LLM을_건너뛰고_종결한다(self):
        """SINGLE_CANDIDATE_FLOOR(0.85) 이상인 유일 후보는 ⑤ 로 보내지 않는다
        — 고를 것이 하나뿐인데 "고르라"고 물으면 비용·주입면만 늘어난다.

        입력은 "BUSAN" 토큰을 그대로 담지 않도록 고른다("BUSANKOREAA" 처럼
        붙여 쓴 오타) — 그렇지 않으면 `bl_form` 토큰 부분집합 억제
        (`Test단계별_정지조건.test_이미_표준인_값은_제안하지_않는다` 근처
        주석 참고)가 먼저 걸려 이 테스트가 검사하려는 "단일 후보 → LLM
        생략" 분기 자체에 닿지 못한다."""
        spy = _SpySelector()
        norm = Normalizer(stack=_stack(), selector=spy)
        result = norm.normalize([_doc({"port_of_loading": "BUSANKOREAA"})], llm=True)

        [suggestion] = result.suggestions
        assert suggestion.to_be == "BUSAN"
        assert suggestion.evidence.stage == "similarity"
        assert suggestion.requires_choice is False
        assert suggestion.confidence == pytest.approx(min(0.88, 0.55 + 0.35 * 0.85), abs=0.02)
        assert spy.batches == []  # 선정기가 아예 호출되지 않았다.

    def test_후보_2건_이상이고_선정기가_없으면_requires_choice로_남는다(self):
        """PORTLAND(US/AU) — 두 후보의 bl_form 이 다르므로("PORTLAND" vs
        "PORTLAND VIC") 후보 전원 일치 축약(§선택 카드는 결과가 있어야
        한다)에 걸리지 않고 진짜 선택 카드로 남는다."""
        norm = Normalizer(stack=_stack())  # selector=None
        result = norm.normalize([_doc({"port_of_loading": "PORTLAND"})], llm=True)

        [suggestion] = result.suggestions
        assert suggestion.requires_choice is True
        assert suggestion.to_be is None
        assert len(suggestion.candidates) == 2
        assert result.stats.llm_path == "not_called"

    def test_후보_2건_이상이고_선정기가_있으면_LLM로_확정된다(self):
        """두 후보의 bl_form 을 일부러 다르게 둔다("PORTLAND"/
        "PORTLAND VIC") — 똑같으면 `_build` 가 후보 전원 일치로 보고
        `requires_choice` 를 접어 선정기 호출 자체가 일어나지 않는다
        (§선택 카드는 결과가 있어야 한다)."""
        terms = [
            _term(
                "PORT.USPDX", "USPDX", "port",
                aliases=("PORTLAND", "PORTLAND, USA"), country="US", bl_form="PORTLAND",
            ),
            _term(
                "PORT.AUPTL", "AUPTL", "port",
                aliases=("PORTLAND", "PORTLAND, AUSTRALIA"), country="AU", bl_form="PORTLAND VIC",
            ),
        ]
        # 후보는 term_id 로 정렬된다("PORT.AUPTL" < "PORT.USPDX") — choice=1
        # 은 candidates[0]=AUPTL(bl_form="PORTLAND VIC")를 고른다(1-index).
        # choice=2(USPDX="PORTLAND")는 원문("PORTLAND")과 글자가 같아져
        # `_resolve_llm` 이 확정 후 카드를 지워 버려 이 테스트가 검사하려는
        # "⑤ 로 확정됐다"는 사실 자체가 사라진다.
        outcome = SelectionOutcome(choices={"item1": 1}, llm_path="called", llm_calls=1)
        spy = _SpySelector(outcome)
        norm = Normalizer(stack=_stack(terms), selector=spy)
        result = norm.normalize([_doc({"port_of_loading": "PORTLAND"})], llm=True)

        [suggestion] = result.suggestions
        assert suggestion.requires_choice is False
        assert suggestion.evidence.stage == "llm"
        assert suggestion.to_be == "PORTLAND VIC"
        assert spy.batches and spy.batches[0][0].term_class == "port"


class Test신뢰도_하한:
    """§정밀도 "제안하지 않는 것이 틀리게 제안하는 것보다 낫다" 의 수치화."""

    def test_MIN_CONFIDENCE_미만은_어떤_정상_경로에서도_나오지_않는다(self):
        """0.60 은 감점이 겹쳐야만 닿는 안전망이지 상시 발동 문턱이 아니다
        — ④⑤ 최소값이 이미 이 문턱 위에 있어야 한다."""
        similarity_floor_confidence = min(0.88, 0.55 + 0.35 * policy.SIMILARITY_FLOOR)
        llm_floor_confidence = min(policy.LLM_CONFIDENCE_CAP, 0.55 + 0.30 * policy.SIMILARITY_FLOOR)

        assert similarity_floor_confidence >= policy.MIN_CONFIDENCE
        assert llm_floor_confidence >= policy.MIN_CONFIDENCE

    def test_MIN_CONFIDENCE_미만_결정은_제안대신_유보로_남는다(self):
        """정상 경로로는 못 만드는 값(0.50)을 직접 주입해 하한 게이트 자체를
        검사한다 — `_build` 의 유일한 신뢰도 차단 지점이다."""
        norm = Normalizer(stack=_stack())
        run = _Run(documents=[])
        ref = FieldRef(doc="선하증권", field="port_of_loading")
        decision = _Decision(stage="similarity", to_be="USNYC", confidence=0.50, score=0.50)

        suggestion = norm._build(run, ref, "port", "NEWYORK", decision)

        assert suggestion is None
        [unevaluated] = run.unevaluated
        assert unevaluated.score == pytest.approx(0.50)
        assert "0.5" in unevaluated.reason


# ════════════════════════════════════════════════════════════════
# 클래스별 허용 단계 — ⑤ 금지
# ════════════════════════════════════════════════════════════════


class Test클래스별_허용_단계:
    def test_금지_클래스_목록이_문서와_일치한다(self):
        """`policy.LLM_FORBIDDEN` 이 HANDOFF §4.2 표의 "금지" 7개와 정확히
        같아야 한다 — 어긋나면 허용 단계표(코드)가 계약서(문서)와 갈라진 것."""
        assert policy.LLM_FORBIDDEN == frozenset(
            {
                "party_suffix",
                "qty_unit",
                "volume_unit",
                "container_no",
                "hs_code",
                "party_name",
                "goods",
            }
        )

    def test_LLM_이_켜져_있어도_호출되지_않는다(self):
        """금지 클래스(container_no·qty_unit·hs_code)의 자극을 함께 주고,
        정상적으로 LLM 이 발동하는 항구 동음이의도 같은 요청에 섞는다.
        선정기가 실제로 호출됐음을 확인해(공허한 통과 방지) 그 배치 안에
        금지 클래스 항목이 하나도 없는지 검사한다."""
        spy = _SpySelector()
        norm = Normalizer(stack=_stack(), selector=spy)
        document = _doc(
            {
                # GANGHOEHANG(KR/KR) — 국가가 같아 판별 불가 → requires_choice
                # + llm_pending. 두 후보의 bl_form 을 다르게 둬서("GANGHOEHANG"
                # vs "GANGHOEHANG B") 후보 전원 일치 축약에 걸리지 않는다.
                "port_of_loading": "GANGHOEHANG",
                "gross_weight": "500 BAGS",  # qty_unit, Rec 20 밖 — LLM 금지
                "description_of_goods": (
                    "MSKU 123456 5 HS 8471.30-1000"
                ),  # container_no·hs_code — LLM 금지
            }
        )
        result = norm.normalize([document], llm=True)

        assert spy.batches, "선정기가 아예 호출되지 않았다 — 이 테스트가 검증할 대상이 없다"
        called_classes = {item.term_class for batch in spy.batches for item in batch}
        assert called_classes == {"port"}
        assert called_classes.isdisjoint(policy.LLM_FORBIDDEN)
        assert result.stats.llm_calls >= 1

    def test_party_suffix는_exact_alias가_금지되어_있다(self):
        assert policy.allows("party_suffix", policy.STAGE_EXACT) is False
        assert policy.allows("party_suffix", policy.STAGE_ALIAS) is False
        assert policy.allows("party_suffix", policy.STAGE_PATTERN) is True

    def test_qty_unit은_유사도가_금지되어_있다(self):
        """Rec 20 은 닫힌 집합이다 — "비슷한 단위" 라는 개념 자체가 없다."""
        assert policy.allows("qty_unit", policy.STAGE_SIMILARITY) is False


# ════════════════════════════════════════════════════════════════
# 동음이의 항구
# ════════════════════════════════════════════════════════════════


class Test동음이의_판별:
    def test_값_안의_국가로_동음이의를_판별한다(self):
        """`_disambiguate` 를 직접 호출해 판별 알고리즘만 떼어 검사한다.
        전체 캐스케이드로 돌리면 `bl_form`(PORTLAND)이 원문("PORTLAND, USA")에
        이미 토큰으로 들어 있어 최종 카드 자체가 억제된다(§토큰 부분집합
        억제, `Test단계별_정지조건` 이 그건 따로 검사한다) — 그래서 여기서는
        판별 결과(어느 후보로 좁혔는가)만 본다."""
        norm = Normalizer(stack=_stack())
        hits = norm.stack.lookup("PORTLAND", "port", alias=True)
        ref = FieldRef(doc="선하증권", field="port_of_loading")

        resolved = norm._disambiguate(_Run(documents=[]), ref, "port", "PORTLAND, USA", hits, {})

        assert resolved is not None
        assert resolved.term.term_id == "PORT.USPDX"

    def test_국가를_특정할_수_없으면_후보를_나열한다(self):
        """`requires_choice=True` 일 때 `to_be` 는 반드시 `None` 이다 —
        임의 선택 금지가 데이터 형태로 강제된다. GANGHOEHANG 두 후보는
        bl_form 이 다르므로("GANGHOEHANG"/"GANGHOEHANG B") 후보 전원 일치
        축약에 걸리지 않는다."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"port_of_loading": "GANGHOEHANG"})])

        [suggestion] = result.suggestions
        assert suggestion.requires_choice is True
        assert suggestion.to_be is None
        assert {c.term_id for c in suggestion.candidates} == {"PORT.KRAAA", "PORT.KRBBB"}

    def test_인접_필드는_반대_국가의_후보를_고른다(self):
        """선적항과 양하항이 같은 나라인 경우가 오히려 드물다 — 인접 필드의
        국가와 **다른** 국가인 후보를 남긴다(같은 국가로 좁히는 게 아니다).
        `_disambiguate` 를 직접 호출한다(위 테스트와 같은 이유)."""
        norm = Normalizer(stack=_stack())
        hits = norm.stack.lookup("PORTLAND", "port", alias=True)
        ref = FieldRef(doc="선하증권", field="port_of_loading")

        resolved = norm._disambiguate(
            _Run(documents=[]), ref, "port", "PORTLAND", hits, {"port_of_discharge": "NEW YORK, USA"}
        )

        # 인접(양하항)이 US 이므로 반대 국가인 AU 후보로 판별되어야 한다.
        assert resolved is not None
        assert resolved.term.term_id == "PORT.AUPTL"

    def test_동음이의_판별_후보는_1개로_못_줄이면_적용하지_않는다(self):
        """PORTLAND(US/AU) 를 국가 신호도 인접 신호도 없이 물으면 두 후보
        모두 남아야 한다 — 하나를 임의로 고르지 않는다. bl_form 이 서로
        다르므로("PORTLAND"/"PORTLAND VIC") 후보 전원 일치 축약에 걸리지
        않는다."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"port_of_loading": "PORTLAND"})])

        [suggestion] = result.suggestions
        assert suggestion.requires_choice is True
        assert len(suggestion.candidates) == 2


# ════════════════════════════════════════════════════════════════
# L/C 문언 우선
# ════════════════════════════════════════════════════════════════


class TestLC_문언_우선:
    def test_LC가_항구를_지정하면_표준코드를_제안하지_않는다(self):
        """사전 기반 교정(①②③④⑤)을 전부 끄고 `Notice(lc_wording)` 만 낸다."""
        norm = Normalizer(stack=_stack())
        lc = LCTerms(port_of_loading="BUSAN, KOREA")
        result = norm.normalize([_doc({"port_of_loading": "BUSAN"})], lc=lc)

        assert result.suggestions == []
        [notice] = result.notices
        assert notice.kind == "lc_wording"
        assert notice.severity == "info"
        [unevaluated] = result.unevaluated
        assert "L/C" in unevaluated.reason

    def test_LC_고정_필드도_format_단계는_허용한다(self):
        """L/C 가 값을 고정해도 공백 정리(⓪)까지 막지는 않는다 — 표기의
        글자 자체는 바꾸지 않으므로 L/C 와 저촉될 위험이 없다."""
        norm = Normalizer(stack=_stack())
        lc = LCTerms(port_of_loading="BUSAN, KOREA")
        result = norm.normalize([_doc({"port_of_loading": "BUSAN   KOREA"})], lc=lc)

        [suggestion] = result.suggestions
        assert suggestion.evidence.stage == "format"
        assert suggestion.to_be == "BUSAN KOREA"

    def test_LC와_값이_같아도_충돌이_아니어도_교정하지_않는다(self):
        """"충돌할 때만"이 아니라 **L/C 값이 있기만 하면** 끈다는 점에서
        기획안보다 보수적이다 — F3 의 판정과 F2 가 같은 자리에서 모순되지
        않게 하려는 의도다."""
        norm = Normalizer(stack=_stack())
        lc = LCTerms(port_of_loading="부산")  # 서류 값과 이미 같다(충돌 없음)
        result = norm.normalize([_doc({"port_of_loading": "부산"})], lc=lc)

        assert result.suggestions == []
        assert any(n.kind == "lc_wording" for n in result.notices)


# ════════════════════════════════════════════════════════════════
# 고유명사·품명 절제
# ════════════════════════════════════════════════════════════════


class Test고유명사_품명_절제:
    def test_품명은_공백_정규화_외에는_제안하지_않는다(self):
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"description_of_goods": "SAW   MACHINE"})])

        [suggestion] = result.suggestions
        assert suggestion.term_class == "goods"
        assert suggestion.evidence.stage == "format"
        assert suggestion.to_be == "SAW MACHINE"

    def test_당사자명은_공백_정규화_외에는_제안하지_않는다(self):
        """접미(CO.,LTD 등)가 없는 상호라 party_name 의 format 제안이
        조각 제안에 밀리지 않고 그대로 나가야 한다."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"shipper": "GAE  WOON  TRADING"})])

        [suggestion] = result.suggestions
        assert suggestion.term_class == "party_name"
        assert suggestion.evidence.stage == "format"
        assert suggestion.to_be == "GAE WOON TRADING"

    def test_상호_접미가_있으면_본체_전체치환은_양보한다(self):
        """접미(party_suffix, span 전용)가 있으면 필드 전체를 덮는
        party_name format 제안은 만들어지지 않는다 — 둘 다 승인되면 전체
        치환이 span 오프셋을 어긋나게 하므로, 더 구체적인 조각 쪽이
        남는다(`_process_field` 의 정지 조건)."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"shipper": "GAE WOON CO.,LTD"})])

        assert {s.term_class for s in result.suggestions} == {"party_suffix"}

    def test_상호_접미는_본체를_바이트_단위로_보존한다(self):
        norm = Normalizer(stack=_stack())
        value = "GAE WOON CO.,LTD"
        result = norm.normalize([_doc({"shipper": value})])

        [suggestion] = result.suggestions
        start, end = suggestion.field.span
        assert value[start:end] == suggestion.as_is == "CO.,LTD"
        assert suggestion.to_be == "Co., Ltd."
        # apply 가 실제로 만드는 결과를 흉내내 본체가 그대로인지 확인한다.
        applied = value[:start] + suggestion.to_be + value[end:]
        assert applied == "GAE WOON Co., Ltd."


# ════════════════════════════════════════════════════════════════
# 결정론 검증기 — 오류 알림 · not_covered
# ════════════════════════════════════════════════════════════════


class Test결정론_검증기_알림:
    def test_체크디지트가_틀리면_교정하지_않고_오류로_보고한다(self):
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"description_of_goods": "container MSKU1234560 here"})])

        assert not any(s.term_class == "container_no" for s in result.suggestions)
        [notice] = [n for n in result.notices if n.kind == "deterministic_error"]
        assert notice.severity == "warning"
        assert "체크디지트" in notice.message

    def test_구분자가_UJZ가_아니면_컨테이너로_보지_않는다(self):
        """클래스 오판 자체를 막는다 — 다른 번호 체계를 컨테이너로 오인해
        "체크디지트가 틀렸다"고 말하는 것이 침묵보다 나쁘다."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"description_of_goods": "code ABCK1234565 here"})])

        assert result.suggestions == []
        assert not any(n.kind == "deterministic_error" for n in result.notices)

    def test_Rec20_밖_단위는_추측하지_않고_not_covered로_알린다(self):
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"gross_weight": "500 BAGS"})])

        assert not any(s.term_class == "qty_unit" for s in result.suggestions)
        [notice] = [n for n in result.notices if n.kind == "not_covered"]
        assert notice.severity == "info"
        assert "BAGS" in notice.message

    def test_HSK_10단위_뒷자리는_지어내지_않는다(self):
        """관세율표 미적재 — 6단위만 확인하고 뒤 4자리를 만들지 않는다."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"description_of_goods": "HS 847130"})])

        [notice] = [n for n in result.notices if n.kind == "not_covered"]
        assert "HSK" in notice.message or "6단위" in notice.message

    def test_가격조건_장소가_없고_인접필드도_없으면_not_covered_경고다(self):
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"incoterms": "FOB"})])

        assert result.suggestions == []
        [notice] = [n for n in result.notices if n.kind == "not_covered"]
        assert notice.severity == "warning"

    def test_가격조건_장소가_없으면_인접필드에서_후보를_제시한다(self):
        norm = Normalizer(stack=_stack())
        result = norm.normalize(
            [_doc({"incoterms": "FOB", "port_of_loading": "BUSAN"})]
        )

        # port_of_loading 자체도 별도의 항구 제안(BUSAN→KRPUS)을 낸다 —
        # 가격조건 제안만 골라 본다.
        [suggestion] = [s for s in result.suggestions if s.term_class == "price_term"]
        assert suggestion.requires_choice is True
        assert suggestion.to_be is None
        assert "Incoterms 2020" in suggestion.candidates[0].to_be


# ════════════════════════════════════════════════════════════════
# 침묵 금지 — Unevaluated
# ════════════════════════════════════════════════════════════════


class Test침묵_금지:
    def test_클래스를_판별할_수_없으면_유보에_남는다(self):
        """`vessel` 은 의도적으로 어느 클래스에도 매핑되지 않은 필드다
        (`policy.py` "매핑에서 의도적으로 뺀 필드" 주석)."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"vessel": "MSC BIANCA"})])

        assert result.suggestions == []
        [unevaluated] = result.unevaluated
        assert unevaluated.field.field == "vessel"
        assert unevaluated.reason == "클래스를 판별할 수 없습니다"

    def test_빈_값은_유보를_만들지_않는다(self):
        """값이 없는 필드는 "판단 유보"가 아니라 판단할 대상 자체가 없다
        — 빈 서류 하나가 유보 목록을 잡음으로 채우면 안 된다."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"vessel": None, "port_of_loading": ""})])

        assert result.unevaluated == []

    def test_LC로_사전경로가_막히고_바꿀_것도_없으면_유보에_남는다(self):
        norm = Normalizer(stack=_stack())
        lc = LCTerms(port_of_loading="BUSAN")
        result = norm.normalize([_doc({"port_of_loading": "BUSAN"})], lc=lc)

        assert result.suggestions == []
        assert any(
            "L/C" in u.reason for u in result.unevaluated
        )


# ════════════════════════════════════════════════════════════════
# span 계약
# ════════════════════════════════════════════════════════════════


class TestSpan_계약:
    """`span` 이 있으면 `value[start:end] == as_is` 는 예외 없는 불변식이다."""

    def test_span_있는_모든_제안은_원문_부분문자열과_일치한다(self):
        norm = Normalizer(stack=_stack())
        document = _doc(
            {
                "gross_weight": "1,234.50 KGS",
                "description_of_goods": "MSKU 123456 5 HS8471.301000",
                "shipper": "GAE WOON CO.,LTD",
            }
        )
        result = norm.normalize([document])

        assert result.suggestions, "span 계약을 검사할 제안이 없다"
        checked_spans = 0
        for suggestion in result.suggestions:
            if suggestion.field.span is None:
                continue
            value = document.fields[suggestion.field.field]
            start, end = suggestion.field.span
            assert value[start:end] == suggestion.as_is
            checked_spans += 1
        assert checked_spans >= 3  # 단위·컨테이너·HS·접미 중 다수가 span 을 쓴다

    def test_단위_치환은_수치를_건드리지_않는다(self):
        """span 이 단위 토큰만 가리켜야 `apply` 가 수치를 복제하지 않는다
        (`HANDOFF.md` §4.5 의 실제 사고 사례)."""
        norm = Normalizer(stack=_stack())
        value = "1,234.50 KGS"
        result = norm.normalize([_doc({"gross_weight": value})])

        [suggestion] = result.suggestions
        start, end = suggestion.field.span
        assert value[:start] == "1,234.50 "
        applied = value[:start] + suggestion.to_be + value[end:]
        assert applied == "1,234.50 KGM"

    def test_HS_코드_스캔은_라벨을_span에서_제외한다(self):
        """`span` 이 `HS ` 라벨까지 포함하면 승인 시 라벨이 사라져 본문이
        바뀐다 — 코드 부분만 가리켜야 한다."""
        norm = Normalizer(stack=_stack())
        value = "HS8471.301000 declared"
        result = norm.normalize([_doc({"description_of_goods": value})])

        [suggestion] = [s for s in result.suggestions if s.term_class == "hs_code"]
        start, end = suggestion.field.span
        assert value[start:end] == suggestion.as_is
        assert not suggestion.as_is.upper().startswith("HS")


# ════════════════════════════════════════════════════════════════
# 겹침 해소
# ════════════════════════════════════════════════════════════════


def _span_suggestion(start: int, end: int, term_class: str) -> Suggestion:
    return Suggestion(
        suggestion_id="x",
        field=FieldRef(doc="d", field="f", span=(start, end)),
        as_is="v" * (end - start),
        to_be="X",
        term_class=term_class,
        evidence=Evidence(authority="t", term_id=None, glossary_version="v", tier="standard", stage="pattern"),
        confidence=0.9,
    )


class Test겹침_해소:
    def test_겹치는_span은_더_긴_쪽을_남긴다(self):
        wide = _span_suggestion(0, 10, "container_no")
        narrow = _span_suggestion(2, 6, "hs_code")

        kept = _resolve_overlaps([wide, narrow])

        assert [s.term_class for s in kept] == ["container_no"]

    def test_겹치지_않는_span은_둘_다_남는다(self):
        first = _span_suggestion(0, 5, "container_no")
        second = _span_suggestion(6, 10, "hs_code")

        kept = _resolve_overlaps([first, second])

        assert {s.term_class for s in kept} == {"container_no", "hs_code"}


# ════════════════════════════════════════════════════════════════
# 영향 범위
# ════════════════════════════════════════════════════════════════


class Test영향_범위:
    def test_영향_범위는_요청에_실린_다른_자리를_가리킨다(self):
        """같은 조각(`"CO.,LTD"`)이 다른 서류의 다른 필드에도 있으면
        `impact` 가 그 자리를 가리켜야 한다."""
        norm = Normalizer(stack=_stack())
        doc_a = _doc({"shipper": "GAE WOON CO.,LTD"}, doc_id="A")
        doc_b = _doc({"notify_party": "GAE WOON CO.,LTD"}, doc_id="B")
        result = norm.normalize([doc_a, doc_b])

        [suggestion] = [s for s in result.suggestions if s.field.doc_id == "A"]
        assert len(suggestion.impact) == 1
        impacted = suggestion.impact[0]
        assert impacted.doc_id == "B"
        assert impacted.field == "notify_party"

    def test_영향_범위는_자기_자신을_제외한다(self):
        norm = Normalizer(stack=_stack())
        result = norm.normalize([_doc({"shipper": "GAE WOON CO.,LTD"}, doc_id="A")])

        [suggestion] = result.suggestions
        assert suggestion.impact == []


# ════════════════════════════════════════════════════════════════
# 자유서식 문구 스캔
# ════════════════════════════════════════════════════════════════


class Test자유서식_문구_스캔:
    def test_관행_문구를_본문에서_찾는다(self):
        norm = Normalizer(stack=_stack())
        result = norm.normalize(
            [_doc({"description_of_goods": "shipment note: SURR confirmed"})]
        )

        found = [s for s in result.suggestions if s.term_class == "practice_phrase"]
        assert any(s.as_is == "SURR" for s in found)
        assert all(s.to_be == "Surrendered B/L" for s in found)

    def test_최소_길이_미만_약어는_스캔하지_않는다(self):
        """`_MIN_SCAN_SURFACE_LEN=4` — 짧은 약어는 자유서식 본문의 흔한
        단어와 충돌해 오제안을 낸다(정밀도 우선 원칙)."""
        norm = Normalizer(stack=_stack())
        result = norm.normalize(
            [_doc({"description_of_goods": "please check the SUR carefully"})]
        )

        assert not any(s.as_is == "SUR" for s in result.suggestions)


# ════════════════════════════════════════════════════════════════
# 판정 재현성
# ════════════════════════════════════════════════════════════════


class Test판정_재현성:
    def test_같은_입력은_같은_결과다(self):
        norm = Normalizer(stack=_stack())
        document = _doc(
            {
                "port_of_loading": "부산",
                "gross_weight": "1,234.50 KGS",
                "description_of_goods": "MSKU 123456 5",
                "shipper": "GAE WOON CO.,LTD",
            }
        )

        first = norm.normalize([document])
        second = norm.normalize([document])

        def _strip_timing(payload: dict) -> dict:
            payload = dict(payload)
            payload["stats"] = {k: v for k, v in payload["stats"].items() if k != "elapsed_ms"}
            return payload

        assert _strip_timing(first.to_dict()) == _strip_timing(second.to_dict())

    def test_suggestion_id는_결정론적이다(self):
        norm = Normalizer(stack=_stack())
        document = _doc({"port_of_loading": "부산"})

        first = _suggestion_ids(norm.normalize([document]))
        second = _suggestion_ids(norm.normalize([document]))

        assert first == second
        assert all(sid.startswith("sg1_") for sid in first)


# ════════════════════════════════════════════════════════════════
# 통계
# ════════════════════════════════════════════════════════════════


class Test통계:
    def test_by_stage_합계는_제안_수와_같다(self):
        """`_register` 시점이 아니라 `normalize()` 끝에서 한 번에 세는
        이유를 검증한다 — ⑤ 확정이 stage 를 바꾸거나 제안을 지운 뒤의
        최종 상태와 항상 일치해야 한다."""
        norm = Normalizer(stack=_stack())
        document = _doc(
            {
                "port_of_loading": "KRPUS,",  # exact
                "port_of_discharge": "부산",  # alias
                "gross_weight": "1,234.50 KGS",  # pattern(verified)
                "description_of_goods": "SAW   MACHINE",  # format
            }
        )
        result = norm.normalize([document])

        assert sum(result.stats.by_stage.values()) == len(result.suggestions)
        assert len(result.suggestions) >= 4

    def test_llm_path_기본값은_not_called다(self):
        norm = Normalizer(stack=_stack())  # selector=None
        result = norm.normalize([_doc({"port_of_loading": "부산"})], llm=True)

        assert result.stats.llm_path == "not_called"
        assert result.stats.llm_calls == 0
