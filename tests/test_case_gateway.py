from unittest.mock import MagicMock, patch
import pytest

from case_gateway import CaseGateway, CaseQuery, CaseRecord, CaseSearchResult, CaseDetail
from case_gateway.provider import CaseProvider


class FakeProvider(CaseProvider):
    def __init__(self, name: str, available: bool = True):
        self._name = name
        self._available = available

    @property
    def name(self) -> str:
        return self._name

    def is_available(self, token=None, cookie=None) -> bool:
        return self._available

    def search(self, query: CaseQuery) -> CaseSearchResult:
        if not self._available:
            return CaseSearchResult(
                source=self._name,
                query=query.keyword,
                error="AUTHENTICATION_REQUIRED",
                message="Need auth",
            )
        return CaseSearchResult(
            source=self._name,
            query=query.keyword,
            total=1,
            count=1,
            records=[CaseRecord(id="fake_1", source=self._name, title="Fake Title")],
        )

    def get_detail(self, case_id: str, query=None) -> CaseDetail:
        return CaseDetail(id=case_id, source=self._name, title=f"Detail for {case_id}")


def test_gateway_registration_and_search():
    gw = CaseGateway()
    gw.register_provider("fake", FakeProvider("fake", available=True))
    res = gw.search("测试", source="fake")
    assert res.source == "fake"
    assert res.count == 1
    assert res.records[0].title == "Fake Title"


def test_gateway_fallback_on_auth_required():
    gw = CaseGateway()
    gw.register_provider("rmfyalk", FakeProvider("rmfyalk", available=False))
    gw.register_provider("court_guiding", FakeProvider("court_guiding", available=True))

    # When querying rmfyalk without credentials, it gracefully degrades to court_guiding
    res = gw.search("借贷", source="rmfyalk", fallback=True)
    assert res.degraded is True
    assert res.source == "court_guiding"
    assert "已自动为您兜底检索最高法公开指导性案例" in res.warning
    assert res.count == 1


def test_gateway_source_auto_selection():
    gw = CaseGateway()
    gw.register_provider("rmfyalk", FakeProvider("rmfyalk", available=False))
    gw.register_provider("court_guiding", FakeProvider("court_guiding", available=True))

    res = gw.search("著作权", source="auto")
    assert res.source == "court_guiding"
    assert res.degraded is True


def test_gateway_id_auto_detection():
    gw = CaseGateway()
    gw.register_provider("court_guiding", FakeProvider("court_guiding"))
    gw.register_provider("rmfyalk", FakeProvider("rmfyalk"))

    # Guiding case URL
    detail_url = gw.get_detail("https://www.court.gov.cn/shenpan/xiangqing/123.html")
    assert detail_url.source == "court_guiding"

    # Guiding case numeric ID (e.g. 490521)
    detail_num = gw.get_detail("490521")
    assert detail_num.source == "court_guiding"

    # Guiding case title-like ID
    detail_guid = gw.get_detail("指导性案例200号")
    assert detail_guid.source == "court_guiding"

    # GID (44 chars Base64 hash)
    gid = "A" * 43 + "="
    detail_gid = gw.get_detail(gid)
    assert detail_gid.source == "rmfyalk"


def test_gateway_wenshu_auth_failure_fallback():
    gw = CaseGateway()
    gw.register_provider("wenshu", FakeProvider("wenshu", available=False))
    gw.register_provider("court_guiding", FakeProvider("court_guiding", available=True))

    res = gw.search("借贷纠纷", source="wenshu", fallback=True)
    assert res.degraded is True
    assert res.source == "court_guiding"
    assert "已自动为您兜底检索最高法公开指导性案例" in res.warning
