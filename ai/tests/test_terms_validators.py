"""F2 결정론 검증기 테스트 — ISO 6346 · UN/ECE Rec 20 · Incoterms 2020 ·
HS/HSK · UN/LOCODE 형식 · 상호 접미.

`docs/f2/HANDOFF.md` §4.9 "100% 를 주장할 수 있는 것과 없는 것" 표를 그대로
따라 검증 범위를 확인한다 — 특히 ISO 6346 체크디지트의 `(sum%11)%10` 접힘
사각지대는 **정직하게 재현**해야 한다(감추면 그 자체가 §1 원칙 위반이다).
"""

from __future__ import annotations

import pytest

from f2_terms.validators import (
    INCOTERMS_2020,
    container_check_digit,
    incoterms_consistent_with_checks,
    normalize_hs,
    normalize_locode,
    party_suffix,
    parse_price_term,
    split_quantity,
    unit_code,
    validate_container,
    validate_locode,
)


# ════════════════════════════════════════════════════════════════
# ISO 6346 — 컨테이너 번호
# ════════════════════════════════════════════════════════════════


class Test컨테이너번호:
    def test_표준_예제의_체크디지트는_3이다(self):
        """ISO 6346 부속서의 표준 예제(`CSQU3054383`) — 몸체 `CSQU305438`
        의 체크디지트가 3이어야 한다."""
        assert container_check_digit("CSQU305438") == 3

    def test_표준_예제_전체가_유효하다고_판정한다(self):
        result = validate_container("CSQU3054383")

        assert result.matched
        assert result.ok is True
        assert result.expected_digit == 3

    def test_체크디지트가_틀리면_ok가_거짓이다(self):
        result = validate_container("CSQU3054384")

        assert result.matched
        assert result.ok is False
        assert result.expected_digit == 3
        assert result.found_digit == 4

    def test_체크디지트가_틀려도_교정값을_만들지_않는다(self):
        """어느 자리가 틀렸는지 이 검사만으로는 알 수 없으므로, 이 타입은
        '고친 값'을 지어내지 않는다 — 사실만 돌려준다."""
        result = validate_container("CSQU3054384")

        assert not hasattr(result, "corrected")
        assert result.normalized == "CSQU3054384"  # 원문 그대로, 정정 아님

    @pytest.mark.parametrize("suffix", ["A", "K", "X", "Y"])
    def test_장비구분자가_UJZ가_아니면_판정하지_않는다(self, suffix):
        # U(화물)·J(분리형 장비)·Z(트레일러/섀시) 이외는 컨테이너 번호로
        # 오판하지 않는다 — 클래스 오판은 침묵보다 나쁘다.
        result = validate_container(f"CSQ{suffix}3054383")

        assert result.matched is False
        assert result.ok is None

    def test_소문자도_인식한다(self):
        result = validate_container("csqu3054383")

        assert result.matched
        assert result.ok is True

    def test_컨테이너_번호가_없는_텍스트는_매칭되지_않는다(self):
        result = validate_container("이 문장에는 컨테이너 번호가 없습니다")

        assert result.matched is False
        assert result.normalized is None
        assert result.ok is None

    def test_공백이_섞여도_형식을_인식한다(self):
        # 실무 표기가 "MSKU 123456 5" 처럼 공백으로 나뉘어 오는 경우.
        result = validate_container("MSKU 123456 5")

        assert result.matched
        assert result.normalized == "MSKU1234565"

    def test_체크디지트_사각지대_단일문자_오류가_통과한다(self):
        """ISO 6346 자체의 알려진 성질(`f2-standard-terms.md` §"ISO 6346 의
        사각지대"): 마지막 `% 10` 때문에 나머지 10 과 나머지 0 이 둘 다
        체크디지트 0 으로 접힌다.

        `AAIU000000`(몸체 합계 나머지 10, 체크디지트 0)과
        `AAIU000002`(몸체 합계 나머지 0, 체크디지트도 0) 는 일련번호
        마지막 한 글자(`0`→`2`)만 다른 서로 다른 번호인데 **같은 체크디지트로
        접힌다** — 원래 번호가 `AAIU0000000` 인데 마지막 일련번호 자리가
        `2`로 오타 났어도(`AAIU0000020`), 원래 체크디지트 `0`을 그대로
        옮겨 적으면 이 함수는 `ok=True`로 판정한다. 이것이 "단일 문자 오류
        검출률 100%"가 이 함수에 대해 사실이 아닌 구체적인 사례다.
        """
        original = container_check_digit("AAIU000000")
        typo_body = container_check_digit("AAIU000002")

        assert original == typo_body == 0

        # 오타난 몸체에 원래 체크디지트를 그대로 붙이면 "정상"으로 읽힌다.
        undetected = validate_container("AAIU0000020")
        assert undetected.ok is True  # 실제로는 몸체가 오타났는데도 통과


