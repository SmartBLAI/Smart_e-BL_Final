"""f6_reality/adapter.py — 화이트박스 (분기 커버리지).

설계표는 docs/ai-service/whitebox-test-plan.md 참고.
"""

from __future__ import annotations

import json
from urllib import error as urlerror

import pytest

from f6_reality.adapter import (
    EventSourceError,
    FixtureSource,
    UlsanVtsSource,
    resolve_call_sign,
    source_from_env,
)


class TestFixtureSource:
    def test_정상_JSON_리스트를_그대로_돌려준다(self, tmp_path):
        path = tmp_path / "events.json"
        path.write_text(json.dumps([{"a": 1}]), encoding="utf-8")
        assert FixtureSource(path=path).fetch() == [{"a": 1}]

    def test_파일이_없으면_EventSourceError(self, tmp_path):
        with pytest.raises(EventSourceError):
            FixtureSource(path=tmp_path / "missing.json").fetch()

    def test_JSON이_아니면_EventSourceError(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        with pytest.raises(EventSourceError):
            FixtureSource(path=path).fetch()

    def test_리스트가_아닌_JSON이면_EventSourceError(self, tmp_path):
        path = tmp_path / "obj.json"
        path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        with pytest.raises(EventSourceError):
            FixtureSource(path=path).fetch()

    def test_경로_미지정시_환경변수를_따른다(self, tmp_path, monkeypatch):
        path = tmp_path / "env.json"
        path.write_text(json.dumps([]), encoding="utf-8")
        monkeypatch.setenv("REALITY_FIXTURE_PATH", str(path))
        assert FixtureSource().path == path


class TestUlsanVtsSource:
    def test_base_url이_없으면_즉시_EventSourceError(self, monkeypatch):
        monkeypatch.delenv("ULSAN_VTS_BASE_URL", raising=False)
        src = UlsanVtsSource(base_url="", service_key="real-key")
        with pytest.raises(EventSourceError):
            src.fetch()

    def test_service_key가_없으면_즉시_EventSourceError(self):
        src = UlsanVtsSource(base_url="https://example.org", service_key="")
        with pytest.raises(EventSourceError):
            src.fetch()

    def test_키가_changeme면_즉시_EventSourceError(self):
        src = UlsanVtsSource(base_url="https://example.org", service_key="changeme")
        with pytest.raises(EventSourceError):
            src.fetch()

    def test_call_sign이_없으면_즉시_EventSourceError(self):
        """실측: callsgn 없이 호출하면 게이트웨이가 HTTP_ERROR 를 낸다 —
        네트워크를 타기 전에 막는다."""
        src = UlsanVtsSource(base_url="https://example.org", service_key="k")
        with pytest.raises(EventSourceError):
            src.fetch()

    def test_HTTP_호출이_실패하면_EventSourceError로_번역한다(self, monkeypatch):
        src = UlsanVtsSource(base_url="https://example.org", service_key="k")

        def _raise(*a, **kw):
            raise urlerror.URLError("boom")

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", _raise)
        with pytest.raises(EventSourceError):
            src.fetch(call_sign="150040")

    def test_스킴없는_URL은_urlopen이_ValueError를_던지고_키는_마스킹된다(self, monkeypatch):
        """base_url 에 스킴(https://)이 빠지면 urlopen 이 URLError 가 아닌
        ValueError 를 던진다 — 메시지에 요청 URL 전체(키 포함)가 그대로
        들어있으므로, EventSourceError 로 옮겨질 때 키가 지워져야 한다."""
        src = UlsanVtsSource(base_url="example.org/vts", service_key="real-secret-key")
        with pytest.raises(EventSourceError) as exc_info:
            src.fetch(call_sign="150040")
        assert "real-secret-key" not in str(exc_info.value)

    def test_응답이_JSON이_아니면_EventSourceError(self, monkeypatch):
        src = UlsanVtsSource(base_url="https://example.org", service_key="k")

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"not json"

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        with pytest.raises(EventSourceError):
            src.fetch(call_sign="150040")

    def test_응답_형식이_예상과_다르면_EventSourceError(self, monkeypatch):
        src = UlsanVtsSource(base_url="https://example.org", service_key="k")
        body = json.dumps({"response": {"body": {"items": "not-a-list"}}}).encode()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        with pytest.raises(EventSourceError):
            src.fetch(call_sign="150040")

    def test_헤더_resultCode가_00이_아니면_EventSourceError(self, monkeypatch):
        src = UlsanVtsSource(base_url="https://example.org", service_key="k")
        body = json.dumps(
            {"response": {"header": {"resultCode": "10", "resultMsg": "INVALID_REQUEST_PARAMETER_ERROR"}}}
        ).encode()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        with pytest.raises(EventSourceError):
            src.fetch(call_sign="150040")

    def test_결과없음_030은_오류가_아니라_빈_리스트다(self, monkeypatch):
        """실측: 매칭되는 레코드가 없으면 response 봉투 없이 최상위
        {"resultCode":"030"} 만 온다 — 오류가 아니라 0건이다."""
        src = UlsanVtsSource(base_url="https://example.org", service_key="k")
        body = json.dumps({"resultMsg": "NODATA_ERROR", "resultCode": "030"}).encode()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        assert src.fetch(call_sign="999999") == []

    def test_게이트웨이_오류_봉투도_EventSourceError(self, monkeypatch):
        """실측: 필수 파라미터 없이 호출하면 response/resultCode 대신
        OpenAPI_ServiceResponse.cmmMsgHeader 로 온다."""
        src = UlsanVtsSource(base_url="https://example.org", service_key="k")
        body = json.dumps(
            {
                "OpenAPI_ServiceResponse": {
                    "cmmMsgHeader": {
                        "errMsg": "HTTP_ERROR",
                        "returnAuthMsg": "HTTP 에러",
                        "returnReasonCode": "04",
                    }
                }
            }
        ).encode()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        with pytest.raises(EventSourceError):
            src.fetch(call_sign="150040")

    def test_정상_응답이면_items를_돌려준다(self, monkeypatch):
        src = UlsanVtsSource(base_url="https://example.org", service_key="k")
        body = json.dumps({"response": {"body": {"items": [{"x": 1}]}}}).encode()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        assert src.fetch(call_sign="150040") == [{"x": 1}]

    def test_실_응답_모양은_items_item에_감싸이고_단건이면_dict다(self, monkeypatch):
        """실측: 정상 응답은 body.items 가 아니라 body.items.item 이고,
        레코드가 1건이면 item 자체가 리스트가 아니라 dict 로 온다."""
        src = UlsanVtsSource(base_url="https://example.org", service_key="k")
        body = json.dumps(
            {
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
                    "body": {"totalCount": "1", "items": {"item": {"x": 1}}},
                }
            }
        ).encode()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        assert src.fetch(call_sign="150040") == [{"x": 1}]

    def test_items가_빈문자열이면_빈_리스트다(self, monkeypatch):
        src = UlsanVtsSource(base_url="https://example.org", service_key="k")
        body = json.dumps(
            {"response": {"header": {"resultCode": "00"}, "body": {"items": ""}}}
        ).encode()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        assert src.fetch(call_sign="150040") == []

    def test_totalCount가_받은_건수보다_많으면_잘림으로_보고_EventSourceError(self, monkeypatch):
        src = UlsanVtsSource(base_url="https://example.org", service_key="k")
        body = json.dumps(
            {
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {"totalCount": "1500", "items": {"item": [{"x": 1}]}},
                }
            }
        ).encode()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        with pytest.raises(EventSourceError):
            src.fetch(call_sign="150040")

    def test_알수없는_봉투_모양이면_EventSourceError(self, monkeypatch):
        src = UlsanVtsSource(base_url="https://example.org", service_key="k")

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"nonsense": True}).encode()

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        with pytest.raises(EventSourceError):
            src.fetch(call_sign="150040")

    def test_serviceKey는_다시_인코딩하지_않고_그대로_붙인다(self, monkeypatch):
        """공공데이터포털의 Encoding 키(%2B 등 포함)를 urlencode 에 다시
        태우면 %252B 로 이중 인코딩된다 — 그 회귀를 막는다."""
        src = UlsanVtsSource(base_url="https://example.org", service_key="a%2Bb%3D%3D")
        captured = {}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"response": {"body": {"items": []}}}).encode()

        def _urlopen(url, timeout=None):
            captured["url"] = url
            return _Resp()

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", _urlopen)
        src.fetch(call_sign="150040")
        assert "serviceKey=a%2Bb%3D%3D" in captured["url"]
        assert "%25" not in captured["url"]

    def test_year를_주면_ptentVtsYr로_실린다(self, monkeypatch):
        src = UlsanVtsSource(base_url="https://example.org", service_key="k")
        captured = {}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"response": {"body": {"items": []}}}).encode()

        def _urlopen(url, timeout=None):
            captured["url"] = url
            return _Resp()

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", _urlopen)
        src.fetch(call_sign="150040", year="2025")
        assert "ptentVtsYr=2025" in captured["url"]
        assert "callsgn=150040" in captured["url"]

    def test_생성자_인자가_환경변수보다_우선한다(self, monkeypatch):
        monkeypatch.setenv("ULSAN_VTS_BASE_URL", "https://env.example.org")
        monkeypatch.setenv("ULSAN_VTS_TIMEOUT", "99")
        src = UlsanVtsSource(base_url="https://explicit.example.org", timeout=3.0)
        assert src.base_url == "https://explicit.example.org"
        assert src.timeout == 3.0


