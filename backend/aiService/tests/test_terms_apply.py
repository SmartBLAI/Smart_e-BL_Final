"""F2 제안 적용 테스트 — `suggestion_id` 재현성·변조 대조·accept/reject·
span 치환.

`docs/f2/HANDOFF.md` §4.5(span 계약)·§4.7(`suggestion_id`) 의 계약을 고정한다.
span 계약이 한 번 깨져 단위 값이 복제된 채 승인 화면까지 갈 뻔한 사고가
있었다는 것이 이 파일에서 가장 무겁게 다루는 사실이다.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from datetime import datetime

import pytest

from terms.apply import (
    apply_suggestions,
    reject_suggestions,
    suggestion_id,
    verify_suggestion_id,
)
from terms.cascade import DocumentInput
from terms.glossary import load_glossary
from terms.keys import normalize_key
from terms.types import Correction, Evidence, FieldRef, Suggestion
from terms.validators import party_suffix, split_quantity, unit_code

# 시각은 주입한다 — accept/reject 는 순수 함수라는 확정 결정(HANDOFF §2)이다.
AS_OF = datetime(2026, 5, 25, 9, 30)


def make_suggestion(
    *,
    doc: str = "선하증권",
    field: str = "gross_weight",
    doc_id: str = "D1",
    span=None,
    as_is: str = "KGS",
    to_be: str = "KGM",
    term_class: str = "qty_unit",
    glossary_version: str = "std-2026.1",
    stage: str = "alias",
    term_id: str = "UOM.KGM",
    confidence: float = 0.95,
    impact=None,
    requires_choice: bool = False,
) -> Suggestion:
    """유효한(=재파생 대조를 통과하는) `Suggestion` 을 만든다.

    `suggestion_id` 를 자리표시자로 먼저 채운 뒤 실제 파생값으로 덮어쓴다
    — `suggestion_id()` 가 `Suggestion` 객체 전체를 재료로 삼기 때문에
    먼저 완전한 객체가 있어야 한다.
    """
    s = Suggestion(
        suggestion_id="placeholder",
        field=FieldRef(doc=doc, field=field, doc_id=doc_id, span=span),
        as_is=as_is,
        to_be=None if requires_choice else to_be,
        term_class=term_class,
        evidence=Evidence(
            authority="TEST",
            term_id=term_id,
            glossary_version=glossary_version,
            tier="standard",
            stage=stage,
            verified=False,
        ),
        confidence=confidence,
        impact=list(impact or []),
        requires_choice=requires_choice,
    )
    s.suggestion_id = suggestion_id(s)
    return s


# ════════════════════════════════════════════════════════════════
# suggestion_id — 재현성·변조 대조
# ════════════════════════════════════════════════════════════════


class TestSuggestionId:
    def test_같은_입력에는_같은_id를_낸다(self):
        s1 = make_suggestion()
        s2 = make_suggestion()

        assert suggestion_id(s1) == suggestion_id(s2)

    def test_사전_버전이_다르면_id가_다르다(self):
        s1 = make_suggestion(glossary_version="std-2026.1")
        s2 = make_suggestion(glossary_version="std-2026.2")

        assert suggestion_id(s1) != suggestion_id(s2)

    def test_span이_다르면_id가_다르다(self):
        s1 = make_suggestion(span=(0, 3))
        s2 = make_suggestion(span=(1, 4))

        assert suggestion_id(s1) != suggestion_id(s2)

    def test_impact는_id에_영향을_주지_않는다(self):
        # 요청에 실린 서류 수에 따라 impact 가 달라질 수 있으므로 해시
        # 재료에서 제외된다(HANDOFF §4.7).
        s1 = make_suggestion(impact=[])
        s2 = make_suggestion(impact=[FieldRef(doc="상업송장", field="net_weight")])

        assert suggestion_id(s1) == suggestion_id(s2)

    def test_as_is의_표기_차이는_같은_id로_접힌다(self):
        # normalize_key 를 거치므로 공백·대소문자 차이는 "같은 오류"로 본다.
        s1 = make_suggestion(as_is="kgs")
        s2 = make_suggestion(as_is=" KGS ")

        assert suggestion_id(s1) == suggestion_id(s2)

    def test_유효한_제안은_verify를_통과한다(self):
        s = make_suggestion()

        assert verify_suggestion_id(s) is True

    def test_변조된_id는_verify가_거짓을_낸다(self):
        s = make_suggestion()
        s.suggestion_id = "sg1_0000000000000000000"

        assert verify_suggestion_id(s) is False


# ════════════════════════════════════════════════════════════════
# apply_suggestions — 변조 대조·requires_choice·오래된 제안
# ════════════════════════════════════════════════════════════════


class TestApply기본동작:
    def test_변조된_제안은_unapplied가_된다(self):
        doc = DocumentInput(doc="선하증권", fields={"gross_weight": "884.00 KGS"}, doc_id="D1")
        s = make_suggestion(span=(7, 10), as_is="KGS", to_be="KGM")
        s.suggestion_id = "sg1_tampered0000000000"

        outcome = apply_suggestions(
            [doc], [s], scope="field", decided_by="reviewer", decided_at=AS_OF
        )

        assert outcome.corrections == []
        assert len(outcome.unapplied) == 1
        assert "변조" in outcome.unapplied[0]["reason"]

    def test_requires_choice_제안은_scope_field에서도_적용되지_않는다(self):
        doc = DocumentInput(doc="선하증권", fields={"port_of_loading": "PORTLAND"}, doc_id="D1")
        s = make_suggestion(
            field="port_of_loading", as_is="PORTLAND", to_be=None,
            requires_choice=True, term_class="port",
        )

        outcome = apply_suggestions(
            [doc], [s], scope="field", decided_by="reviewer", decided_at=AS_OF
        )

        assert outcome.corrections == []
        assert doc.fields["port_of_loading"] == "PORTLAND"  # 원본 미변경(복사본 대상)
        assert outcome.documents[0].fields["port_of_loading"] == "PORTLAND"

    def test_requires_choice_제안은_scope_all에서도_적용되지_않는다(self):
        # "임의 선택 금지" 가 일괄 적용에서도 뚫리면 안 된다(HANDOFF §4.5).
        doc = DocumentInput(doc="선하증권", fields={"port_of_loading": "PORTLAND"}, doc_id="D1")
        s = make_suggestion(
            field="port_of_loading", as_is="PORTLAND", to_be=None,
            requires_choice=True, term_class="port",
        )

        outcome = apply_suggestions(
            [doc], [s], scope="all", decided_by="reviewer", decided_at=AS_OF
        )

        assert outcome.corrections == []
        assert outcome.unapplied[0]["reason"] == "사용자 선택이 필요한 제안입니다"

    def test_오래된_제안은_unapplied가_된다(self):
        # 사람이 S3 에서 값을 이미 고친 뒤 오래된 제안을 승인한 경우 —
        # as_is 가 더 이상 문서 값과 일치하지 않는다.
        doc = DocumentInput(
            doc="선하증권", fields={"gross_weight": "884.00 KGM"}, doc_id="D1"  # 이미 KGM
        )
        s = make_suggestion(span=(7, 10), as_is="KGS", to_be="KGM")

        outcome = apply_suggestions(
            [doc], [s], scope="field", decided_by="reviewer", decided_at=AS_OF
        )

        assert outcome.corrections == []
        assert len(outcome.unapplied) == 1
        assert "일치하지" in outcome.unapplied[0]["reason"]

    def test_문서를_못_찾으면_unapplied가_된다(self):
        doc = DocumentInput(doc="선하증권", fields={"gross_weight": "884.00 KGS"}, doc_id="D1")
        s = make_suggestion(doc_id="다른-문서", span=(7, 10))

        outcome = apply_suggestions(
            [doc], [s], scope="field", decided_by="reviewer", decided_at=AS_OF
        )

        assert outcome.corrections == []
        assert len(outcome.unapplied) == 1

    def test_필드값이_None이면_unapplied가_된다(self):
        doc = DocumentInput(doc="선하증권", fields={"gross_weight": None}, doc_id="D1")
        s = make_suggestion(span=(7, 10))

        outcome = apply_suggestions(
            [doc], [s], scope="field", decided_by="reviewer", decided_at=AS_OF
        )

        assert outcome.corrections == []
        assert len(outcome.unapplied) == 1

    def test_알_수_없는_scope는_예외를_낸다(self):
        doc = DocumentInput(doc="선하증권", fields={"gross_weight": "884.00 KGS"}, doc_id="D1")
        s = make_suggestion(span=(7, 10))

        with pytest.raises(ValueError, match="scope"):
            apply_suggestions([doc], [s], scope="일부", decided_by="r", decided_at=AS_OF)


# ════════════════════════════════════════════════════════════════
# 필수 — 수치·바이트 보존, span 계약 불변식
# ════════════════════════════════════════════════════════════════


class Test필수_보존_계약:
    def test_적용하면_수치가_보존된다(self):
        """`'1,234.50 KGS'` → `'1,234.50 KGM'` — 수치 부분은 복제되지도
        사라지지도 않는다. span 계약이 한 번 깨져 `'1,234.50 1,234.50 KGM'`
        처럼 수치가 복제된 채 승인 화면까지 갈 뻔한 사고를 재현·고정한다
        (HANDOFF §4.5)."""
        text = "1,234.50 KGS"
        number, unit, span = split_quantity(text)
        assert unit_code(unit).code == "KGM"

        doc = DocumentInput(doc="선하증권", fields={"gross_weight": text}, doc_id="D1")
        s = make_suggestion(span=span, as_is=unit, to_be="KGM")

        outcome = apply_suggestions(
            [doc], [s], scope="field", decided_by="reviewer", decided_at=AS_OF
        )

        result = outcome.documents[0].fields["gross_weight"]
        assert result == "1,234.50 KGM"
        assert result.count("1,234.50") == 1  # 복제 없음

    def test_상호_본체는_바이트가_보존된다(self):
        text = "GAE WOON CO.,LTD"
        check = party_suffix(text)
        assert check.matched

        doc = DocumentInput(doc="선하증권", fields={"shipper": text}, doc_id="D1")
        s = make_suggestion(
            field="shipper", span=check.span, as_is=check.as_is, to_be=check.to_be,
            term_class="party_suffix",
        )

        outcome = apply_suggestions(
            [doc], [s], scope="field", decided_by="reviewer", decided_at=AS_OF
        )

        result = outcome.documents[0].fields["shipper"]
        assert result == "GAE WOON Co., Ltd."
        # 본체 바이트가 정확히 그대로 옮겨졌는지 — span 앞부분과 원문의
        # 같은 구간을 바이트 단위로 대조한다.
        body_len = check.span[0]
        assert result[:body_len].encode("utf-8") == text[:body_len].encode("utf-8")

    def test_span_계약_불변식_전_제안_루프(self):
        """`span` 이 있는 모든 제안에 대해 `value[start:end] == as_is` 를
        확인한다. 실제 카탈로그로 여러 클래스(qty_unit·volume_unit·
        party_suffix)를 정규화해 만든 제안 전부를 도는 루프로 고정한다 —
        한 클래스만 봐서는 이 계약이 우연히 지켜진 것인지 구조적으로
        지켜진 것인지 구분할 수 없다."""
        g = load_glossary()

        def catalog_to_be(term_class: str, alias: str) -> str:
            key = normalize_key(alias)
            hits = g.by_alias_key(key, term_class) or g.by_canonical_key(key, term_class)
            assert hits, f"실제 카탈로그에 '{alias}'({term_class}) 항목이 없습니다"
            return hits[0].canonical

        weight_text = "884.00 KGS"
        w_number, w_unit, w_span = split_quantity(weight_text)
        measurement_text = "349.64 CBM"
        m_number, m_unit, m_span = split_quantity(measurement_text)
        shipper_text = "GAE WOON CO.,LTD"
        suffix_check = party_suffix(shipper_text)

        suggestions = [
            make_suggestion(
                field="gross_weight", span=w_span, as_is=w_unit,
                to_be=catalog_to_be("qty_unit", w_unit), term_class="qty_unit",
            ),
            make_suggestion(
                field="measurement", span=m_span, as_is=m_unit,
                to_be=catalog_to_be("volume_unit", m_unit), term_class="volume_unit",
            ),
            make_suggestion(
                field="shipper", span=suffix_check.span, as_is=suffix_check.as_is,
                to_be=suffix_check.to_be, term_class="party_suffix",
            ),
        ]
        values = {
            "gross_weight": weight_text,
            "measurement": measurement_text,
            "shipper": shipper_text,
        }

        # 계약 검증 — apply 하기 전에도 "제안이 가리키는 자리가 실제로
        # as_is 인가" 가 성립해야 한다.
        for s in suggestions:
            if s.field.span is not None:
                start, end = s.field.span
                value = values[s.field.field]
                assert value[start:end] == s.as_is

        doc = DocumentInput(doc="선하증권", fields=dict(values), doc_id="D1")
        outcome = apply_suggestions(
            [doc], suggestions, scope="field", decided_by="reviewer", decided_at=AS_OF
        )

        assert len(outcome.corrections) == 3
        assert outcome.documents[0].fields["gross_weight"] == "884.00 KGM"
        assert outcome.documents[0].fields["measurement"] == "349.64 MTQ"
        assert outcome.documents[0].fields["shipper"] == "GAE WOON Co., Ltd."


# ════════════════════════════════════════════════════════════════
# 같은 필드 여러 span — 오프셋 어긋남·겹침·전체 대 부분
# ════════════════════════════════════════════════════════════════


class Test같은필드_여러span:
    def test_여러_span_제안이_오프셋_어긋남_없이_적용된다(self):
        # to_be 길이가 as_is 와 다른 두 span 이 한 필드 안에 있을 때, 앞쪽을
        # 먼저 치환하면 뒤쪽 좌표가 밀린다 — 뒤에서부터 처리해야 한다.
        text = "27 PKG CELL ASSEMBLY, FREIGHT PREPAID"
        # "PKG" span
        pkg_start = text.index("PKG")
        pkg_span = (pkg_start, pkg_start + 3)
        # "FREIGHT PREPAID" span (뒤쪽, 더 긴 치환)
        fp_start = text.index("FREIGHT PREPAID")
        fp_span = (fp_start, fp_start + len("FREIGHT PREPAID"))

        doc = DocumentInput(doc="선하증권", fields={"description_of_goods": text}, doc_id="D1")
        s1 = make_suggestion(
            field="description_of_goods", span=pkg_span, as_is="PKG",
            to_be="Package(s)", term_class="qty_unit",
        )
        s2 = make_suggestion(
            field="description_of_goods", span=fp_span, as_is="FREIGHT PREPAID",
            to_be="Freight Prepaid (운임 선불)", term_class="delivery",
        )

        outcome = apply_suggestions(
            [doc], [s1, s2], scope="field", decided_by="reviewer", decided_at=AS_OF
        )

        result = outcome.documents[0].fields["description_of_goods"]
        assert result == "27 Package(s) CELL ASSEMBLY, Freight Prepaid (운임 선불)"
        assert len(outcome.corrections) == 2

    def test_span이_겹치면_하나만_적용된다(self):
        """겹치는 두 span 을 동시에 승인해도 치환이 서로를 덮어쓰지 않는다
        — 정확히 하나만 적용되고 나머지는 겹침 사유로 보류된다. 어느
        쪽이 이기는지는 별도 테스트(`test_겹침_해소는_원본_리스트_순서를_따른다`)
        가 다룬다."""
        text = "MSKU1234565"
        s1 = make_suggestion(
            field="marks", span=(0, 4), as_is="MSKU", to_be="MSCU", term_class="container_no",
        )
        s2 = make_suggestion(
            field="marks", span=(2, 6), as_is="KU12", to_be="XXXX", term_class="container_no",
        )
        doc = DocumentInput(doc="선하증권", fields={"marks": text}, doc_id="D1")

        outcome = apply_suggestions(
            [doc], [s1, s2], scope="field", decided_by="reviewer", decided_at=AS_OF
        )

        applied_ids = {c.suggestion_id for c in outcome.corrections}
        unapplied_ids = {u["suggestion_id"] for u in outcome.unapplied}
        assert len(outcome.corrections) == 1
        assert applied_ids | unapplied_ids == {s1.suggestion_id, s2.suggestion_id}
        assert applied_ids.isdisjoint(unapplied_ids)
        loser_id = (unapplied_ids - applied_ids).pop()
        loser_reason = next(u["reason"] for u in outcome.unapplied if u["suggestion_id"] == loser_id)
        assert "겹칩" in loser_reason

    def test_겹침_해소는_원본_리스트_순서를_따른다(self):
        """`apply.py::_apply_group` 자신의 docstring 이 약속하는 계약을
        고정한다: "두 제안의 span 이 겹치면 ... 그룹에 들어온 순서(= 원본
        `suggestions` 리스트 순서) 기준으로 먼저 온 것을 남기고 뒤엣것을
        unapplied 로 돌린다."

        여기서 s1(span=(0,4))을 리스트의 **첫** 자리에, s2(span=(2,6),
        s1 과 겹치지만 시작 위치가 더 뒤)를 **두 번째** 자리에 둔다.
        문서대로라면 리스트 순서상 먼저인 s1 이 남아야 한다.

        **발견**: 실제 구현(`_apply_group`)은 겹침 대상을
        `sorted(..., key=lambda pair: (-pair[1].ref.span[0], pair[0]))` 로
        정렬해 처리한다 — 1순위 정렬 키가 리스트 인덱스(`pair[0]`)가
        아니라 **span 시작 위치의 내림차순**(`-start`)이다. 이 정렬은
        span 오프셋이 서로 밀리지 않도록 "문자열 뒤에서부터 치환"하려는
        목적이지만, 시작 위치가 다른 겹침에서는 그 정렬이 곧 승자도
        정해버린다 — 이 예시에서는 start=2 인 s2 가 start=0 인 s1 보다
        먼저 정렬되어 **s2 가 이긴다.** 이 테스트는 docstring 이 약속한
        대로(s1 이 이겨야 한다) 작성돼 있으므로, 실패한다면 docstring 과
        구현이 시작 위치가 다른 겹침에서 어긋난다는 뜻이다 — 소스를 고쳐
        통과시키지 않는다(작업 지시 "카탈로그·소스 수정 금지").
        """
        text = "MSKU1234565"
        s1 = make_suggestion(
            field="marks", span=(0, 4), as_is="MSKU", to_be="MSCU", term_class="container_no",
        )
        s2 = make_suggestion(
            field="marks", span=(2, 6), as_is="KU12", to_be="XXXX", term_class="container_no",
        )
        doc = DocumentInput(doc="선하증권", fields={"marks": text}, doc_id="D1")

        outcome = apply_suggestions(
            [doc], [s1, s2], scope="field", decided_by="reviewer", decided_at=AS_OF
        )

        assert outcome.corrections[0].suggestion_id == s1.suggestion_id

    def test_span_None과_span이_공존하면_span_쪽이_보류된다(self):
        # 전체 치환이 확정되면 그 안의 부분 span 좌표는 무효가 될 수
        # 있다 — span 있는 대상은 전부 포기하고 span=None 만 처리한다.
        text = "SHANGHAI, CHINA"
        whole = make_suggestion(
            field="port_of_loading", span=None, as_is=text, to_be="Shanghai (CNSHA)",
            term_class="port",
        )
        partial = make_suggestion(
            field="port_of_loading", span=(0, 8), as_is="SHANGHAI", to_be="Shanghai",
            term_class="port",
        )
        doc = DocumentInput(doc="선하증권", fields={"port_of_loading": text}, doc_id="D1")

        outcome = apply_suggestions(
            [doc], [whole, partial], scope="field", decided_by="reviewer", decided_at=AS_OF
        )

        assert outcome.documents[0].fields["port_of_loading"] == "Shanghai (CNSHA)"
        assert len(outcome.corrections) == 1
        assert outcome.corrections[0].suggestion_id == whole.suggestion_id
        partial_unapplied = [
            u for u in outcome.unapplied if u["suggestion_id"] == partial.suggestion_id
        ]
        assert len(partial_unapplied) == 1


# ════════════════════════════════════════════════════════════════
# scope · impact · 불변성
# ════════════════════════════════════════════════════════════════


class TestScope와Impact:
    def test_scope_field는_impact_자리를_건드리지_않는다(self):
        doc1 = DocumentInput(doc="선하증권", fields={"gross_weight": "884.00 KGS"}, doc_id="D1")
        doc2 = DocumentInput(doc="포장명세서", fields={"gross_weight": "884.00 KGS"}, doc_id="D2")
        impact_ref = FieldRef(doc="포장명세서", field="gross_weight", doc_id="D2", span=(7, 10))
        s = make_suggestion(span=(7, 10), impact=[impact_ref])

        outcome = apply_suggestions(
            [doc1, doc2], [s], scope="field", decided_by="reviewer", decided_at=AS_OF
        )

        by_doc = {d.doc_id: d for d in outcome.documents}
        assert by_doc["D1"].fields["gross_weight"] == "884.00 KGM"
        assert by_doc["D2"].fields["gross_weight"] == "884.00 KGS"  # 미변경

    def test_scope_all은_impact_자리도_적용한다(self):
        doc1 = DocumentInput(doc="선하증권", fields={"gross_weight": "884.00 KGS"}, doc_id="D1")
        doc2 = DocumentInput(doc="포장명세서", fields={"gross_weight": "884.00 KGS"}, doc_id="D2")
        impact_ref = FieldRef(doc="포장명세서", field="gross_weight", doc_id="D2", span=(7, 10))
        s = make_suggestion(span=(7, 10), impact=[impact_ref])

        outcome = apply_suggestions(
            [doc1, doc2], [s], scope="all", decided_by="reviewer", decided_at=AS_OF
        )

        by_doc = {d.doc_id: d for d in outcome.documents}
        assert by_doc["D1"].fields["gross_weight"] == "884.00 KGM"
        assert by_doc["D2"].fields["gross_weight"] == "884.00 KGM"
        assert outcome.corrections[0].impact == [impact_ref]

    def test_impact_적용_실패해도_주_결정은_기록된다(self):
        # 주 필드가 성공했으면 impact 자리 일부가 실패해도 Correction 은
        # 만든다 — 하나를 위해 다른 하나를 감추지 않는다.
        doc1 = DocumentInput(doc="선하증권", fields={"gross_weight": "884.00 KGS"}, doc_id="D1")
        doc2 = DocumentInput(
            doc="포장명세서", fields={"gross_weight": "이미_바뀐_값"}, doc_id="D2"  # as_is 불일치
        )
        impact_ref = FieldRef(doc="포장명세서", field="gross_weight", doc_id="D2", span=(7, 10))
        s = make_suggestion(span=(7, 10), impact=[impact_ref])

        outcome = apply_suggestions(
            [doc1, doc2], [s], scope="all", decided_by="reviewer", decided_at=AS_OF
        )

        assert len(outcome.corrections) == 1
        assert outcome.corrections[0].impact == []  # 실제로 바뀐 자리만
        assert any(u["suggestion_id"] == s.suggestion_id for u in outcome.unapplied)

    def test_입력_documents는_변경되지_않는다(self):
        original_value = "884.00 KGS"
        doc = DocumentInput(doc="선하증권", fields={"gross_weight": original_value}, doc_id="D1")
        s = make_suggestion(span=(7, 10))

        apply_suggestions([doc], [s], scope="field", decided_by="reviewer", decided_at=AS_OF)

        assert doc.fields["gross_weight"] == original_value


# ════════════════════════════════════════════════════════════════
# Correction — 기획안 §5.8 6필드
# ════════════════════════════════════════════════════════════════


class TestCorrection:
    def test_Correction은_기획안_6필드를_모두_갖는다(self):
        """기획안 §5.8: 변경 필드, 이전 값, 새 값, 영향 항목, 승인자, 시각."""
        field_names = {f.name for f in dataclass_fields(Correction)}

        assert {"field", "as_is", "to_be", "impact", "decided_by", "decided_at"} <= field_names

    def test_승인시_Correction의_결정은_accepted다(self):
        doc = DocumentInput(doc="선하증권", fields={"gross_weight": "884.00 KGS"}, doc_id="D1")
        s = make_suggestion(span=(7, 10))

        outcome = apply_suggestions(
            [doc], [s], scope="field", decided_by="검수자-1", decided_at=AS_OF
        )

        correction = outcome.corrections[0]
        assert correction.decision == "accepted"
        assert correction.decided_by == "검수자-1"
        assert correction.as_is == "KGS"
        assert correction.to_be == "KGM"

    def test_decided_at은_주입한_값_그대로다(self):
        # `datetime.now()` 를 부르지 않는다 — 같은 거절을 재현했을 때
        # 시각이 달라지면 순수성이 깨진다.
        doc = DocumentInput(doc="선하증권", fields={"gross_weight": "884.00 KGS"}, doc_id="D1")
        s = make_suggestion(span=(7, 10))

        outcome = apply_suggestions(
            [doc], [s], scope="field", decided_by="r", decided_at=AS_OF
        )

        assert outcome.corrections[0].decided_at == AS_OF

    def test_reject_suggestions는_서류를_건드리지_않는다(self):
        s = make_suggestion(span=(7, 10))

        corrections = reject_suggestions(
            [s], reason="false_positive", note="", decided_by="검수자-1", decided_at=AS_OF
        )

        assert len(corrections) == 1
        c = corrections[0]
        assert c.decision == "rejected"
        assert c.decided_by == "검수자-1"
        assert c.decided_at == AS_OF
        assert c.reason == "false_positive"
        assert c.impact == []  # 거절은 아무것도 바꾸지 않는다
