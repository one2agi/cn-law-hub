import json
from unittest.mock import MagicMock, patch
import pytest

import case_search


def test_case_search_router_court_guiding():
    mock_html = """
    <html>
      <body>
        <div class="list">
          <ul>
            <li>
              <a href="/shenpan/xiangqing/123.html" title="指导性案例200号：某某纠纷案">指导性案例200号：某某纠纷案</a>
              <i class="date">2024-05-01</i>
            </li>
          </ul>
        </div>
      </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = mock_html

    with patch("case_search.http_request", return_value=mock_resp):
        res = case_search.search_cases(
            source="court_guiding",
            keyword="纠纷",
            no_cache=True,
        )
        assert res["source"] == "court_guiding"
        assert res["count"] == 1
        rec = res["records"][0]
        assert "指导性案例200号" in rec["case_no"]
        assert "指导性案例200号：某某纠纷案" in rec["title"]
        assert rec["judge_date"] == "2024-05-01"


def test_case_search_router_invalid_source():
    res = case_search.search_cases(source="invalid_source", keyword="test")
    assert res["error"] == "UNKNOWN_SOURCE"
    assert "不支持的案例库来源" in res["message"]


def test_case_search_court_guiding_detail():
    mock_html = """
    <html>
      <body>
        <h2>指导性案例200号：某某纠纷案 - 中华人民共和国最高人民法院</h2>
        <div class="txt_txt">
          指导性案例200号
          【裁判要点】
          这是裁判要点文本。
          【基本案情】
          这是基本案情文本。
          【裁判理由】
          这是裁判理由文本。
        </div>
      </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = mock_html

    with patch("case_search.http_request", return_value=mock_resp):
        detail = case_search.get_case_detail(
            source="court_guiding",
            case_id="123",
            no_cache=True,
        )
        assert detail["title"] == "指导性案例200号：某某纠纷案"
        assert detail["key_points"] == "这是裁判要点文本。"
        assert detail["facts"] == "这是基本案情文本。"
        assert detail["reasoning"] == "这是裁判理由文本。"


def test_case_search_court_guiding_ssrf_protection():
    # Attempting to fetch internal or non-court URLs should be blocked immediately
    res1 = case_search.fetch_court_guiding_detail("http://127.0.0.1:8000/internal-secrets")
    assert res1["error"].startswith("INVALID_URL")

    res2 = case_search.fetch_court_guiding_detail("https://attacker.example.com/exploit")
    assert res2["error"].startswith("INVALID_URL")


def test_case_search_court_guiding_cai_pan_yao_zhi():
    mock_html = """
    <html>
      <body>
        <h2>指导性案例201号：合同要旨案</h2>
        <div class="txt_txt">
          【裁判要旨】
          裁判要旨内容说明。
          【基本案情】
          案情内容。
        </div>
      </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = mock_html

    with patch("case_search.http_request", return_value=mock_resp):
        detail = case_search.fetch_court_guiding_detail("https://www.court.gov.cn/shenpan/xiangqing/201.html")
        assert detail["key_points"] == "裁判要旨内容说明。"
        assert detail["facts"] == "案情内容。"


def test_case_search_router_backward_compatibility():
    with patch("case_search._gateway.search") as mock_gw_search:
        from case_gateway.contracts import CaseSearchResult, CaseRecord
        mock_gw_search.return_value = CaseSearchResult(
            source="rmfyalk",
            query="借贷",
            page=1,
            size=10,
            total=1,
            count=1,
            records=[CaseRecord(id="g1", source="rmfyalk", title="借贷案", case_no="2024-1")],
        )
        res = case_search.search_cases(source="rmfyalk", keyword="借贷")
        assert res["source"] == "rmfyalk"
        assert res["keyword"] == "借贷"
        assert res["count"] == 1
        assert res["records"][0]["gid"] == "g1"
        assert res["records"][0]["title"] == "借贷案"


def test_case_detail_router_backward_compatibility():
    with patch("case_search._gateway.get_detail") as mock_gw_detail:
        from case_gateway.contracts import CaseDetail
        mock_gw_detail.return_value = CaseDetail(
            id="g1",
            source="rmfyalk",
            title="借贷案详情",
            key_points="要点",
        )
        res = case_search.get_case_detail(source="rmfyalk", case_id="g1")
        assert res["gid"] == "g1"
        assert res["title"] == "借贷案详情"
        assert res["key_points"] == "要点"

