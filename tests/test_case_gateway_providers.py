from unittest.mock import MagicMock, patch
import pytest

from case_gateway.contracts import CaseQuery
from case_gateway.providers.rmfyalk_provider import RmfyalkProvider
from case_gateway.providers.wenshu_provider import WenshuProvider
from case_gateway.providers.court_guiding_provider import CourtGuidingProvider
from case_gateway.errors import AuthenticationRequiredError


def test_rmfyalk_provider_search_success():
    provider = RmfyalkProvider()
    mock_res = {
        "source": "rmfyalk",
        "keyword": "民间借贷",
        "page": 1,
        "size": 10,
        "total": 1,
        "count": 1,
        "records": [
            {
                "gid": "test_gid_1",
                "title": "民间借贷案",
                "case_no": "2024-001",
                "court_case_no": "（2023）最高法民终100号",
                "court": "最高人民法院",
                "judge_date": "2023-11-01",
                "case_type": "民事",
                "key_points": "出借人举证要点",
                "keywords": "借贷;举证",
                "url": "https://rmfyalk.court.gov.cn/view/content.html?id=test_gid_1",
            }
        ],
    }
    with patch("rmfyalk_crawler.search_cases", return_value=mock_res):
        q = CaseQuery(keyword="民间借贷", token="test_token")
        res = provider.search(q)
        assert res.total == 1
        assert res.count == 1
        assert len(res.records) == 1
        rec = res.records[0]
        assert rec.id == "test_gid_1"
        assert rec.title == "民间借贷案"
        assert rec.court_case_no == "（2023）最高法民终100号"
        assert rec.summary == "出借人举证要点"


def test_rmfyalk_provider_auth_error_mapping():
    provider = RmfyalkProvider()
    mock_err = {
        "source": "rmfyalk",
        "total": 0,
        "count": 0,
        "records": [],
        "error": "AUTHENTICATION_REQUIRED",
        "message": "Token is required",
    }
    with patch("rmfyalk_crawler.search_cases", return_value=mock_err):
        q = CaseQuery(keyword="借贷", token=None)
        res = provider.search(q)
        assert res.error == "AUTHENTICATION_REQUIRED"
        assert res.count == 0


def test_wenshu_provider_search_success():
    provider = WenshuProvider()
    mock_res = {
        "source": "wenshu",
        "keyword": "民间借贷",
        "page": 1,
        "size": 10,
        "total": 1,
        "count": 1,
        "records": [
            {
                "doc_id": "test_doc_1",
                "title": "李四诉张三借款合同案",
                "case_no": "（2023）京01民终123号",
                "court": "北京市第一中级人民法院",
                "judge_date": "2023-10-10",
                "case_type": "民事案件",
                "summary": "民间借贷利息裁判规则",
                "url": "https://wenshu.court.gov.cn/test_doc_1",
            }
        ],
    }
    with patch("wenshu_crawler.search_cases", return_value=mock_res):
        q = CaseQuery(keyword="民间借贷", cookie="test_cookie")
        res = provider.search(q)
        assert res.total == 1
        assert res.count == 1
        assert len(res.records) == 1
        rec = res.records[0]
        assert rec.id == "test_doc_1"
        assert rec.title == "李四诉张三借款合同案"
        assert rec.summary == "民间借贷利息裁判规则"


def test_court_guiding_provider_search():
    provider = CourtGuidingProvider()
    mock_html = """
    <html><body><div class="list"><ul>
      <li><a href="/shenpan/xiangqing/500.html" title="指导性案例500号：借款合同案">指导性案例500号：借款合同案</a><i class="date">2024-01-01</i></li>
    </ul></div></body></html>
    """
    mock_resp = MagicMock()
    mock_resp.text = mock_html
    mock_resp.status_code = 200

    with patch("case_gateway.providers.court_guiding_provider.http_request", return_value=mock_resp):
        q = CaseQuery(keyword="借款", no_cache=True)
        res = provider.search(q)
        assert res.count == 1
        assert res.records[0].case_no == "指导性案例500号"
        assert res.records[0].title == "指导性案例500号：借款合同案"
