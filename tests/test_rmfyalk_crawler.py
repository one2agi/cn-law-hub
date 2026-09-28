import json
import pytest
from unittest.mock import MagicMock, patch

import rmfyalk_crawler


def test_rmfyalk_search_no_token():
    with patch("rmfyalk_crawler.get_credential", return_value={"token": None, "cookie": None}):
        res = rmfyalk_crawler.search_cases(keyword="民间借贷", token=None, no_cache=True)
        assert res["error"] == "AUTHENTICATION_REQUIRED"
        assert "人民法院案例库需要认证凭证" in res["message"]
        assert res["count"] == 0


def test_rmfyalk_search_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": "0",
        "msg": "获取成功！",
        "data": {
            "total": 1,
            "rows": [
                {
                    "gid": "test_gid_101",
                    "title": "张三诉李四民间借贷纠纷案",
                    "cpws_al_no": "2024-08-2-001-001",
                    "cpws_al_ajzh": "（2023）最高法民终888号",
                    "cpws_al_slfy": "最高人民法院",
                    "cpws_al_zs_date": "2023-12-01",
                    "cpws_al_cpyt": "民间借贷中出借人仅依据转账凭证提起诉讼的审查规则",
                    "case_sort_name": "民事",
                    "keyword_cpwsAl": "民间借贷;转账凭证;举证责任",
                    "lib": "参考案例",
                }
            ],
        },
    }

    with patch("rmfyalk_crawler.http_request", return_value=mock_response):
        res = rmfyalk_crawler.search_cases(
            keyword="民间借贷",
            token="mock-valid-token",
            page=1,
            size=10,
            no_cache=True,
        )

        assert res["total"] == 1
        assert res["count"] == 1
        assert len(res["records"]) == 1
        rec = res["records"][0]
        assert rec["gid"] == "test_gid_101"
        assert rec["title"] == "张三诉李四民间借贷纠纷案"
        assert rec["case_no"] == "2024-08-2-001-001"
        assert rec["court"] == "最高人民法院"
        assert "举证责任" in rec["keywords"]


def test_rmfyalk_search_expired_token():
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {
        "code": "401",
        "msg": "未登录",
    }

    with patch("rmfyalk_crawler.http_request", return_value=mock_response):
        res = rmfyalk_crawler.search_cases(
            keyword="保证人",
            token="expired-token",
            no_cache=True,
        )
        assert res["error"] == "TOKEN_EXPIRED_OR_INVALID"
        assert "Token 已过期或无效" in res["message"]


def test_rmfyalk_detail_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": "0",
        "data": {
            "gid": "test_gid_101",
            "title": "张三诉李四民间借贷纠纷案",
            "cpws_al_no": "2024-08-2-001-001",
            "cpws_al_ajzh": "（2023）最高法民终888号",
            "cpws_al_slfy": "最高人民法院",
            "cpws_al_zs_date": "2023-12-01",
            "cpws_al_keyword": "民间借贷;转账凭证",
            "cpws_al_cpyt": "裁判要点内容...",
            "cpws_al_jbaq": "基本案情事实...",
            "cpws_al_cply": "裁判理由说理...",
            "cpws_al_jg": "裁判结果判决...",
        },
    }

    with patch("rmfyalk_crawler.http_request", return_value=mock_response):
        detail = rmfyalk_crawler.fetch_case_detail(
            case_id="test_gid_101",
            token="mock-valid-token",
            no_cache=True,
        )
        assert detail["gid"] == "test_gid_101"
        assert detail["key_points"] == "裁判要点内容..."
        assert detail["facts"] == "基本案情事实..."
        assert detail["reasoning"] == "裁判理由说理..."
        assert detail["ruling"] == "裁判结果判决..."


def test_rmfyalk_search_case_no_advance():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"code": "0", "data": {"total": 0, "rows": []}}

    with patch("rmfyalk_crawler.http_request", return_value=mock_response) as mock_http:
        rmfyalk_crawler.search_cases(
            keyword="2023-07-2-127-001",
            token="mock-token",
            no_cache=True,
        )
        payload = mock_http.call_args[1].get("json", {})
        sp = payload.get("searchParams", {})
        assert sp.get("isAdvSearch") == "1"
        assert sp.get("cpws_al_no") == "2023-07-2-127-001"


def test_rmfyalk_search_court_no_advance():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"code": "0", "data": {"total": 0, "rows": []}}

    with patch("rmfyalk_crawler.http_request", return_value=mock_response) as mock_http:
        rmfyalk_crawler.search_cases(
            keyword="（2021）最高法民终1203号",
            token="mock-token",
            no_cache=True,
        )
        payload = mock_http.call_args[1].get("json", {})
        sp = payload.get("searchParams", {})
        assert sp.get("isAdvSearch") == "1"
        assert sp.get("cpws_al_ajzh") == "（2021）最高法民终1203号"


def test_rmfyalk_detail_resolve_case_no_not_found():
    with patch("rmfyalk_crawler.search_cases", return_value={"records": []}):
        res = rmfyalk_crawler.fetch_case_detail(
            case_id="2024-99-9-999-999",
            token="mock-token",
            no_cache=True,
        )
        assert res["error"] == "CASE_NOT_FOUND"
        assert "未在人民法院案例库中找到案号" in res["message"]


def test_rmfyalk_detail_empty_case_id():
    res = rmfyalk_crawler.fetch_case_detail(case_id="", token="mock-token")
    assert res["error"] == "INVALID_ARGUMENT"

