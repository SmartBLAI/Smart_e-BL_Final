"""F2 API 계층(`/normalize`·`/glossary` 등) 테스트.

`tests/test_api.py` 의 module-scope `TestClient` 픽스처 형태를 그대로
따른다. 실제 카탈로그(`std-2026.1`)를 타되 **건수에 의존하지 않는다** —
카탈로그가 커지거나 줄어도 이 파일은 안 깨져야 한다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

fastapi = pytest.importorskip("fastapi", reason="FastAPI 미설치 시 건너뜀")
from fastapi.testclient import TestClient  # noqa: E402

import api.main as main  # noqa: E402
from api.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# 시각은 주입한다 — 서버가 만드는 것이 아니라 요청이 싣는 값이다
# (`f2_terms/types.py:Correction.decided_at` docstring).
AS_OF = datetime(2026, 5, 25)
DECIDED_AT = AS_OF.isoformat()


def _normalize(client, **kwargs) -> dict:
    return client.post("/normalize", json=kwargs).json()


class TestNormalize:
    def test_모든_구성요소를_담는다(self, client):
        """`suggestions`·`notices`·`unevaluated`·`versions`·`stats` 가 전부
        실려야 화면이 침묵 없이 판정 결과를 그릴 수 있다."""
        response = client.post(
            "/normalize",
            json={"bl": {"port_of_loading": "부산", "gross_weight": "1,234.50 KGS"}},
        )
        body = response.json()

        assert response.status_code == 200
        assert set(body) >= {"suggestions", "notices", "unevaluated", "versions", "stats"}
        assert body["suggestions"], "표준 사전에 있는 값인데 제안이 하나도 없다"
        assert body["versions"]["glossary_version"]
        assert body["versions"]["cascade_version"]
        assert "by_stage" in body["stats"]

    def test_bl만_주면_선하증권_한장으로_해석한다(self, client):
        body = _normalize(client, bl={"port_of_loading": "부산"})

        assert body["suggestions"][0]["field"]["doc"] == "선하증권"

    def test_documents와_bl이_모두_없으면_400이다(self, client):
        response = client.post("/normalize", json={})

        assert response.status_code == 400

    def test_bl이_빈_객체여도_400이다(self, client):
        response = client.post("/normalize", json={"bl": {}})

        assert response.status_code == 400

    def test_없는_glossary_version은_400이고_가용_목록을_담는다(self, client):
        response = client.post(
            "/normalize", json={"bl": {"port_of_loading": "부산"}, "glossary_version": "nope-9999"}
        )

        assert response.status_code == 400
        assert "std-2026.1" in response.json()["detail"]

    def test_형식이_틀린_오버라이드는_400이다(self, client):
        """조직 사전 오버라이드가 깨져 있으면 요청 오류다 — 서버는 안 죽는다."""
        response = client.post(
            "/normalize",
            json={
                "bl": {"port_of_loading": "부산"},
                "overrides": {"organization": {"version": "org-1", "terms": []}},
            },
        )

        assert response.status_code == 400


class TestNormalizeApply:
    def test_왕복은_수치와_상호_본체를_보존한다(self, client):
        bl = {"gross_weight": "1,234.50 KGS", "shipper": "GAE WOON  CO.,LTD"}
        suggestions = _normalize(client, bl=bl)["suggestions"]

        applied = client.post(
            "/normalize/apply",
            json={
                "documents": [{"doc": "선하증권", "fields": bl}],
                "suggestions": suggestions,
                "scope": "field",
                "decided_by": "tester",
                "decided_at": DECIDED_AT,
            },
        ).json()

        fields = applied["documents"][0]["fields"]
        assert fields["gross_weight"] == "1,234.50 KGM"  # 수치는 그대로.
        assert fields["shipper"] == "GAE WOON  Co., Ltd."  # "GAE WOON" 본체 보존.
        assert len(applied["corrections"]) == len(suggestions)
        assert all(c["decision"] == "accepted" for c in applied["corrections"])

    def test_제안이_전부_변조되면_400이다(self, client):
        bl = {"port_of_loading": "부산"}
        suggestions = _normalize(client, bl=bl)["suggestions"]
        for s in suggestions:
            s["suggestion_id"] = "sg1_deadbeefdeadbeefdeadbeef"

        response = client.post(
            "/normalize/apply",
            json={
                "documents": [{"doc": "선하증권", "fields": bl}],
                "suggestions": suggestions,
                "scope": "field",
                "decided_by": "tester",
                "decided_at": DECIDED_AT,
            },
        )

        assert response.status_code == 400

    def test_제안이_일부만_변조되면_200이고_그_건만_unapplied다(self, client):
        bl = {"port_of_loading": "부산", "gross_weight": "1,234.50 KGS"}
        suggestions = _normalize(client, bl=bl)["suggestions"]
        assert len(suggestions) >= 2
        tampered_id = suggestions[0]["suggestion_id"]
        suggestions[0]["suggestion_id"] = "sg1_deadbeefdeadbeefdeadbeef"

        response = client.post(
            "/normalize/apply",
            json={
                "documents": [{"doc": "선하증권", "fields": bl}],
                "suggestions": suggestions,
                "scope": "field",
                "decided_by": "tester",
                "decided_at": DECIDED_AT,
            },
        )
        body = response.json()

        assert response.status_code == 200
        assert len(body["unapplied"]) == 1
        assert body["unapplied"][0]["suggestion_id"] == "sg1_deadbeefdeadbeefdeadbeef"
        # 변조 안 된 나머지는 정상 적용됐다.
        assert len(body["corrections"]) == len(suggestions) - 1
        assert tampered_id not in {c["suggestion_id"] for c in body["corrections"]}

    def test_scope_all이면_영향_범위_자리도_함께_적용한다(self, client):
        documents = [
            {"doc": "선하증권", "doc_id": "A", "fields": {"shipper": "GAE WOON CO.,LTD"}},
            {"doc": "선하증권", "doc_id": "B", "fields": {"notify_party": "GAE WOON CO.,LTD"}},
        ]
        norm = client.post("/normalize", json={"documents": documents}).json()
        suggestion = next(s for s in norm["suggestions"] if s["field"]["doc_id"] == "A")
        assert suggestion["impact"], "이 테스트는 impact 가 있어야 의미가 있다"

        applied = client.post(
            "/normalize/apply",
            json={
                "documents": documents,
                "suggestions": [suggestion],
                "scope": "all",
                "decided_by": "tester",
                "decided_at": DECIDED_AT,
            },
        ).json()

        by_doc_id = {d["doc_id"]: d["fields"] for d in applied["documents"]}
        assert by_doc_id["A"]["shipper"] == "GAE WOON Co., Ltd."
        assert by_doc_id["B"]["notify_party"] == "GAE WOON Co., Ltd."

    def test_적용_대상_서류가_없으면_unapplied_사유를_남긴다(self, client):
        bl = {"port_of_loading": "부산"}
        [suggestion] = _normalize(client, bl=bl)["suggestions"]

        response = client.post(
            "/normalize/apply",
            json={
                "documents": [{"doc": "상업송장", "fields": {"invoice_no": "X"}}],  # 다른 서류
                "suggestions": [suggestion],
                "scope": "field",
                "decided_by": "tester",
                "decided_at": DECIDED_AT,
            },
        )
        body = response.json()

        assert response.status_code == 200
        assert len(body["unapplied"]) == 1
        assert body["corrections"] == []

    def test_잘못된_scope는_422다(self, client):
        response = client.post(
            "/normalize/apply",
            json={
                "documents": [{"doc": "선하증권", "fields": {}}],
                "suggestions": [],
                "scope": "everything",
                "decided_by": "tester",
                "decided_at": DECIDED_AT,
            },
        )

        assert response.status_code == 422


class TestNormalizeReject:
    def test_거절은_Correction을_반환한다(self, client):
        bl = {"port_of_loading": "부산"}
        [suggestion] = _normalize(client, bl=bl)["suggestions"]

        response = client.post(
            "/normalize/reject",
            json={
                "suggestions": [suggestion],
                "reason": "false_positive",
                "note": "우리 조직은 원문 표기를 쓴다",
                "decided_by": "reviewer-1",
                "decided_at": DECIDED_AT,
            },
        )
        body = response.json()

        assert response.status_code == 200
        [correction] = body["corrections"]
        assert correction["decision"] == "rejected"
        assert correction["decided_by"] == "reviewer-1"
        assert correction["reason"] == "false_positive"
        assert correction["suggestion_id"] == suggestion["suggestion_id"]

    def test_거절은_변조_대조를_하지_않는다(self, client):
        """거절은 값을 바꾸지 않으므로 `suggestion_id` 재검증을 하지 않는다
        — 사람이 "틀렸다"고 판단한 사실만 기록하면 된다."""
        bl = {"port_of_loading": "부산"}
        [suggestion] = _normalize(client, bl=bl)["suggestions"]
        suggestion["suggestion_id"] = "sg1_deadbeefdeadbeefdeadbeef"

        response = client.post(
            "/normalize/reject",
            json={
                "suggestions": [suggestion],
                "reason": "other",
                "decided_by": "reviewer-1",
                "decided_at": DECIDED_AT,
            },
        )

        assert response.status_code == 200

    def test_잘못된_reason은_422다(self, client):
        bl = {"port_of_loading": "부산"}
        [suggestion] = _normalize(client, bl=bl)["suggestions"]

        response = client.post(
            "/normalize/reject",
            json={
                "suggestions": [suggestion],
                "reason": "그냥 싫음",  # 닫힌 집합 밖.
                "decided_by": "reviewer-1",
                "decided_at": DECIDED_AT,
            },
        )

        assert response.status_code == 422


class TestGlossary:
    def test_GET_glossary는_미검증_건수를_보고한다(self, client):
        body = client.get("/glossary").json()

        assert isinstance(body["unverified_term_count"], int)
        assert body["unverified_term_count"] >= 0
        assert body["catalog_version"]
        assert "std-2026.1" in body["available_versions"]

    def test_POST_glossary_validate는_문제_전부를_보고한다(self, client):
        """항목 하나가 아니라 카탈로그 전체의 문제를 한 번에 모아 던져야
        한다(`glossary.py` "문제를 전부 모아 한 번에" 규약) — 하나씩만
        보고하면 편집자가 고치고 다시 돌리기를 반복해야 한다."""
        response = client.post(
            "/glossary/validate",
            json={
                "version": "org-broken",
                "terms": [
                    {"term_id": "A"},  # 필수 키 대부분 누락
                    {
                        "term_id": "B",
                        "canonical": "X",
                        "category": "존재하지-않는-클래스",
                        "lang": "en",
                        "authority": "TEST",
                        "version": "1",
                        "effective_date": "2026-01-01",
                    },
                ],
            },
        )
        body = response.json()

        assert response.status_code == 400
        assert isinstance(body["detail"], list)
        assert len(body["detail"]) > 1  # 항목 하나짜리 오류가 아니다.

    def test_POST_glossary_validate는_정상_사전은_통과시킨다(self, client):
        response = client.post(
            "/glossary/validate",
            json={
                "version": "org-2026.1",
                "terms": [
                    {
                        "term_id": "ORG.TESTPORT",
                        "canonical": "KRTST",
                        "category": "port",
                        "lang": "code",
                        "authority": "조직 사전",
                        "version": "org-2026.1",
                        "effective_date": "2026-01-01",
                        "country": "KR",
                        "aliases": ["테스트항"],
                    }
                ],
            },
        )
        body = response.json()

        assert response.status_code == 200
        assert body["ok"] is True
        assert body["terms"] == 1


class TestHealth:
    def test_사전_버전과_건수를_담는다(self, client):
        body = client.get("/health").json()

        assert body["glossary_version"]
        assert isinstance(body["glossary_terms"], int)
        assert body["glossary_terms"] > 0


class TestLLM실패:
    def test_LLM이_실패해도_200이고_결정론_제안은_산다(self, client, monkeypatch):
        """`api.md` "예측 실패는 200 이다" 와 같은 판단 — 선정기가 뭘
        잘못했다고 요청 전체를 500 으로 내리면 이미 확정된 제안까지
        함께 잃는다."""

        class _FailingSelector:
            def select(self, items):
                raise RuntimeError("LLM 서비스 단절")

        monkeypatch.setattr(main, "_selector", _FailingSelector())
        monkeypatch.setattr(main, "_selector_resolved", True)

        response = client.post(
            "/normalize",
            json={
                # "ROTERDAM"(오타) — ④유사도 후보가 ROTTERDAM/AMSTERDAM 로
                # 갈린다(적용 표기가 서로 달라 후보 전원 일치 축약에 걸리지
                # 않는다). "포틀랜드"는 이제 못 쓴다 — 동음이의 두 후보의
                # bl_form 이 둘 다 "PORTLAND"로 같아 `_build` 가
                # requires_choice 를 접어 단일 제안으로 확정해 버리므로
                # 선정기 호출 자체가 일어나지 않는다.
                "bl": {"port_of_loading": "ROTERDAM", "gross_weight": "1,234.50 KGS"},
                "glossary_version": "std-2026.1",  # normalizer_for 가 매번 새 Normalizer 를 만들게 한다.
                "llm": True,
            },
        )
        body = response.json()

        assert response.status_code == 200
        assert body["stats"]["llm_path"] == "failed"
        # 결정론 제안(단위 정렬)은 그대로 살아 있다.
        assert any(s["term_class"] == "qty_unit" and s["to_be"] == "KGM" for s in body["suggestions"])
