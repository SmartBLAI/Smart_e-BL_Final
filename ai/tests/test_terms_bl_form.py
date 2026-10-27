"""F2 `bl_form`(B/L 면 항구명) 회귀 테스트.

배경: F2 가 항구 필드를 UN/LOCODE 코드(예: `KRPUS`)로 제안하면, F3 룰
엔진이 UCP 600 제20조(서류는 L/C 문언과 일치해야 한다)에 따라 D003/D004
위양성 판정을 낸다 — 코드는 선박회사가 발행하는 B/L 면에 인쇄되지 않기
때문이다(EDIFACT·세관 매니페스트·DCSA eBL 데이터 레이어 전용). 이 파일은
그 회귀를 막는다: 제안은 `canonical`(코드)이 아니라 `bl_form`(B/L 면
항구명)을 써야 한다.
"""

from __future__ import annotations

from f2_terms.cascade import DocumentInput, Normalizer
from f2_terms.glossary import Glossary, GlossaryStack, load_glossary
from f2_terms.types import GlossaryTerm


def _term(term_id: str, canonical: str, aliases=(), country=None, bl_form=None) -> GlossaryTerm:
    return GlossaryTerm(
        term_id=term_id,
        category="port",
        canonical=canonical,
        lang="en",
        authority="TEST",
        version="test-1",
        effective_date="2026-01-01",
        aliases=list(aliases),
        country=country,
        bl_form=bl_form,
    )


class Test카탈로그_전수_검증:
    # 의도적 예외 목록 — 지금은 비어 있다(52/52 항구가 bl_form 을 가진다).
    # 새 예외가 생기면 이유와 함께 여기 추가하고, 그 전까지는 이 테스트가
    # 빠진 항목을 이름으로 잡아낸다.
    _KNOWN_MISSING: set = set()

    def test_표준_카탈로그의_모든_항구_항목이_bl_form을_가진다(self):
        """의도적 예외(`_KNOWN_MISSING`) 밖에서 bl_form 이 빠지면 이
        테스트가 이름을 댄다 — 조용히 넘어가지 않는다."""
        glossary = load_glossary()
        ports = [t for t in glossary.terms if t.category == "port"]

        assert ports, "카탈로그에 항구 항목이 없다 — 이 테스트가 검증할 대상이 없다"
        missing = {t.term_id for t in ports if not t.bl_form}

        assert missing == self._KNOWN_MISSING, f"bl_form 이 없는 항구 항목: {sorted(missing)}"


class Test제안은_코드가_아니라_bl_form이다:
    def test_PUSAN은_코드가_아니라_BUSAN을_제안한다(self):
        """구표기(PUSAN)를 표준 표기로 교정하되, 그 표준 표기는 코드
        (`KRPUS`)가 아니라 B/L 면 항구명(`BUSAN`)이어야 한다."""
        stack = GlossaryStack([load_glossary()])
        norm = Normalizer(stack=stack)
        result = norm.normalize([DocumentInput(doc="선하증권", fields={"port_of_loading": "PUSAN"})])

        [suggestion] = result.suggestions
        assert suggestion.to_be == "BUSAN"
        assert "KRPUS" not in suggestion.to_be
        assert suggestion.message and "KRPUS" not in suggestion.message

    def test_BUSAN_KOREA는_이미_bl_form을_담고_있어_제안하지_않는다(self):
        """`as_is` 토큰이 이미 `bl_form` 을 부분집합으로 담고 있으면
        (`"BUSAN, KOREA"` ⊇ `"BUSAN"`) 무의미한 카드를 만들지 않는다."""
        stack = GlossaryStack([load_glossary()])
        norm = Normalizer(stack=stack)
        result = norm.normalize([DocumentInput(doc="선하증권", fields={"port_of_loading": "BUSAN, KOREA"})])

        assert result.suggestions == []

    def test_공백_섞인_코드도_코드가_아니라_BUSAN을_제안한다(self):
        """③pattern 단계 — `"KR PUS"` 는 공백 때문에 exact/alias 를 놓치고
        정규화하면 `"KRPUS"`(형식만 유효한 코드)가 된다. 예전에는 이 코드를
        그대로 `to_be` 로 냈다 — 사전에 있는 항구인데도 코드가 서류 면에
        박히는 회귀였다. 지금은 정규화된 코드를 사전에서 역조회해
        `bl_form`(BUSAN)을 낸다."""
        stack = GlossaryStack([load_glossary()])
        norm = Normalizer(stack=stack)
        result = norm.normalize([DocumentInput(doc="선하증권", fields={"port_of_loading": "KR PUS"})])

        [suggestion] = result.suggestions
        assert suggestion.to_be == "BUSAN"
        assert "KRPUS" not in suggestion.to_be

    def test_사전에_없는_코드는_형식만_맞아도_제안하지_않는다(self):
        """`"US SEA"` → `"USSEA"` 는 LOCODE 형식(대문자 5글자)은 맞지만
        사전 어디에도 없는 코드다. 형식만 맞다고 없는 표기를 지어내지
        않는다 — 제안 없이 유보로 남는다."""
        stack = GlossaryStack([load_glossary()])
        norm = Normalizer(stack=stack)
        result = norm.normalize([DocumentInput(doc="선하증권", fields={"port_of_loading": "US SEA"})])

        assert result.suggestions == []
        assert "USSEA" not in [s.to_be for s in result.suggestions]
        assert any("사전에 없는 항구 코드" in u.reason for u in result.unevaluated)