# ════════════════════════════════════════════════════════════════
# UN/ECE Recommendation 20 — 수량·용적 단위
# ════════════════════════════════════════════════════════════════


class TestRec20단위:
    def test_KGS는_KGM으로_조회된다(self):
        assert unit_code("KGS").code == "KGM"

    def test_M3는_MTQ로_조회된다(self):
        assert unit_code("M3").code == "MTQ"

    def test_M은_MTR로_조회된다(self):
        assert unit_code("M").code == "MTR"

    def test_M3와_M이_접두로_충돌하지_않는다(self):
        """부분 일치를 허용하면 `M3`이 `M`(MTR)으로 먼저 잡힌다 — 전체
        일치로만 조회해야 이 둘이 서로 다른 코드로 남는다."""
        assert unit_code("M3").code != unit_code("M").code
        assert unit_code("M3").code == "MTQ"
        assert unit_code("M").code == "MTR"

    def test_윗첨자_M3_표기도_NFKC로_흡수한다(self):
        assert unit_code("M³").code == "MTQ"

    def test_점이_있는_변형을_흡수한다(self):
        assert unit_code("K.G.S").code == "KGM"
        assert unit_code("M.T.").code == "TNE"
        assert unit_code("C.B.M.").code == "MTQ"

    def test_대소문자_공백을_구분하지_않는다(self):
        assert unit_code("  kg  ").code == "KGM"

    def test_집합_밖의_단위는_None이다(self):
        # 닫힌 집합이다 — "비슷한 단위"를 추측하지 않는다.
        assert unit_code("XYZ") is None

    def test_포장_단위는_미검증으로_등록된다(self):
        assert unit_code("CTN").verified is False

    def test_Piece는_Rec21_PP이고_PCE_구코드도_PP로_받는다(self):
        for token in ("PCS", "PC", "PIECE", "PCE"):
            assert unit_code(token).code == "PP"

    def test_핵심_6종은_검증됨으로_등록된다(self):
        assert unit_code("KGM").verified is True
        assert unit_code("MTR").verified is True

    def test_split_quantity는_수치와_단위를_가른다(self):
        text = "1,234.50 KGS"

        result = split_quantity(text)

        assert result is not None
        number, unit, span = result
        assert number == "1,234.50"
        assert unit == "KGS"
        assert text[span[0]:span[1]] == "KGS"

    def test_split_quantity는_수치를_변형하지_않는다(self):
        number, _unit, _span = split_quantity("1,234.50 KGS")

        assert number == "1,234.50"  # 콤마·자릿수 그대로

    def test_split_quantity_매칭_실패시_None(self):
        assert split_quantity("가격 정보 없음") is None


# ════════════════════════════════════════════════════════════════
# Incoterms 2020
# ════════════════════════════════════════════════════════════════


class TestIncoterms:
    def test_조건과_장소를_분리한다(self):
        result = parse_price_term("FOB BUSAN")

        assert result is not None
        assert result.code == "FOB"
        assert result.place == "BUSAN"

    def test_장소가_없으면_place는_None이다(self):
        assert parse_price_term("FOB").place is None

    def test_F_O_B_점_표기를_흡수한다(self):
        result = parse_price_term("F.O.B BUSAN")

        assert result.code == "FOB"
        assert result.place == "BUSAN"

    def test_정상_코드는_exact_깨진_표기는_토큰_구간을_돌려준다(self):
        exact = parse_price_term("FOB BUSAN")
        assert exact.exact and exact.token_span == (0, 3)

        broken = parse_price_term("F.O.B. BUSAN")
        assert not broken.exact and broken.token_span == (0, 6)  # 끝 점까지

        assert not parse_price_term("F O B").exact

    def test_Incoterms가_아닌_3글자는_None이다(self):
        # 클래스 오판 방지 — 컨테이너 번호와 같은 논거.
        assert parse_price_term("XXX BUSAN") is None

    def test_형식이_아니면_None이다(self):
        assert parse_price_term("") is None

    def test_checks_INCOTERMS와_같은_집합이다(self):
        assert incoterms_consistent_with_checks() is True

    def test_INCOTERMS_2020은_11개_조건이다(self):
        assert len(INCOTERMS_2020) == 11


