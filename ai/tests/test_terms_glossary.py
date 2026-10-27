"""F2 용어사전 테스트 — 카탈로그 로드·전수 검증·키 충돌·3계층 오버라이드.

`f3_rules/engine.py` 를 검증하는 `test_rule_engine.py::TestCatalog` 를
원형으로 삼는다: 로더는 문제를 전부 모아 한 번에 던지는지, 주입 seam
(`Glossary(terms=[...])`)이 파일과 같은 불변식을 지키는지, 실제 카탈로그를
쓰는 테스트는 건수·내용에 의존하지 않는지를 지킨다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from f2_terms import policy
from f2_terms.glossary import (
    Glossary,
    GlossaryCatalogError,
    GlossaryStack,
    available_versions,
    build_override,
    load_glossary,
)
from f2_terms.keys import normalize_key
from f2_terms.types import GlossaryTerm


def make_term(
    term_id: str,
    category: str,
    canonical: str,
    *,
    aliases=None,
    country=None,
    verified: bool = False,
    deprecated_by=None,
) -> GlossaryTerm:
    """테스트용 최소 `GlossaryTerm`. 주입 seam 은 raw dict 의 필수 키
    (lang/authority/version/effective_date)를 요구하지 않는다 — 그 검사는
    `_raw_entry_problems` 층이고 `Glossary.__init__` 은 타지 않는다."""
    return GlossaryTerm(
        term_id=term_id,
        category=category,
        canonical=canonical,
        aliases=list(aliases or []),
        country=country,
        verified=verified,
        deprecated_by=deprecated_by,
    )


def _raw_term(
    term_id: str,
    category: str,
    canonical: str,
    *,
    version: str,
    effective_date: str = "2026-01-01",
    aliases=None,
    country=None,
    lang: str = "en",
    authority: str = "TEST",
) -> dict:
    """오버라이드/카탈로그 파일 검증(1층)까지 통과하는 완전한 raw 항목."""
    d = {
        "term_id": term_id,
        "category": category,
        "canonical": canonical,
        "lang": lang,
        "authority": authority,
        "version": version,
        "effective_date": effective_date,
        "aliases": list(aliases or []),
    }
    if country is not None:
        d["country"] = country
    return d


# `policy.CLASSES` 중 사전이 필요한 클래스 전체. 하드코딩하지 않는 이유는
# 이 목록이 정책이 아니라 파생값이어야 하기 때문이다 — `policy.py` 에 클래스가
# 느는 순간에도(카탈로그 스키마 정합성 검사가 아니라 이 헬퍼가) 자동으로
# 따라간다.
NEEDS_GLOSSARY_CLASSES = sorted(k for k, c in policy.CLASSES.items() if c.needs_glossary)


def _write_synthetic_catalog(base: Path, version: str, effective_date: str) -> None:
    """`load_glossary` 가 요구하는 최소 완전 카탈로그(모든 needs_glossary
    클래스 1건씩) 를 `base/version/` 아래에 만든다. 버전 선택·상호 검증
    테스트가 실제 std-2026.1 을 건드리지 않고 파일 기반 로직만 검증하려고
    쓴다."""
    d = base / version
    d.mkdir(parents=True)

    manifest = {
        "version": 1,
        "catalog_version": version,
        "effective_date": effective_date,
        "deprecates": [],
        "files": ["glossary.yaml", "locode.yaml"],
    }
    (d / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    glossary_terms = [
        _raw_term(f"T-{cat}-{i}", cat, f"CANON{i}", version=version,
                  effective_date=effective_date, aliases=[f"ALIAS{i}"])
        for i, cat in enumerate(NEEDS_GLOSSARY_CLASSES)
        if cat != "port"
    ]
    (d / "glossary.yaml").write_text(
        yaml.safe_dump({"catalog_version": version, "terms": glossary_terms}),
        encoding="utf-8",
    )

    locode_terms = [
        _raw_term("PORT-1", "port", "TESTPORT", version=version,
                  effective_date=effective_date, country="KR", aliases=["TP"]),
    ]
    (d / "locode.yaml").write_text(
        yaml.safe_dump({"catalog_version": version, "terms": locode_terms}),
        encoding="utf-8",
    )


# ════════════════════════════════════════════════════════════════
# 로드
# ════════════════════════════════════════════════════════════════


class Test카탈로그로드:
    def test_표준_카탈로그가_로드된다(self):
        """`f2_terms/catalogs/std-2026.3/` (최신판)이 실제로 검증을 통과하는지 —
        건수는 보지 않는다(카탈로그가 자라도 이 테스트는 안 깨져야 한다)."""
        g = load_glossary()

        assert g.term_count > 0
        assert g.catalog_version == "std-2026.3"

    def test_모르는_버전을_요청하면_가용_목록과_함께_거부한다(self):
        with pytest.raises(GlossaryCatalogError, match="std-2026.1"):
            load_glossary("존재하지-않는-버전")

    def test_sample_카탈로그는_available_versions에_없다(self):
        # `_sample` 은 T4 자체 검증용이지 실사전이 아니다. 가용 버전
        # 목록에 섞이면 사용자가 요청할 수 있는 버전으로 오인된다.
        assert "_sample" not in available_versions()

    def test_sample_카탈로그는_직접_지정하면_로드된다(self):
        from f2_terms.glossary import DEFAULT_CATALOG_DIR

        g = load_glossary("_sample", base_dir=DEFAULT_CATALOG_DIR)

        assert g.catalog_version == "_sample"


# ════════════════════════════════════════════════════════════════
# 전수 검증 — 문제를 전부 모아 한 번에
# ════════════════════════════════════════════════════════════════


class Test전수검증:
    def test_원본_필수_키_누락을_모아_보고한다(self):
        """`lang`·`authority`·`version`·`effective_date` 는 `GlossaryTerm`
        변환 후에는 사라지므로 raw dict 단계에서만 검사할 수 있다
        (`glossary.py` 모듈 docstring "검증을 두 층으로 나눈 이유")."""
        payload = {
            "version": "org-2026.1",
            "terms": [
                {"term_id": "X1", "category": "qty_unit", "canonical": "ABC"},
            ],
        }

        with pytest.raises(GlossaryCatalogError) as exc:
            build_override(payload, tier="organization")

        message = str(exc.value)
        assert "lang" in message
        assert "authority" in message
        assert "effective_date" in message

    def test_포트_항목은_country_누락을_원본_단계에서_거부한다(self):
        # 동음이의 여부와 무관하게 port 는 항상 country 를 요구한다 —
        # 지금은 후보가 하나뿐이라 충돌이 안 걸려도, 나중에 동음이의가
        # 추가되며 조용히 판별 불가가 되는 것을 편집 시점에 막는다.
        payload = {
            "version": "org-2026.1",
            "terms": [_raw_term("P1", "port", "SOMEPORT", version="org-2026.1")],
        }

        with pytest.raises(GlossaryCatalogError, match="country"):
            build_override(payload, tier="organization")

    def test_여러_문제를_한_번의_예외에_모두_담는다(self):
        """항목이 3개 이상 문제를 동시에 갖고 있어도 첫 문제에서 멈추지
        않고 전부 모아 던지는지 — 세션이 한 번에 하나씩만 고치게 되는
        상황을 막는 핵심 계약(`HANDOFF.md` §4.6)."""
        payload = {
            "version": "org-2026.1",
            "terms": [
                # 문제 1: term_id 중복
                _raw_term("DUP", "qty_unit", "ABC", version="org-2026.1"),
                _raw_term("DUP", "volume_unit", "DEF", version="org-2026.1"),
                # 문제 2: 모르는 category
                _raw_term("BAD-CAT", "존재하지_않는_클래스", "GHI", version="org-2026.1"),
            ],
        }

        with pytest.raises(GlossaryCatalogError) as exc:
            build_override(payload, tier="organization")

        message = str(exc.value)
        assert "중복" in message
        assert "알 수 없는 category" in message

    def test_사전_항목이_0건이면_거부한다(self, tmp_path: Path):
        _write_synthetic_catalog(tmp_path, "v-empty", "2026-01-01")
        # glossary.yaml/locode.yaml 을 빈 terms 로 덮어써 항목 0건을 만든다.
        (tmp_path / "v-empty" / "glossary.yaml").write_text(
            yaml.safe_dump({"catalog_version": "v-empty", "terms": []}), encoding="utf-8"
        )
        (tmp_path / "v-empty" / "locode.yaml").write_text(
            yaml.safe_dump({"catalog_version": "v-empty", "terms": []}), encoding="utf-8"
        )

        with pytest.raises(GlossaryCatalogError, match="하나도 없습니다"):
            load_glossary("v-empty", base_dir=tmp_path)


# ════════════════════════════════════════════════════════════════
# 정규화 키 충돌
# ════════════════════════════════════════════════════════════════


class Test정규화키충돌:
    def test_다른_클래스는_같은_canonical을_써도_충돌하지_않는다(self):
        # 인덱스가 (category, key) 로 이름공간을 나누므로 클래스가 다르면
        # 같은 표기가 있어도 무관하다.
        terms = [
            make_term("Q1", "qty_unit", "ABC"),
            make_term("V1", "volume_unit", "ABC"),
        ]

        g = Glossary(terms, catalog_version="t", effective_date="2026-01-01")

        assert [t.term_id for t in g.by_canonical_key("ABC", "qty_unit")] == ["Q1"]
        assert [t.term_id for t in g.by_canonical_key("ABC", "volume_unit")] == ["V1"]

    def test_별칭이_다른_항목의_canonical과_충돌하면_거부한다(self):
        terms = [
            make_term("Q1", "qty_unit", "KGM", aliases=["KG"]),
            make_term("Q2", "qty_unit", "KG"),
        ]

        with pytest.raises(GlossaryCatalogError, match="정규화 키 충돌"):
            Glossary(terms, catalog_version="t", effective_date="2026-01-01")

    def test_term_id가_중복되면_거부한다(self):
        terms = [
            make_term("X1", "qty_unit", "ABC"),
            make_term("X1", "volume_unit", "DEF"),
        ]

        with pytest.raises(GlossaryCatalogError, match="중복"):
            Glossary(terms, catalog_version="t", effective_date="2026-01-01")

    def test_별칭이_자기_canonical과_같으면_거부한다(self):
        terms = [make_term("X1", "qty_unit", "KGM", aliases=["KGM"])]

        with pytest.raises(GlossaryCatalogError, match="같습니다"):
            Glossary(terms, catalog_version="t", effective_date="2026-01-01")

    def test_포트_동음이의는_country가_있으면_허용된다(self):
        terms = [
            make_term("P1", "port", "PORTLAND, USA", aliases=["PORTLAND"], country="US"),
            make_term("P2", "port", "PORTLAND, AUSTRALIA", aliases=["PORTLAND"], country="AU"),
        ]

        g = Glossary(terms, catalog_version="t", effective_date="2026-01-01")

        hits = g.by_alias_key("PORTLAND", "port")
        assert {t.term_id for t in hits} == {"P1", "P2"}

    def test_포트_동음이의도_country가_없으면_거부한다(self):
        terms = [
            make_term("P1", "port", "PORTLAND, USA", aliases=["PORTLAND"], country="US"),
            make_term("P2", "port", "PORTLAND, AUSTRALIA", aliases=["PORTLAND"], country=None),
        ]

        with pytest.raises(GlossaryCatalogError, match="country"):
            Glossary(terms, catalog_version="t", effective_date="2026-01-01")

    def test_포트가_아닌_클래스는_동음이의를_허용하지_않는다(self):
        # port 만의 특례다 — 다른 클래스가 같은 방식으로 충돌하면
        # country 유무와 무관하게 거부해야 한다.
        terms = [
            make_term("Q1", "qty_unit", "AMBIGUOUS"),
            make_term("Q2", "qty_unit", "AMBIGUOUS"),
        ]

        with pytest.raises(GlossaryCatalogError, match="port 이외"):
            Glossary(terms, catalog_version="t", effective_date="2026-01-01")

    def test_deprecated_by가_없는_term_id를_가리키면_거부한다(self):
        terms = [make_term("X1", "qty_unit", "OLD", deprecated_by="NOT-A-REAL-ID")]

        with pytest.raises(GlossaryCatalogError, match="deprecated_by"):
            Glossary(terms, catalog_version="t", effective_date="2026-01-01")


# ════════════════════════════════════════════════════════════════
# 버전 선택
# ════════════════════════════════════════════════════════════════


class Test버전선택:
    def test_버전을_생략하면_effective_date가_최신인_것을_고른다(self, tmp_path: Path):
        _write_synthetic_catalog(tmp_path, "v2026.1", "2026-01-01")
        _write_synthetic_catalog(tmp_path, "v2026.2", "2026-06-01")

        g = load_glossary(base_dir=tmp_path)

        assert g.catalog_version == "v2026.2"

    def test_버전을_지정하면_effective_date와_무관하게_그것을_읽는다(self, tmp_path: Path):
        _write_synthetic_catalog(tmp_path, "v2026.1", "2026-01-01")
        _write_synthetic_catalog(tmp_path, "v2026.2", "2026-06-01")

        g = load_glossary("v2026.1", base_dir=tmp_path)

        assert g.catalog_version == "v2026.1"

    def test_카탈로그_버전이_디렉터리명과_다르면_거부한다(self, tmp_path: Path):
        _write_synthetic_catalog(tmp_path, "v2026.1", "2026-01-01")
        manifest_path = tmp_path / "v2026.1" / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["catalog_version"] = "v2026.9-거짓말"
        manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

        with pytest.raises(GlossaryCatalogError, match="다릅니다"):
            load_glossary("v2026.1", base_dir=tmp_path)

    def test_needs_glossary_클래스가_비면_표준_카탈로그_로드는_거부한다(self, tmp_path: Path):
        # `load_glossary` 는 항상 `check_coverage=True` 다 — port 클래스를
        # 통째로 빼면 "정책상 사전이 필요한데 항목이 0건" 으로 거부돼야 한다.
        _write_synthetic_catalog(tmp_path, "v-partial", "2026-01-01")
        (tmp_path / "v-partial" / "locode.yaml").write_text(
            yaml.safe_dump({"catalog_version": "v-partial", "terms": []}), encoding="utf-8"
        )

        with pytest.raises(GlossaryCatalogError, match="port"):
            load_glossary("v-partial", base_dir=tmp_path)

    def test_오버라이드는_부분_사전이라_커버리지를_요구하지_않는다(self):
        # `build_override` 는 `check_coverage=False` — 조직이 항구 하나만
        # 등록해도 유효해야 한다.
        payload = {
            "version": "org-2026.1",
            "terms": [_raw_term("P1", "port", "TESTPORT", version="org-2026.1", country="KR")],
        }

        g = build_override(payload, tier="organization")

        assert g.term_count == 1
        assert g.tier == "organization"


# ════════════════════════════════════════════════════════════════
# 3계층 오버라이드 — GlossaryStack
# ════════════════════════════════════════════════════════════════


class Test삼계층오버라이드:
    def _standard(self) -> Glossary:
        return Glossary(
            [make_term("STD-P1", "port", "BUSAN, KOREA", aliases=["PUSAN"], country="KR")],
            catalog_version="std-2026.1", effective_date="2026-01-01", tier="standard",
        )

    def test_계층에_없으면_표준까지_내려가_찾는다(self):
        standard = self._standard()
        organization = Glossary(
            [make_term("ORG-1", "qty_unit", "ABC")],  # port 와 무관한 항목
            catalog_version="org-1", effective_date="2026-01-01", tier="organization",
        )
        stack = GlossaryStack([standard, organization])

        hits = stack.lookup("PUSAN", "port")

        assert len(hits) == 1
        assert hits[0].tier == "standard"

    def test_조직_계층이_표준보다_우선한다(self):
        standard = self._standard()
        organization = Glossary(
            [make_term("ORG-P1", "port", "BUSAN ORG PORT", aliases=["PUSAN"], country="KR")],
            catalog_version="org-1", effective_date="2026-01-01", tier="organization",
        )
        stack = GlossaryStack([standard, organization])

        hits = stack.lookup("PUSAN", "port")

        assert len(hits) == 1
        assert hits[0].tier == "organization"
        assert hits[0].term.canonical == "BUSAN ORG PORT"

    def test_선적_계층이_조직_계층보다_우선한다(self):
        standard = self._standard()
        organization = Glossary(
            [make_term("ORG-P1", "port", "BUSAN ORG PORT", aliases=["PUSAN"], country="KR")],
            catalog_version="org-1", effective_date="2026-01-01", tier="organization",
        )
        shipment = Glossary(
            [make_term("SHP-P1", "port", "BUSAN SHIPMENT PORT", aliases=["PUSAN"], country="KR")],
            catalog_version="shp-1", effective_date="2026-01-01", tier="shipment",
        )
        stack = GlossaryStack([standard, organization, shipment])

        hits = stack.lookup("PUSAN", "port")

        assert len(hits) == 1
        assert hits[0].tier == "shipment"
        assert hits[0].term.canonical == "BUSAN SHIPMENT PORT"

    def test_diverges_from_standard가_표준과_다르면_채워진다(self):
        standard = self._standard()
        shipment = Glossary(
            [make_term("SHP-P1", "port", "BUSAN SHIPMENT PORT", aliases=["PUSAN"], country="KR")],
            catalog_version="shp-1", effective_date="2026-01-01", tier="shipment",
        )
        stack = GlossaryStack([standard, shipment])

        hit = stack.lookup("PUSAN", "port")[0]

        assert hit.diverges_from_standard == "BUSAN, KOREA"

    def test_diverges_from_standard는_표준과_같으면_비어있다(self):
        standard = self._standard()
        shipment = Glossary(
            # 표준과 canonical 이 완전히 같다 — "다르다"고 표기할 것이 없다.
            [make_term("SHP-P1", "port", "BUSAN, KOREA", aliases=["PUSAN"], country="KR")],
            catalog_version="shp-1", effective_date="2026-01-01", tier="shipment",
        )
        stack = GlossaryStack([standard, shipment])

        hit = stack.lookup("PUSAN", "port")[0]

        assert hit.diverges_from_standard is None

    def test_표준_계층_자신의_응답에는_diverges가_없다(self):
        standard = self._standard()
        organization = Glossary(
            [make_term("ORG-1", "qty_unit", "ABC")],
            catalog_version="org-1", effective_date="2026-01-01", tier="organization",
        )
        stack = GlossaryStack([standard, organization])

        hit = stack.lookup("PUSAN", "port")[0]

        assert hit.tier == "standard"
        assert hit.diverges_from_standard is None

    def test_풀은_전_계층을_합친다(self):
        standard = self._standard()  # canonical 1건 + 별칭 1건 = 2 IndexedTerm
        organization = Glossary(
            [make_term("ORG-P1", "port", "INCHEON, KOREA", aliases=["INCHON"], country="KR")],
            catalog_version="org-1", effective_date="2026-01-01", tier="organization",
        )
        stack = GlossaryStack([standard, organization])

        combined = stack.pool("port")

        assert len(combined) == len(standard.pool("port")) + len(organization.pool("port"))


# ════════════════════════════════════════════════════════════════
# 미검증 집계
# ════════════════════════════════════════════════════════════════


class Test미검증집계:
    def test_verified가_아닌_항목_수를_센다(self):
        terms = [
            make_term("A", "qty_unit", "A", verified=True),
            make_term("B", "qty_unit", "B", verified=False),
            make_term("C", "qty_unit", "C", verified=False),
        ]

        g = Glossary(terms, catalog_version="t", effective_date="2026-01-01")

        assert g.unverified_count == 2

    def test_by_class는_canonical_건수만_센다(self):
        # 별칭이 여럿이어도 by_class 의 category 건수는 canonical(=term) 수다.
        terms = [
            make_term("A", "qty_unit", "A", aliases=["A1", "A2", "A3"]),
            make_term("B", "volume_unit", "B"),
        ]

        g = Glossary(terms, catalog_version="t", effective_date="2026-01-01")

        assert g.by_class() == {"qty_unit": 1, "volume_unit": 1}
        assert g.alias_count == 3


# ════════════════════════════════════════════════════════════════
# 주입 seam
# ════════════════════════════════════════════════════════════════


class Test주입seam:
    def test_Glossary_terms로_직접_주입한다(self):
        # `RuleEngine(rules=[...])` 와 같은 이유 — 테스트가 파일을 만들지
        # 않고도 인덱스·조회 로직을 검증할 수 있어야 한다.
        terms = [make_term("Q1", "qty_unit", "KGM", aliases=["KG", "KGS"])]

        g = Glossary(terms, catalog_version="test-1", effective_date="2026-01-01")

        assert [t.term_id for t in g.by_alias_key("KGS", "qty_unit")] == ["Q1"]

    def test_주입_경로도_키_충돌_검증을_받는다(self):
        # 파일에서 온 카탈로그만 검증받고 주입된 항목은 면제되면, 테스트가
        # 만든 표본 사전이 실제로는 발동하지 않을 불변식을 검증하는 셈이
        # 된다 — 주입도 로더와 같은 보장을 받아야 한다.
        terms = [
            make_term("A", "qty_unit", "SAME"),
            make_term("B", "qty_unit", "SAME"),
        ]

        with pytest.raises(GlossaryCatalogError):
            Glossary(terms, catalog_version="test-1", effective_date="2026-01-01")


# ════════════════════════════════════════════════════════════════
# 정합성 — 다른 자료구조와 어긋나지 않는지
# ════════════════════════════════════════════════════════════════


class Test기존_동의어표와의_정합성:
    def test_모든_클래스는_진입_경로를_갖는다(self):
        """`policy.CLASSES` 전부가 `FIELD_CLASS` 또는 `FIELD_SCAN_CLASSES`
        어딘가에 등장해야 한다 — 어느 필드로도 매핑되지 않은 클래스는
        절대 발동하지 않는 죽은 코드다."""
        mapped = set(policy.FIELD_CLASS.values())
        scanned: set = set()
        for classes in policy.FIELD_SCAN_CLASSES.values():
            scanned |= set(classes)

        reachable = mapped | scanned
        unreachable = set(policy.CLASSES) - reachable

        assert unreachable == set(), f"진입 경로가 없는 클래스: {unreachable}"

    def test_카탈로그의_category_는_전부_policy_에_있다(self):
        """실제 표준 카탈로그의 모든 항목이 `policy.CLASSES` 가 아는
        category 만 쓰는지 — 건수가 아니라 **집합 포함** 만 확인하므로
        카탈로그가 자라도 이 테스트는 깨지지 않는다."""
        g = load_glossary()

        categories = {t.category for t in g.terms}

        assert categories <= set(policy.CLASSES)

    # Stage A 카탈로그(항구 52건: 한·중·일·동남아·미주·유럽)가 아직 담지 않은
    # `PORT_SYNONYMS` 쌍. 인도 3곳·노르웨이·사우디 항구가 없고, BEIJING/PEKING 은
    # 애초에 해항이 아니다(톈진이 그 역할을 한다).
    #
    # 이 목록을 상수로 박아 두는 이유: 그냥 `assert not uncovered` 로 두면 테스트가
    # **영구히 빨갛고**, 빨간 테스트가 상수처럼 있으면 사람이 빨강을 무시하게 된다.
    # 그러면 진짜 회귀가 묻힌다. 대신 "지금 못 덮는 것이 정확히 이것들"을 고정해
    # 두면, 커버리지가 늘거나 줄 때 **양방향으로** 테스트가 알려 준다.
    PORT_SYNONYM_GAPS = {
        ("BOMBAY", "MUMBAI"),
        ("CHENNAI", "MADRAS"),
        ("CALCUTTA", "KOLKATA"),
        ("BEIJING", "PEKING"),
        ("TROMSO", "TROMSOE"),
        ("JEDDA", "JEDDAH"),
    }

    def _synonym_coverage(self):
        from f3_rules.checks import PORT_SYNONYMS

        g = load_glossary()
        covered, uncovered = set(), set()
        for pair in PORT_SYNONYMS:
            words = sorted(pair)
            id_sets = []
            for word in words:
                key = normalize_key(word)
                hits = g.by_canonical_key(key, "port") + g.by_alias_key(key, "port")
                id_sets.append({t.term_id for t in hits})
            if bool(id_sets[0]) and all(id_sets[0] & s for s in id_sets[1:]):
                covered.add(tuple(words))
            else:
                uncovered.add(tuple(words))
        return covered, uncovered

    def test_사전이_덮는_쌍은_한_코드로_모인다(self):
        """덮는 쌍은 **반드시** 하나의 term_id 로 수렴해야 한다.

        진짜 위험은 "안 덮는 것"이 아니라 **한쪽만 덮는 것**이다. `BUSAN` 은
        `KRPUS` 로 가는데 `PUSAN` 은 아무 데도 안 가면, F3 의 `match_place` 와
        F2 의 판단이 갈려 같은 값에 서로 다른 결론이 나온다. 이 테스트가 막는
        것이 그 상태다.
        """
        covered, _ = self._synonym_coverage()

        assert covered, "덮는 쌍이 하나도 없다면 사전 적재나 조회가 깨진 것이다"

    def test_아직_못_덮는_쌍은_알려진_목록과_같다(self):
        """커버리지 격차를 **고정**한다 — 양방향으로.

        새 항구를 넣어 격차가 줄면 이 테스트가 깨져서 `PORT_SYNONYM_GAPS` 를
        갱신하라고 알려 준다. 반대로 누가 항구를 지워 격차가 늘어도 알려 준다.
        이관(T19)의 착수 조건이 이 목록이 비는 것이다(`HANDOFF.md` §6.1).
        """
        _, uncovered = self._synonym_coverage()

        assert uncovered == self.PORT_SYNONYM_GAPS, (
            f"PORT_SYNONYMS 커버리지가 바뀌었다. 지금 못 덮는 것: {sorted(uncovered)} / "
            f"알려진 목록: {sorted(self.PORT_SYNONYM_GAPS)} — "
            "카탈로그를 늘렸다면 위 상수를 갱신하고, 줄인 게 아니라면 왜 줄었는지 확인하라."
        )
