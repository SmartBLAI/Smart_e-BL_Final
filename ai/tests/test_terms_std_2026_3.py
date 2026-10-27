"""std-2026.3 제안 정책(practice-1) — 사용자에게 보이는 제안과 내부 비교용 정규화의 분리.

원칙: 서류 관행상 맞는 표기는 제안하지 않고, 오기·비표준·폐지·깨진 구두점·잘못된
체크디지트만 다룬다. 옛 판(std-2026.1/2)은 같은 입력에 옛 판정을 그대로 낸다(재현성).
"""

from __future__ import annotations

import pytest

from f2_terms.cascade import DocumentInput, Normalizer
from f2_terms.glossary import (
    SUGGESTION_POLICY_PRACTICE,
    Glossary,
    GlossaryCatalogError,
    GlossaryStack,
    available_versions,
    load_glossary,
)
from f2_terms.types import GlossaryTerm

NEW = "std-2026.3"


@pytest.fixture(scope="module")
def norms():
    return {
        v: Normalizer(stack=GlossaryStack([load_glossary(v)]))
        for v in ("std-2026.1", "std-2026.2", NEW)
    }


def run(norms, fields, version=NEW):
    doc = DocumentInput(doc="선하증권", doc_id="T", fields=fields)
    return norms[version].normalize([doc])


def pairs(norms, fields, version=NEW):
    return [(s.as_is, s.to_be) for s in run(norms, fields, version).suggestions]


# ── 카탈로그 · 버전 ─────────────────────────────────────────────


def test_세_버전이_적재되고_새_판이_기본이며_옛_판을_폐기한다():
    assert {"std-2026.1", "std-2026.2", NEW} <= set(available_versions())
    g = load_glossary()
    assert g.catalog_version == NEW and g.suggestion_policy == SUGGESTION_POLICY_PRACTICE
    assert load_glossary("std-2026.2").suggestion_policy == "legacy"


def test_단위_canonical은_EDI_코드로_남고_서류_표기는_bl_form이다():
    g = load_glossary(NEW)
    kgm = g.by_term_id("UOM.KGM")
    assert kgm.canonical == "KGM" and kgm.bl_form == "KGS"
    assert g.by_term_id("UOM.MTQ").canonical == "MTQ" and g.by_term_id("UOM.MTQ").bl_form == "CBM"
    assert "KGS" in kgm.practice_variants and "KGS" not in kgm.aliases


def test_옛_판은_같은_입력에_옛_판정을_낸다(norms):
    assert pairs(norms, {"gross_weight": "12 KGS"}, "std-2026.2") == [("KGS", "KGM")]
    assert pairs(norms, {"incoterms": "FOB BUSAN"}, "std-2026.2") == [("FOB BUSAN", "FOB")]
    assert pairs(norms, {"consignee": "NORDWIND GMBH"}, "std-2026.2") == [("GMBH", "GmbH")]


# ── 1) 단위 ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "field,value",
    [
        ("gross_weight", "12,480 KGS"),
        ("gross_weight", "12,480 KG"),
        ("gross_weight", "12 kgs"),
        ("gross_weight", "12,480 KGM"),
        ("gross_weight", "12 MT"),
        ("measurement", "38.5 CBM"),
        ("measurement", "38.5 M3"),
        ("measurement", "38.5 M³"),
        ("measurement", "38.5 MTQ"),
        ("quantity", "100 PCS"),
        ("quantity", "20 CTNS"),
        ("quantity", "20 CTN"),
        ("package_count", "5 PKGS"),
        ("quantity", "50 BAGS"),
    ],
)
def test_정상_관행_단위는_제안하지_않는다(norms, field, value):
    assert pairs(norms, {field: value}) == []


@pytest.mark.parametrize(
    "field,value,as_is,to_be",
    [
        ("gross_weight", "12 KILOS", "KILOS", "KGS"),
        ("gross_weight", "12 K.G.S", "K.G.S", "KGS"),
        ("gross_weight", "12 TONS", "TONS", "MT"),
        ("measurement", "5 CU.M", "CU.M", "CBM"),
        ("measurement", "5 C.B.M.", "C.B.M.", "CBM"),
        ("quantity", "20 카톤", "카톤", "CTNS"),
    ],
)
def test_비표준_단위는_EDI_코드가_아니라_관행_표기를_제안한다(norms, field, value, as_is, to_be):
    [s] = run(norms, {field: value}).suggestions
    assert (s.as_is, s.to_be) == (as_is, to_be)
    # 코드(KGM·MTQ)는 근거(authority)로만 남는다 — 서류에 박는 값이 아니다.
    assert s.evidence.authority.startswith("UN/ECE")
    assert "내부 비교용" in s.message
    # span 은 단위 토큰뿐이라 수치는 구조적으로 보존된다.
    assert s.field.span is not None


