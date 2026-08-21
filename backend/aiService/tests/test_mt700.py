"""MT700 원문 파서 — 기획안 v2 5.1 입력 사양.

검사의 무게는 "읽었는가"보다 **"못 읽은 것을 말하는가"** 에 있다. L/C 조건이
비면 그 조건을 쓰는 룰이 평가불가로 빠지고, 위반 0건은 화면에서 '하자 없음'
으로 읽힌다. 조용한 실패가 안전해 보이는 구조라 그쪽을 집중적으로 잡는다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from ocr.types import BLFields
from ruleEngine import LCTerms, MT700ParseError, RuleEngine, parse_mt700
from ruleEngine.checks import parse_amount

# 실무 전문에 가까운 최소 형태. 값은 test_rule_engine 의 정상 픽스처와 맞춘다.
MESSAGE = """\
:20:LC-2026-101
:31D:261231SEOUL
:32B:USD123456,78
:39A:10/10
:43P:NOT ALLOWED
:43T:ALLOWED
:44C:260630
:44E:BUSAN, KOREA
:44F:TOKYO, JAPAN
:45A:SAW MACHINE
+FOB BUSAN INCOTERMS 2020
:46A:+SIGNED COMMERCIAL INVOICE IN 3 COPIES
+FULL SET OF CLEAN ON BOARD OCEAN BILL OF LADING
+PACKING LIST IN 2 COPIES
:47A:ALL DOCUMENTS MUST BEAR THE CREDIT NUMBER
:48:21/DAYS AFTER SHIPMENT DATE
:50:DHHJ FRANCHISING CO., LTD.
1-2 SHIBUYA, TOKYO, JAPAN
:59:/1234567890
GAE WOON CO., LTD.
BUSAN, KOREA
"""


@pytest.fixture
def parsed():
    return parse_mt700(MESSAGE)


class Test태그_분해:
    def test_필드를_읽는다(self, parsed):
        lc = parsed.lc

        assert lc.lc_no == "LC-2026-101"
        assert lc.port_of_loading == "BUSAN, KOREA"
        assert lc.port_of_discharge == "TOKYO, JAPAN"

    def test_여러_줄_값을_이어_붙인다(self, parsed):
        # 45A 는 다음 태그가 나오기 전까지 전부 한 필드다. 첫 줄만 읽으면
        # 물품 명세가 잘려 D006(명세 대조)이 정상 서류를 하자로 잡는다.
        assert parsed.lc.description_of_goods == "SAW MACHINE FOB BUSAN INCOTERMS 2020"

    def test_요구_서류를_목록으로_만든다(self, parsed):
        docs = parsed.lc.documents_required

        assert len(docs) == 3
        assert docs[0] == "SIGNED COMMERCIAL INVOICE IN 3 COPIES"
        # 줄머리 `+` 는 SWIFT 연속 줄 표시이지 서류명의 일부가 아니다.
        assert not any(d.startswith("+") for d in docs)

    def test_당사자는_상호_줄만_쓴다(self, parsed):
        # 주소까지 붙이면 상호 대조가 주소 표기 차이로 어긋난다.
        assert parsed.lc.applicant == "DHHJ FRANCHISING CO., LTD."
        # 59 의 첫 줄은 계좌번호다. 그걸 상호로 쓰면 전건 불일치가 된다.
        assert parsed.lc.beneficiary == "GAE WOON CO., LTD."

    def test_블록_구조를_벗긴다(self):
        wrapped = "{1:F01BANKKRSEAXXX}{2:I700BANKJPJTXXXN}{4:\n" + MESSAGE + "\n-}"

        assert parse_mt700(wrapped).lc.lc_no == "LC-2026-101"

    def test_CRLF_전문도_읽는다(self):
        # SWIFT 전문은 CRLF 로 온다. 줄 끝 처리가 없으면 태그 정규식이
        # 줄 앞을 못 잡아 통째로 실패한다.
        assert parse_mt700(MESSAGE.replace("\n", "\r\n")).lc.lc_no == "LC-2026-101"

    def test_태그가_없으면_예외다(self):
        # 빈 LCTerms 를 돌려주면 L/C 룰이 전부 평가불가로 빠지고, 그 결과는
        # 화면에서 '하자 없음'으로 읽힌다. 조용한 실패를 만들지 않는다.
        with pytest.raises(MT700ParseError):
            parse_mt700("첨부 참조 바랍니다.")

    def test_중복_태그는_첫_값을_지킨다(self):
        result = parse_mt700(":20:LC-1\n:44E:BUSAN\n:44E:INCHEON\n")

        assert result.lc.port_of_loading == "BUSAN"
        assert any("두 번 이상" in n for n in result.notes)


class Test정규화:
    def test_YYMMDD_를_ISO_로_바꾼다(self, parsed):
        # 룰의 `parse_date` 는 YYMMDD 형식을 모른다. 여기서 바꾸지 않으면
        # 날짜 룰이 전부 '해석 실패'로 빠진다.
        assert parsed.lc.expiry_date == "2026-12-31"
        assert parsed.lc.latest_shipment_date == "2026-06-30"

    def test_사람이_적은_날짜_형식도_받는다(self):
        result = parse_mt700(":20:LC-1\n:44C:2026-06-30\n")

        assert result.lc.latest_shipment_date == "2026-06-30"

    def test_달력에_없는_날짜는_비우고_알린다(self):
        result = parse_mt700(":20:LC-1\n:44C:260631\n")

        assert result.lc.latest_shipment_date is None
        assert any("달력에 없습니다" in n for n in result.notes)

    def test_SWIFT_콤마는_소수점이다(self, parsed):
        # 회귀: `USD123456,78` 을 그대로 두면 parse_amount 가 콤마를
        # 천단위로 보고 지워 **금액이 100배**가 된다. 송장 금액 초과(X009)가
        # 통과해 버리는 조용한 실패다.
        assert parse_amount(parsed.lc.currency_amount) == pytest.approx(123456.78)
        assert parsed.lc.currency == "USD"

    def test_사람이_적은_금액_표기도_같은_값이_된다(self):
        result = parse_mt700(":20:LC-1\n:32B:USD 123,456.78\n")

        assert parse_amount(result.lc.currency_amount) == pytest.approx(123456.78)

    def test_금지를_허용으로_뒤집지_않는다(self, parsed):
        # `NOT ALLOWED` 는 `ALLOWED` 를 품고 있다. 부분 일치로 판정하면
        # 분할선적 금지가 허용으로 뒤집혀 D013 이 통째로 잠든다.
        assert parsed.lc.partial_shipment == "PROHIBITED"
        assert parsed.lc.transhipment == "ALLOWED"

    def test_판정할_수_없는_금지조건은_기본값을_두고_알린다(self):
        result = parse_mt700(":20:LC-1\n:43P:CONDITIONAL\n")

        # UCP 600 상 명시가 없으면 허용이 기본이다. 임의로 금지로 잡으면
        # 정상 건이 하자가 된다.
        assert result.lc.partial_shipment == "ALLOWED"
        assert any("43P" in n for n in result.notes)

    def test_제시기간을_읽는다(self, parsed):
        assert parsed.lc.presentation_days == 21

    def test_비대칭_허용오차는_엄격한_쪽을_쓴다(self):
        result = parse_mt700(":20:LC-1\n:39A:10/05\n")

        # 룰의 허용 오차는 대칭 한 값이다. 큰 쪽을 쓰면 초과분을 놓친다.
        assert result.lc.tolerance_pct == 5.0
        assert any("비대칭" in n for n in result.notes)


class Test버린_것을_말한다:
    def test_47A는_한도만_옮기고_나머지는_버린다(self, parsed):
        # MESSAGE 의 47A(ALL DOCUMENTS MUST BEAR THE CREDIT NUMBER)에는
        # 총중량·용적 한도가 없다. 핸들러는 있지만(더 이상 unmapped 가
        # 아니다) 뽑을 게 없으면 조용히 None 을 유지해야 한다 — 없는 한도를
        # 지어내면 정상 서류가 D007/D007B 에 걸린다.
        assert "47A" not in parsed.unmapped
        assert parsed.lc.max_gross_weight_kg is None
        assert parsed.lc.max_measurement_cbm is None

    def test_모르는_태그도_버리지_않는다(self):
        result = parse_mt700(":20:LC-1\n:99Z:정체불명\n")

        assert result.unmapped["99Z"] == "정체불명"

    def test_47A에_코드가_없으면_45A에서_거래조건을_채운다(self, parsed):
        # MESSAGE 의 47A(ALL DOCUMENTS MUST BEAR THE CREDIT NUMBER)에는
        # 거래조건 표기가 없다. 45A 의 `FOB` 로 채워진다 — 코드만, 장소
        # 병기(`FOB BUSAN`)는 담지 않는다. 담으면 송장의 표기와 어긋나
        # 동등 비교(X010)가 정상 서류를 하자로 잡는다.
        assert parsed.lc.incoterms == "FOB"
        assert any("45A" in n and "FOB" in n for n in parsed.notes)

    def test_31D_유효장소를_버렸다고_알린다(self, parsed):
        assert any("SEOUL" in n for n in parsed.notes)

    def test_원문_태그를_그대로_보존한다(self, parsed):
        # 정규화가 틀렸을 때 원문과 대조할 수 있어야 한다.
        assert parsed.tags["32B"] == "USD123456,78"


class Test거래조건_추출:
    """47A 우선, 없으면 45A. 코드만 담고 장소 병기는 담지 않는다."""

    def test_47A_에서_거래조건을_뽑는다(self):
        result = parse_mt700(
            ":20:LC-1\n:45A:MACHINE PARTS\n:47A:SHIPMENT ON FOB BUSAN BASIS, INCOTERMS 2020\n"
        )

        assert result.lc.incoterms == "FOB"
        assert any("47A" in n and "FOB" in n for n in result.notes)

    def test_47A가_45A보다_우선한다(self):
        # 45A 에 다른 코드가 있어도 47A 에 코드가 있으면 47A 를 쓴다.
        result = parse_mt700(":20:LC-1\n:45A:MACHINE PARTS CIF\n:47A:SHIPMENT ON FOB BASIS\n")

        assert result.lc.incoterms == "FOB"

    def test_코드가_2개면_채우지_않는다(self):
        # 임의로 하나를 고르면 신용장이 말하지 않은 거래조건을 지어내는 것이다.
        result = parse_mt700(":20:LC-1\n:47A:EITHER FOB BUSAN OR CIF HAMBURG ACCEPTABLE\n")

        assert result.lc.incoterms is None
        assert any("여럿" in n for n in result.notes)

    def test_어느_태그에도_코드가_없으면_비운다(self):
        result = parse_mt700(":20:LC-1\n:45A:MACHINE PARTS\n:47A:CREDIT NUMBER MUST APPEAR\n")

        assert result.lc.incoterms is None


class Test수하인_지정_추출:
    """46A B/L 요구 항목의 지시식/기명식 — D027 이 이 값을 쓴다."""

    def test_지시식_요구는_bl_consignment로_간다(self):
        result = parse_mt700(
            ":20:LC-1\n:46A:+FULL SET OF CLEAN ON BOARD OCEAN BILL OF LADING MADE OUT TO ORDER\n"
        )

        assert result.lc.bl_consignment == "TO_ORDER"
        assert result.lc.consignee is None

    def test_TO_ORDER_OF_은행도_지시식으로_잡는다(self):
        result = parse_mt700(
            ":20:LC-1\n:46A:+FULL SET OF CLEAN ON BOARD B/L TO ORDER OF ISSUING BANK\n"
        )

        assert result.lc.bl_consignment == "TO_ORDER"

    def test_기명식은_consignee로_간다(self):
        result = parse_mt700(
            ":20:LC-1\n:46A:+FULL SET OF CLEAN ON BOARD BILL OF LADING CONSIGNED TO ABC TRADING CO., LTD\n"
        )

        assert result.lc.consignee == "ABC TRADING CO., LTD"
        assert result.lc.bl_consignment is None

    def test_BL_요구_항목이_없으면_아무것도_채우지_않는다(self):
        result = parse_mt700(":20:LC-1\n:46A:+SIGNED COMMERCIAL INVOICE IN TRIPLICATE\n")

        assert result.lc.bl_consignment is None
        assert result.lc.consignee is None


class Test통지처_추출:
    """46A B/L 요구 줄의 NOTIFY 절 — D010·D020 이 이 값을 쓴다."""

    def test_NOTIFY_뒤_줄_끝까지가_이름이다(self):
        result = parse_mt700(
            ":20:LC-1\n"
            ":46A:+FULL SET OF CLEAN ON BOARD OCEAN BILL OF LADING MADE OUT TO ORDER "
            "AND BLANK ENDORSED NOTIFY SCHENKER AG HAMBURG\n"
        )

        assert result.lc.notify_party == "SCHENKER AG HAMBURG"

    def test_NOTIFY_PARTY_콜론_표기도_받는다(self):
        result = parse_mt700(
            ":20:LC-1\n:46A:+FULL SET OF CLEAN ON BOARD B/L NOTIFY PARTY: ABC TRADING CO., LTD\n"
        )

        assert result.lc.notify_party == "ABC TRADING CO., LTD"

    def test_NOTIFY_ADDRESS_표기도_받는다(self):
        result = parse_mt700(
            ":20:LC-1\n:46A:+FULL SET OF CLEAN ON BOARD B/L NOTIFY ADDRESS SAME AS CONSIGNEE\n"
        )

        assert result.lc.notify_party == "SAME AS CONSIGNEE"

    def test_NOTIFY_가_없으면_None_이다(self):
        # D010 은 notify_party 가 None 이면 미검사로 빠진다 — 통지처를 지어
        # 내면 정상 서류에 없는 하자를 만든다.
        result = parse_mt700(
            ":20:LC-1\n:46A:+FULL SET OF CLEAN ON BOARD B/L MADE OUT TO ORDER\n"
        )

        assert result.lc.notify_party is None

    def test_NOTIFY_APPLICANT는_개설의뢰인_상호로_치환한다(self):
        # 50 이 46A 보다 먼저 오는 것이 SWIFT 표준 순서라 이미 읽혀 있다.
        # 원문 그대로 "APPLICANT" 를 넣으면 서류의 실제 개설의뢰인 상호와
        # 어긋나 D020 이 정상 서류를 매번 위반으로 잡는다.
        result = parse_mt700(
            ":20:LC-1\n"
            ":50:NORDWIND HANDELS GMBH\nKAISERSTRASSE 42\n"
            ":46A:+FULL SET OF CLEAN ON BOARD B/L MADE OUT TO ORDER NOTIFY APPLICANT\n"
        )

        assert result.lc.notify_party == "NORDWIND HANDELS GMBH"
        assert any("치환" in n for n in result.notes)

    def test_NOTIFY_APPLICANT인데_50을_못_읽으면_원문을_둔다(self):
        result = parse_mt700(
            ":20:LC-1\n:46A:+FULL SET OF CLEAN ON BOARD B/L MADE OUT TO ORDER NOTIFY APPLICANT\n"
        )

        assert result.lc.notify_party == "APPLICANT"
        assert any("APPLICANT" in n and "읽지 못해" in n for n in result.notes)


class Test47A_한도_추출:
    """47A 자유서식의 총중량·용적 한도 — D007·D007B 가 이 값을 쓴다."""

    def test_기본_표기를_읽는다(self):
        result = parse_mt700(
            ":20:LC-1\n"
            ":47A:+GROSS WEIGHT NOT TO EXCEED 13,000 KGS\n"
            "+MEASUREMENT NOT TO EXCEED 40 CBM\n"
        )

        assert result.lc.max_gross_weight_kg == pytest.approx(13000.0)
        assert result.lc.max_measurement_cbm == pytest.approx(40.0)

    def test_MAXIMUM_MAX_점_NOT_EXCEEDING_변형을_받는다(self):
        result = parse_mt700(
            ":20:LC-1\n"
            ":47A:+MAXIMUM GROSS WEIGHT: 13,000 KGS\n"
            "+MEASUREMENT NOT EXCEEDING 40 CBM\n"
        )

        assert result.lc.max_gross_weight_kg == pytest.approx(13000.0)
        assert result.lc.max_measurement_cbm == pytest.approx(40.0)

        result2 = parse_mt700(":20:LC-1\n:47A:+MAX. GROSS WEIGHT 13000 KGS\n")

        assert result2.lc.max_gross_weight_kg == pytest.approx(13000.0)

    def test_M_TON_단위는_KG로_환산한다(self):
        result = parse_mt700(":20:LC-1\n:47A:+GROSS WEIGHT NOT TO EXCEED 13 M.TON\n")

        assert result.lc.max_gross_weight_kg == pytest.approx(13000.0)

    def test_단위를_모르면_값을_넣지_않는다(self):
        # 잘못된 한도는 정상 서류를 하자로 만든다 — 단위를 확신할 수 없으면
        # 비워 두는 쪽이 안전하다.
        result = parse_mt700(":20:LC-1\n:47A:+GROSS WEIGHT NOT TO EXCEED 13,000 LBS\n")

        assert result.lc.max_gross_weight_kg is None
        assert any("47A" in n and "단위" in n for n in result.notes)

    def test_한도가_적혀_있지_않으면_None을_유지한다(self):
        result = parse_mt700(
            ":20:LC-1\n:47A:+ALL DOCUMENTS MUST BEAR OUR CREDIT NUMBER\n"
        )

        assert result.lc.max_gross_weight_kg is None
        assert result.lc.max_measurement_cbm is None

    def test_거래조건_추출과_공존한다(self):
        # 47A 안에서 Incoterms 코드(_h_incoterms)와 한도(_h_47a)를 동시에
        # 뽑아야 한다 — 둘 다 같은 태그 원문을 따로 읽는다.
        result = parse_mt700(
            ":20:LC-1\n"
            ":47A:+SHIPMENT ON CFR HAMBURG BASIS, INCOTERMS 2020\n"
            "+GROSS WEIGHT NOT TO EXCEED 13,000 KGS\n"
        )

        assert result.lc.incoterms == "CFR"
        assert result.lc.max_gross_weight_kg == pytest.approx(13000.0)


class Test룰엔진_연결:
    """파서의 값어치는 이 검증이 실제로 도는가에 있다."""

    def _bl(self, **overrides) -> BLFields:
        bl = BLFields(
            bl_no="HG290309",
            shipper="GAE WOON CO., LTD.",
            consignee="DHHJ FRANCHISING CO., LTD.",
            notify_party="TRY ENERGY CO., LTD.",
            vessel="MSC BIANCA",
            voyage_no="V.112",
            port_of_loading="BUSAN, KOREA",
            port_of_discharge="TOKYO, JAPAN",
            # 45A 를 그대로 옮긴 명세. D006 은 L/C 명세의 낱말이 서류에
            # 있는지를 보므로, 여기가 짧으면 파서가 아니라 픽스처 때문에
            # 위반이 난다.
            description_of_goods="SAW MACHINE FOB BUSAN INCOTERMS 2020",
            gross_weight="884 KG",
            measurement="349.64 CBM",
            date_of_issue="2026-06-01",
            place_of_issue="PUSAN",
            on_board_date="2026-06-01",
            total_freight="$1,741.56",
            no_of_original_bl="THREE (3)",
        )
        for name, value in overrides.items():
            setattr(bl, name, value)
        return bl

    def test_전문만으로_정상_서류가_통과한다(self):
        lc = parse_mt700(MESSAGE).lc

        verdict = RuleEngine().verify(self._bl(), lc, as_of=datetime(2026, 6, 10))

        assert not verdict.has_critical, [v.rule_id for v in verdict.violations]

    def test_전문의_선적기한을_넘기면_잡는다(self):
        # 44C 가 ISO 로 정규화되지 않으면 이 룰은 위반이 아니라 '해석 실패'로
        # 빠진다. 검출과 평가불가는 화면에서 둘 다 '위반 없음'으로 보인다.
        lc = parse_mt700(MESSAGE).lc

        verdict = RuleEngine().verify(
            self._bl(on_board_date="2026-07-15"), lc, as_of=datetime(2026, 7, 20)
        )

        assert "D002" in {v.rule_id for v in verdict.violations}

    def test_46A_목록으로_선하증권_요구를_확인한다(self):
        lc = parse_mt700(MESSAGE).lc

        verdict = RuleEngine().verify(self._bl(), lc, as_of=datetime(2026, 6, 10))

        assert "D016" not in {s.rule_id for s in verdict.skipped}

    def test_from_tags_와_같은_자리에_꽂힌다(self):
        # 기존 진입점과 결과가 갈리면 두 경로가 다른 시스템이 된다.
        parsed = parse_mt700(":20:LC-1\n:44E:BUSAN\n:44F:TOKYO\n").lc
        tagged = LCTerms.from_tags({"44E": "BUSAN", "44F": "TOKYO"}, lc_no="LC-1")

        assert parsed.lc_no == tagged.lc_no
        assert parsed.port_of_loading == tagged.port_of_loading
        assert parsed.port_of_discharge == tagged.port_of_discharge


class Testfrom_tags_도_같은_정규화를_탄다:
    """문이 둘인데 한쪽만 정규화하면, 그쪽으로 들어온 L/C 는 조용히 다르게 판정된다."""

    def test_46A_를_목록으로_만든다(self):
        # 회귀: 문자열로 두면 `bl_in_documents_required` 가 **문자 단위로**
        # 순회해 선하증권 요구를 못 찾고, 정상 L/C 에 D016 을 날조했다.
        lc = LCTerms.from_tags({"46A": "FULL SET OF CLEAN ON BOARD B/L"})

        assert lc.documents_required == ["FULL SET OF CLEAN ON BOARD B/L"]

    def test_46A_날조를_직접_잡는다(self):
        bl = BLFields(
            bl_no="HG290309",
            shipper="GAE WOON CO., LTD.",
            consignee="DHHJ FRANCHISING CO., LTD.",
            notify_party="TRY ENERGY CO., LTD.",
            vessel="MSC BIANCA",
            port_of_loading="BUSAN",
            port_of_discharge="TOKYO",
            description_of_goods="SAW MACHINE",
            gross_weight="884 KG",
            date_of_issue="2026-06-01",
            place_of_issue="PUSAN",
            on_board_date="2026-06-01",
        )
        lc = LCTerms.from_tags({"46A": "FULL SET OF CLEAN ON BOARD B/L"})

        verdict = RuleEngine().verify(bl, lc, as_of=datetime(2026, 6, 10))

        assert "D016" not in {v.rule_id for v in verdict.violations}

    def test_YYMMDD_를_읽는다(self):
        # 회귀: 원값을 그대로 두면 날짜 룰이 '해석 실패'로 빠지는데, 화면에서
        # 그것은 위반 없음과 구분되지 않는다.
        lc = LCTerms.from_tags({"44C": "260630", "31D": "261231SEOUL"})

        assert lc.latest_shipment_date == "2026-06-30"
        assert lc.expiry_date == "2026-12-31"

    def test_참조표의_모든_태그에_처리기가_있다(self):
        # `MT700_TAGS` 는 참조용이고 변환은 `_HANDLERS` 가 한다. 둘이 어긋나면
        # 표에만 있는 태그가 조용히 무시된다.
        from ruleEngine.mt700 import _HANDLERS
        from ruleEngine.types import MT700_TAGS

        assert not set(MT700_TAGS) - set(_HANDLERS)
