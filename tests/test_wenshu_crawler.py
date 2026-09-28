import json
import pytest
from unittest.mock import MagicMock, patch

import wenshu_crawler


def test_wenshu_search_no_auth():
    with patch("wenshu_crawler.get_credential", return_value={"token": None, "cookie": None}):
        res = wenshu_crawler.search_cases(keyword="借款合同", token=None, cookie=None, no_cache=True)
        assert res["error"] == "AUTHENTICATION_REQUIRED"
        assert "中国裁判文书网需要用户登录凭证" in res["message"]
        assert res["count"] == 0


def test_wenshu_search_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = json.dumps({
        "result": {
            "total": 1,
            "list": [
                {
                    "DocId": "doc_999",
                    "案件名称": "某银行诉某公司借款纠纷二审判决书",
                    "案号": "（2023）京01民终555号",
                    "审判法院": "北京市第一中级人民法院",
                    "裁判日期": "2023-10-15",
                    "案件类型": "民事案件",
                    "裁判要旨": "金融借款合同中罚息计算标准的认定",
                }
            ],
        }
    })
    mock_response.json.return_value = json.loads(mock_response.text)

    with patch("wenshu_crawler.http_request", return_value=mock_response):
        res = wenshu_crawler.search_cases(
            keyword="借款",
            cookie="session=xyz; token=abc",
            no_cache=True,
        )
        assert res["total"] == 1
        assert res["count"] == 1
        rec = res["records"][0]
        assert rec["doc_id"] == "doc_999"
        assert rec["title"] == "某银行诉某公司借款纠纷二审判决书"
        assert rec["case_no"] == "（2023）京01民终555号"
        assert rec["court"] == "北京市第一中级人民法院"


def test_wenshu_search_waf_blocked():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><head><title>412 WAF Challenge</title></head><body>Verify human</body></html>"

    with patch("wenshu_crawler.http_request", return_value=mock_response):
        res = wenshu_crawler.search_cases(
            keyword="合同",
            cookie="expired_cookie",
            no_cache=True,
        )
        assert res["error"] == "WAF_OR_SESSION_BLOCKED"
        assert "安全网关" in res["message"]


def test_wenshu_detail_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = json.dumps({
        "result": {
            "s1": "某银行诉某公司借款纠纷二审判决书",
            "s7": "（2023）京01民终555号",
            "s2": "北京市第一中级人民法院",
            "s31": "2023-10-15",
            "s8": "民事案件",
            "s23": "判决书全文详细说理内容...",
        }
    })
    mock_response.json.return_value = json.loads(mock_response.text)

    with patch("wenshu_crawler.http_request", return_value=mock_response):
        detail = wenshu_crawler.fetch_case_detail(
            doc_id="doc_999",
            cookie="session=xyz",
            no_cache=True,
        )
        assert detail["doc_id"] == "doc_999"
        assert detail["title"] == "某银行诉某公司借款纠纷二审判决书"
        assert detail["full_text"] == "判决书全文详细说理内容..."


def test_wenshu_des3_crypto_roundtrip():
    key_str = "123456789012345678901234"
    iv_str = "20260928"
    plaintext = '{"queryResult": {"resultCount": 1, "resultList": [{"1": "测试判决", "rowkey": "doc_123"}]}}'

    ciphertext = wenshu_crawler._des3_encrypt(plaintext, key_str, iv_str)
    assert ciphertext
    assert isinstance(ciphertext, str)

    decrypted = wenshu_crawler._des3_decrypt(ciphertext, key_str, iv_str)
    assert decrypted == plaintext


def test_wenshu_generate_ciphertext():
    ct = wenshu_crawler._generate_ciphertext()
    assert ct
    assert isinstance(ct, str)
    assert len(ct) > 16


def test_wenshu_search_encrypted_response():
    key_str = "abcdefghijklmnopqrstuvwx"
    iv_str = wenshu_crawler.datetime.now().strftime("%Y%m%d")
    payload_json = json.dumps({
        "queryResult": {
            "resultCount": 1,
            "resultList": [
                {
                    "rowkey": "doc_enc_1",
                    "1": "加密传输民间借贷案件",
                    "7": "（2024）京01民终888号",
                    "2": "北京市第一中级人民法院",
                    "31": "2024-05-20",
                    "8": "民事案件",
                    "26": "本院认为借贷合意成立...",
                }
            ]
        }
    })
    encrypted_cipher = wenshu_crawler._des3_encrypt(payload_json, key_str, iv_str)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = json.dumps({
        "code": 1,
        "secretKey": key_str,
        "result": encrypted_cipher,
    })
    mock_response.json.return_value = json.loads(mock_response.text)

    with patch("wenshu_crawler.http_request", return_value=mock_response):
        res = wenshu_crawler.search_cases(
            keyword="民间借贷",
            cookie="SESSION=test_session",
            no_cache=True,
        )
        assert res.get("error") is None
        assert res["total"] == 1
        assert len(res["records"]) == 1
        rec = res["records"][0]
        assert rec["doc_id"] == "doc_enc_1"
        assert rec["title"] == "加密传输民间借贷案件"
        assert rec["case_no"] == "（2024）京01民终888号"


def test_wenshu_search_decryption_failure():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = json.dumps({
        "code": 1,
        "secretKey": "bad_key",
        "result": "corrupted_non_base64_ciphertext!@#$",
    })
    mock_response.json.return_value = json.loads(mock_response.text)

    with patch("wenshu_crawler.http_request", return_value=mock_response):
        res = wenshu_crawler.search_cases(
            keyword="民间借贷",
            cookie="SESSION=test_session",
            no_cache=True,
        )
        assert res["error"] == "DECRYPTION_FAILED"
        assert "解密失败" in res["message"]


def test_wenshu_search_court_no_detection():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = json.dumps({"queryResult": {"resultCount": 0, "resultList": []}})
    mock_response.json.return_value = json.loads(mock_response.text)

    with patch("wenshu_crawler.http_request", return_value=mock_response) as mock_http:
        wenshu_crawler.search_cases(
            keyword="（2023）京01民终555号",
            cookie="SESSION=test",
            no_cache=True,
        )
        # Check payload data passed to http_request
        call_kwargs = mock_http.call_args[1]
        data = call_kwargs.get("data", {})
        cond = json.loads(data.get("queryCondition", "[]"))
        assert len(cond) == 1
        assert cond[0]["key"] == "s7"
        assert cond[0]["value"] == "（2023）京01民终555号"


def test_wenshu_detail_invalid_doc_id():
    res = wenshu_crawler.fetch_case_detail(doc_id="", cookie="SESSION=abc")
    assert res["error"] == "INVALID_ARGUMENT"