class TestResolveCallSign:
    """resolve_call_sign — 해양수산부 선박제원정보 선명→콜사인 조회.

    부분일치 검색이라(실측: "OSUNG" 검색에 "BOSUNG"도 걸림) 정확히
    하나로 좁혀지는 경우만 콜사인을 돌려주고, 그 외엔 전부 None.
    """

    def _xml(self, *items: str, result_code: str = "00") -> bytes:
        body = "".join(items)
        return (
            f"<response><header><resultCode>{result_code}</resultCode></header>"
            f"<body><items>{body}</items></body></response>"
        ).encode("utf-8")

    def _item(self, clsgn: str, eng: str = "", kor: str = "") -> str:
        return f"<item><clsgn>{clsgn}</clsgn><vsslEngNm>{eng}</vsslEngNm><vsslKorNm>{kor}</vsslKorNm></item>"

    def test_선명이_비어있으면_None(self):
        assert resolve_call_sign("") is None
        assert resolve_call_sign("   ") is None
        assert resolve_call_sign(None) is None

    def test_service_key가_없으면_None(self, monkeypatch):
        monkeypatch.delenv("ULSAN_VTS_SERVICE_KEY", raising=False)
        assert resolve_call_sign("OSUNG", base_url="https://example.org", service_key="") is None
        assert (
            resolve_call_sign("OSUNG", base_url="https://example.org", service_key="changeme")
            is None
        )

    def test_영문선명_정확히_하나_일치하면_콜사인을_돌려준다(self, monkeypatch):
        body = self._xml(
            self._item("100000", eng="NO.2000 BOSUNG"),
            self._item("150040", eng="OSUNG", kor="오성호"),
        )

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        assert (
            resolve_call_sign("OSUNG", base_url="https://example.org", service_key="k")
            == "150040"
        )

    def test_BL_선명_표기_접두와_항차를_벗겨_검색하고_비교한다(self, monkeypatch):
        body = self._xml(
            self._item("100000", eng="NO.2000 BOSUNG"),
            self._item("150040", eng="OSUNG", kor="오성호"),
        )
        seen = {}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        def _open(url, *a, **kw):
            seen["url"] = url
            return _Resp()

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", _open)
        assert (
            resolve_call_sign("M/V OSUNG / 2608E", base_url="https://example.org", service_key="k")
            == "150040"
        )
        assert "vsslNm=OSUNG" in seen["url"] and "2608E" not in seen["url"]

    def test_국문선명도_정확히_일치하면_콜사인을_돌려준다(self, monkeypatch):
        body = self._xml(self._item("150040", eng="OSUNG", kor="오성호"))

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        assert (
            resolve_call_sign("오성호", base_url="https://example.org", service_key="k")
            == "150040"
        )

    def test_동명이선박으로_둘_이상_일치하면_None(self, monkeypatch):
        body = self._xml(
            self._item("150040", eng="OSUNG"),
            self._item("999999", eng="OSUNG"),
        )

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        assert resolve_call_sign("OSUNG", base_url="https://example.org", service_key="k") is None

    def test_정확히_일치하는_항목이_없으면_None(self, monkeypatch):
        body = self._xml(self._item("100000", eng="NO.2000 BOSUNG"))

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        assert resolve_call_sign("OSUNG", base_url="https://example.org", service_key="k") is None

    def test_resultCode가_00이_아니면_None(self, monkeypatch):
        body = self._xml(result_code="99")

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        assert resolve_call_sign("OSUNG", base_url="https://example.org", service_key="k") is None

    def test_HTTP_호출이_실패하면_None(self, monkeypatch):
        def _raise(*a, **kw):
            raise urlerror.URLError("boom")

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", _raise)
        assert resolve_call_sign("OSUNG", base_url="https://example.org", service_key="k") is None

    def test_XML_파싱이_실패하면_None(self, monkeypatch):
        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"not xml"

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", lambda *a, **kw: _Resp())
        assert resolve_call_sign("OSUNG", base_url="https://example.org", service_key="k") is None

    def test_예상밖_예외도_삼키고_None을_돌려준다(self, monkeypatch):
        """UlsanVtsSource.fetch() 와 같은 이유(스킴 없는 base_url 등)로
        URLError/TimeoutError/ParseError 가 아닌 예외도 날 수 있다 —
        여기선 다시 던지지 않고 그냥 None(특정 못 함)으로 삼켜야 한다."""

        def _raise(*a, **kw):
            raise ValueError("unknown url type: 'example.org?serviceKey=k'")

        monkeypatch.setattr("f6_reality.adapter.urlrequest.urlopen", _raise)
        assert resolve_call_sign("OSUNG", base_url="https://example.org", service_key="k") is None


class TestSourceFromEnv:
    def test_기본값은_fixture(self, monkeypatch):
        monkeypatch.delenv("REALITY_EVENT_SOURCE", raising=False)
        assert isinstance(source_from_env(), FixtureSource)

    def test_ulsan을_대소문자_공백_무관하게_인식한다(self, monkeypatch):
        monkeypatch.setenv("REALITY_EVENT_SOURCE", " ULSAN ")
        assert isinstance(source_from_env(), UlsanVtsSource)

    def test_알수없는_값은_fixture로_떨어진다(self, monkeypatch):
        monkeypatch.setenv("REALITY_EVENT_SOURCE", "typo")
        assert isinstance(source_from_env(), FixtureSource)
