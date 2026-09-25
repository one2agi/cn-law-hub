"""Tests for network self-healing and proxy bypass for domestic government sites."""

import os
from unittest import mock
import pytest
import requests

from scripts.common.ratelimit import (
    is_domestic_gov_domain,
    http_request,
)


def test_is_domestic_gov_domain():
    assert is_domestic_gov_domain("https://flk.npc.gov.cn/law-search/download/pc") is True
    assert is_domestic_gov_domain("https://www.gov.cn/zhengce/index.htm") is True
    assert is_domestic_gov_domain("http://court.gov.cn/fabu.html") is True
    assert is_domestic_gov_domain("https://12371.cn/special/dnfg/index.shtml") is True
    assert is_domestic_gov_domain("https://chinatax.gov.cn/n810341/index.html") is True
    assert is_domestic_gov_domain("https://github.com/ZongziForu/cn-law-hub") is False
    assert is_domestic_gov_domain("https://example.com/test") is False


def test_proxy_bypass_for_gov_domain():
    """Verify domestic gov domains automatically bypass proxy when not explicitly configured."""
    with mock.patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:9999", "HTTPS_PROXY": "http://127.0.0.1:9999"}):
        with mock.patch("requests.request") as mock_req:
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_req.return_value = mock_resp

            resp = http_request("GET", "https://flk.npc.gov.cn/detail?id=123")
            assert resp.status_code == 200

            call_kwargs = mock_req.call_args.kwargs
            assert "proxies" in call_kwargs
            assert call_kwargs["proxies"]["http"] is None
            assert call_kwargs["proxies"]["https"] is None
            assert call_kwargs["proxies"]["all"] is None


def test_proxy_error_self_healing():
    """Verify that a ProxyError triggers automatic retry with direct connection."""
    with mock.patch("requests.request") as mock_req:
        mock_success = mock.MagicMock()
        mock_success.status_code = 200

        # First call raises ProxyError, second call succeeds
        mock_req.side_effect = [
            requests.exceptions.ProxyError("Cannot connect to proxy 127.0.0.1:8045"),
            mock_success,
        ]

        resp = http_request("GET", "https://example.com/api", proxies={"http": "http://127.0.0.1:8045"})
        assert resp.status_code == 200
        assert mock_req.call_count == 2
        # The second call must have fallen back to proxies={"http": None, "https": None, "all": None}
        fallback_kwargs = mock_req.call_args.kwargs
        assert fallback_kwargs["proxies"]["http"] is None
        assert fallback_kwargs["proxies"]["https"] is None
        assert fallback_kwargs["proxies"]["all"] is None