# ════════════════════════════════════════════════════════════════
# HS / HSK
# ════════════════════════════════════════════════════════════════


class TestHS코드:
    def test_6단위_형식을_정규화한다(self):
        result = normalize_hs("847130")

        assert result.normalized == "8471.30"

    def test_이미_점찍힌_형식도_받는다(self):
        assert normalize_hs("8471.30").normalized == "8471.30"

    def test_HS_접두를_허용한다(self):
        assert normalize_hs("HS 8471.30").normalized == "8471.30"

    def test_6단위만_주어지면_뒤_4자리를_만들지_않는다(self):
        """관세율표 미적재 — 지어내지 않는다는 §1 원칙의 결정론 검증기
        구현. `hsk_present=False` 로 호출부가 `Notice(not_covered)` 를
        만들게 한다."""
        result = normalize_hs("847130")

        assert result.hsk is None
        assert result.hsk_present is False

    def test_10단위가_주어지면_그대로_보존한다(self):
        result = normalize_hs("8471.30-1000")

        assert result.hsk == "8471.30-1000"
        assert result.hsk_present is True

    def test_형식이_아니면_None이다(self):
        assert normalize_hs("품목분류없음") is None


# ════════════════════════════════════════════════════════════════
# UN/LOCODE — 형식만
# ════════════════════════════════════════════════════════════════


class TestLOCODE형식:
    def test_정상_형식을_통과시킨다(self):
        result = validate_locode("KRPUS")

        assert result.ok is True
        assert result.country == "KR"

    def test_공백을_지우고_대문자화한다(self):
        assert normalize_locode("KR PUS") == "KRPUS"
        assert normalize_locode("krpus") == "KRPUS"

    def test_3자리_지역코드에_0은_불가하다(self):
        # UN/LOCODE 는 자모와 혼동되는 0·1 을 지역 코드에 쓰지 않는다.
        assert validate_locode("KRP0S").ok is False

    def test_3자리_지역코드에_1은_불가하다(self):
        assert validate_locode("KRP1S").ok is False

    def test_형식이_아니면_country가_비어있다(self):
        result = validate_locode("XY0")

        assert result.ok is False
        assert result.country is None

    def test_5자를_넘으면_형식이_아니다(self):
        assert validate_locode("KRPUSAN").ok is False


# ════════════════════════════════════════════════════════════════
# 상호 접미 (party_suffix)
# ════════════════════════════════════════════════════════════════


class Test상호접미:
    def test_span은_접미_토큰만_가리킨다(self):
        """`HANDOFF.md` §4.8 예시 그대로 — span 이 상호 본체를 포함하면
        안 된다. `apply` 가 지키는 게 아니라 span 이 구조적으로 강제한다."""
        text = "GAE WOON CO.,LTD"

        result = party_suffix(text)

        assert result.matched
        assert text[result.span[0]:result.span[1]] == result.as_is == "CO.,LTD"

    def test_상호_본체는_span_밖에_있다(self):
        text = "GAE WOON CO.,LTD"

        result = party_suffix(text)

        body = text[:result.span[0]]
        assert body == "GAE WOON "
        assert "GAE WOON" not in result.as_is

    def test_두_토큰_접미를_표준_표기로_이어붙인다(self):
        result = party_suffix("DHHJ FRANCHISING CO., LTD.")

        assert result.to_be == "Co., Ltd."

    def test_접미가_없으면_매치하지_않는다(self):
        result = party_suffix("GAE WOON TRADING")

        assert result.matched is False
        assert result.span is None
        assert result.to_be is None

    def test_대소문자와_무관하게_인식한다(self):
        result = party_suffix("gae woon co.,ltd")

        assert result.matched
        assert result.to_be == "Co., Ltd."

    def test_PTE_LTD는_ISO20275_등록_약어_Pte_Ltd다(self):
        # 점도 쉼표도 없는 등록 약어. "Pte., Ltd." 가 아니다.
        for text in ("ACME PTE LTD", "ACME PTE. LTD.", "ACME Pte., Ltd."):
            assert party_suffix(text).to_be == "Pte Ltd"
