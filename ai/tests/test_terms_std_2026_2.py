"""std-2026.2 실카탈로그가 e-B/L 현행 표준 표기로 교정하는지 — 포장 단위(Rec 21)·
Incoterms 코드만·ISO 20275 상호 접미. 옛 판(std-2026.1)은 재현용으로 그대로 남는다."""

from __future__ import annotations

from f2_terms.cascade import DocumentInput, Normalizer
from f2_terms.glossary import GlossaryStack, available_versions, load_glossary


def _suggestions(fields, version="std-2026.2"):
    norm = Normalizer(stack=GlossaryStack([load_glossary(version)]))
    doc = DocumentInput(doc="선하증권", doc_id="T", fields=fields)
    return norm.normalize([doc]).suggestions


def test_두_버전이_모두_적재되고_새_판이_옛_판을_폐기한다():
    assert {"std-2026.1", "std-2026.2"} <= set(available_versions())
    assert load_glossary("std-2026.2").catalog_version == "std-2026.2"


def test_PCS는_Rec21_PP로_정렬된다():
    [s] = _suggestions({"quantity": "100 PCS"})
    assert s.to_be == "PP"
    assert s.evidence.authority == "UN/ECE Rec 21"


def test_CTN_authority는_Rec21이다():
    [s] = _suggestions({"quantity": "20 CTN"})
    assert s.to_be == "CT"
    assert s.evidence.authority == "UN/ECE Rec 21"


def test_FOB_BUSAN은_코드만_남긴다():
    [s] = [x for x in _suggestions({"incoterms": "FOB BUSAN"}) if x.term_class == "price_term"]
    assert s.to_be == "FOB"


def test_PTE_LTD는_Pte_Ltd로_정렬된다():
    [s] = _suggestions({"shipper": "ACME TRADING PTE LTD"})
    assert s.to_be == "Pte Ltd"


def test_PVT_LTD는_쉼표_없이_Pvt_Ltd로_정렬된다():
    # ISO 20275 인도 Private Limited Company 등록 약어 'Pvt. Ltd.' — 일반 규칙이면 'Pvt., Ltd.'
    [s] = _suggestions({"shipper": "ACME EXPORTS PVT LTD"})
    assert s.to_be == "Pvt. Ltd."


def test_옛_판은_재현용으로_PCE를_그대로_낸다():
    [s] = _suggestions({"quantity": "100 PCS"}, version="std-2026.1")
    assert s.to_be == "PCE"