class Test선택_카드는_결과가_있어야_한다:
    def test_PORTLAND_동음이의는_후보가_같아_카드를_만들지_않는다(self):
        """`PORTLAND` 는 USPDX/AUPTJ 두 항구의 별칭이지만 둘 다
        `bl_form="PORTLAND"` 다 — 어느 쪽을 골라도 서류 면 값이 안 바뀐다.
        `_build` 가 `requires_choice` 를 접어 `to_be="PORTLAND"` 결정
        하나로 만들고, 그 값이 원문과 같아 일반 무카드 조건(`to_be ==
        as_is`)에 조용히 걸린다 — 그 조건이 원래 그렇듯 `Unevaluated` 를
        남기지 않는다(`test_이미_표준인_값은_제안하지_않는다` 와 같은
        규약)."""
        stack = GlossaryStack([load_glossary()])
        norm = Normalizer(stack=stack)
        result = norm.normalize([DocumentInput(doc="선하증권", fields={"port_of_loading": "PORTLAND"})])

        assert result.suggestions == []

    def test_PORTLAND_PORT_동음이의는_토큰_부분집합으로_카드를_만들지_않는다(self):
        """`"PORTLAND PORT"` 는 위와 같은 이유로 `to_be="PORTLAND"` 결정
        하나로 접히지만, 원문과 글자가 똑같지는 않다(무카드 조건 미해당).
        대신 원문 토큰 {PORTLAND, PORT} 가 `to_be` 토큰 {PORTLAND} 를
        포함하므로 항구 토큰 부분집합 억제에 걸려 역시 카드를 만들지
        않는다 — 접힌 결정이 기존 정지 조건을 그대로 탄다는 뜻이다."""
        stack = GlossaryStack([load_glossary()])
        norm = Normalizer(stack=stack)
        result = norm.normalize(
            [DocumentInput(doc="선하증권", fields={"port_of_loading": "PORTLAND PORT"})]
        )

        assert result.suggestions == []


class Test사전에_bl_form이_없으면_유보한다:
    def test_bl_form_없는_항구는_제안_대신_유보로_남는다(self):
        """`_applied_form` 은 `bl_form` 이 없는 포트 용어를 절대 `canonical`
        (코드)로 조용히 되돌리지 않는다 — 유보(`Unevaluated`)로 남긴다."""
        terms = [_term("PORT.ZZTST", "ZZTST", aliases=("테스트항",), country="ZZ", bl_form=None)]
        glossary = Glossary(terms, catalog_version="test-1", effective_date="2026-01-01")
        stack = GlossaryStack([glossary])
        norm = Normalizer(stack=stack)

        result = norm.normalize([DocumentInput(doc="선하증권", fields={"port_of_loading": "테스트항"})])

        assert result.suggestions == []
        assert "ZZTST" not in [s.to_be for s in result.suggestions]
        # 단계마다(①②...) bl_form 부재를 각자 기록하지만, 같은 필드·같은
        # 사유는 `normalize()` 가 한 건으로 접는다(§Unevaluated 중복 제거).
        assert len(result.unevaluated) == 1
        assert "선하증권 표기" in result.unevaluated[0].reason