def test_모르는_단위는_추측하지_않고_안내만_한다(norms):
    r = run(norms, {"gross_weight": "12 FOO"})
    assert r.suggestions == [] and [n.kind for n in r.notices] == ["not_covered"]


# ── 2) Incoterms ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        "FOB",
        "FOB BUSAN",
        "fob busan",
        "CIP $3,111.09",
        "CIF HAMBURG USD 12,000",
        "FOB BUSAN INCOTERMS 2020",
        "EX WORKS",
    ],
)
def test_코드_뒤_장소와_금액은_정상_표기라_제안하지_않는다(norms, value):
    assert pairs(norms, {"incoterms": value}) == []


@pytest.mark.parametrize(
    "value,as_is",
    [("F.O.B", "F.O.B"), ("F O B BUSAN", "F O B"), ("F.O.B. BUSAN", "F.O.B."), ("c.i.f HAMBURG", "c.i.f")],
)
def test_깨진_코드_표기는_코드_토큰만_고치고_장소는_그대로_둔다(norms, value, as_is):
    [s] = run(norms, {"incoterms": value}).suggestions
    assert s.as_is == as_is and s.to_be in ("FOB", "CIF")
    start, end = s.field.span
    assert value[start:end] == as_is  # 뒤따르는 장소·금액은 span 밖


def test_한글_조건명은_코드로_제안한다(norms):
    assert pairs(norms, {"incoterms": "공장인도"}) == [("공장인도", "EXW")]


@pytest.mark.parametrize("value", ["DES HAMBURG", "DAT", "DEQ ROTTERDAM", "DDU SEOUL", "DAF"])
def test_폐지된_조건은_후속_후보를_보여_주되_사람이_고른다(norms, value):
    [s] = run(norms, {"incoterms": value}).suggestions
    assert s.requires_choice and s.to_be is None
    assert [c.to_be for c in s.candidates] == ["DAP", "DPU"]
    assert "폐지" in s.message


def test_알_수_없는_앞_토큰은_추측하지_않는다(norms):
    assert run(norms, {"incoterms": "XYZ BUSAN"}).suggestions == []


# ── 3) 상호 접미: 원문 대소문자 유지 ───────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        "HANKOOK PRECISION CO., LTD.",
        "HANKOOK PRECISION CO., LTD",
        "NORDWIND HANDELS GMBH",
        "ACME TRADING PTE LTD",
        "ACME TRADING PTE. LTD.",
        "ACME EXPORTS PVT LTD",
        "FOO TRADING INC",
        "FOO TRADING INC.",
        "FOO TRADING CORP",
        "FOO LTD",
        "FOO LIMITED",
        "Nordwind GmbH",
        "Foo Trading Pte Ltd",
        "Foo Trading Co., Ltd.",
    ],
)
def test_정상_접미는_제안하지_않는다(norms, value):
    assert pairs(norms, {"shipper": value}) == []


@pytest.mark.parametrize(
    "value,as_is,to_be",
    [
        ("HANKOOK PRECISION CO.,LTD", "CO.,LTD", "CO., LTD."),
        ("HANKOOK PRECISION CO LTD", "CO LTD", "CO., LTD."),
        ("ACME EXPORTS PVT.LTD", "PVT.LTD", "PVT. LTD."),
        ("ACME PTE.LTD", "PTE.LTD", "PTE LTD"),
    ],
)
def test_대문자_상호는_대문자를_유지하고_깨진_구두점만_고친다(norms, value, as_is, to_be):
    assert pairs(norms, {"shipper": value}) == [(as_is, to_be)]


@pytest.mark.parametrize(
    "value,as_is,to_be",
    [
        ("Hankook Precision Co.,Ltd", "Co.,Ltd", "Co., Ltd."),
        ("Hankook Precision CO., LTD.", "CO., LTD.", "Co., Ltd."),
        ("Nordwind Handels Gmbh", "Gmbh", "GmbH"),
        ("Acme Exports Pvt.Ltd", "Pvt.Ltd", "Pvt. Ltd."),
        ("Acme Trading Pte.Ltd", "Pte.Ltd", "Pte Ltd"),
    ],
)
def test_혼합_케이스_상호는_옛_동작_그대로_표준_표기로_맞춘다(norms, value, as_is, to_be):
    assert pairs(norms, {"shipper": value}) == [(as_is, to_be)]


# ── 4) 컨테이너 · HS ────────────────────────────────────────────


def test_체크디지트가_맞는_컨테이너는_표기와_무관하게_정상이다(norms):
    assert pairs(norms, {"description_of_goods": "MSKU 123456 5"}) == []
    assert pairs(norms, {"description_of_goods": "msku1234565"}) == []


def test_체크디지트가_틀린_컨테이너는_제안_없이_경고한다(norms):
    r = run(norms, {"description_of_goods": "MSCU1234567"})
    assert r.suggestions == [] and "deterministic_error" in [n.kind for n in r.notices]


def test_형식이_맞는_HS는_제안하지_않고_자릿수_안내만_한다(norms):
    r = run(norms, {"description_of_goods": "HS 847130 PARTS"})
    assert r.suggestions == [] and "not_covered" in [n.kind for n in r.notices]


# ── 5) 관행 문구 · 운송서류 · 항구 ───────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "SHIPPED ONBOARD FREIGHT PREPAID",
        "Freight Prepaid",
        "SURRENDERED B/L",
        "SLAC",
        "FREIGHT PREPAID MULTIMODAL",
    ],
)
def test_정상_관행_문구와_약어_대소문자는_제안하지_않는다(norms, text):
    assert run(norms, {"description_of_goods": text}).suggestions == []


def test_오기_문구는_계속_제안한다(norms):
    assert pairs(norms, {"description_of_goods": "CARGO ONDECK"}) == [("ONDECK", "ON DECK")]


def test_항구_대소문자_변형은_제안하지_않고_구표기_깨진_코드는_제안한다(norms):
    assert pairs(norms, {"port_of_loading": "Busan"}) == []
    assert pairs(norms, {"port_of_loading": "PUSAN"}) == [("PUSAN", "BUSAN")]
    assert pairs(norms, {"port_of_loading": "KR PUS"}) == [("KR PUS", "BUSAN")]


# ── 6) 샘플 시나리오 ────────────────────────────────────────────


def test_결함_샘플_B_L_값은_제안이_없다(norms):
    fields = {
        "shipper": "HANKOOK PRECISION CO.,LTD",
        "consignee": "NORDWIND HANDELS GMBH",
        "gross_weight": "12,480 KGS",
        "measurement": "38.5 CBM",
        "incoterms": "FOB BUSAN",
        "port_of_loading": "BUSAN",
    }
    assert pairs(norms, fields) == [("CO.,LTD", "CO., LTD.")]


# ── 7) 내부 비교용 canonical 은 남는다 ───────────────────────────


def test_정상_표기도_사전으로_canonical_코드를_알아낼_수_있다():
    stack = GlossaryStack([load_glossary(NEW)])
    for text, cls, code in [("KGS", "qty_unit", "KGM"), ("CBM", "volume_unit", "MTQ"), ("M3", "volume_unit", "MTQ"), ("PCS", "qty_unit", "PP")]:
        [hit] = stack.lookup(text, cls)
        assert hit.term.canonical == code


# ── 8) 로더 검증 ────────────────────────────────────────────────


def _t(tid, canonical, **kw):
    return GlossaryTerm(term_id=tid, category="qty_unit", canonical=canonical, **kw)


def test_관행_표기가_별칭과_겹치면_카탈로그를_거부한다():
    with pytest.raises(GlossaryCatalogError, match="관행 표기"):
        Glossary([_t("U.A", "KGM", aliases=["KG"], practice_variants=["KG"])], "x", "2026-01-01")


def test_관행_표기는_canonical과_같아도_된다_그리고_조회에_색인된다():
    g = Glossary([_t("U.A", "KGM", practice_variants=["KGM", "KGS"])], "x", "2026-01-01")
    assert [t.term_id for t in g.by_alias_key("KGS", "qty_unit")] == ["U.A"]


def test_successors가_없는_term_id를_가리키면_거부한다():
    with pytest.raises(GlossaryCatalogError, match="successors"):
        Glossary([_t("U.A", "KGM", successors=["U.NOPE"])], "x", "2026-01-01")


def test_다른_항목의_관행_표기와_키가_충돌하면_거부한다():
    with pytest.raises(GlossaryCatalogError, match="키 충돌"):
        Glossary(
            [_t("U.A", "KGM", practice_variants=["KGS"]), _t("U.B", "LBR", aliases=["KGS"])],
            "x",
            "2026-01-01",
        )
