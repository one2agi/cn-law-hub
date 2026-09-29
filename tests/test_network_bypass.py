"""Tests for network self-healing upon ProxyError."""

from unittest import mock
import pytest
import requests

from scripts.common.ratelimit import http_request


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


def test_proxy_error_exhaustion_raises():
    """Verify that continuous ProxyError eventually raises RuntimeError after retries."""
    with mock.patch("requests.request", side_effect=requests.exceptions.ProxyError("Dead proxy")):
        with pytest.raises(RuntimeError) as exc_info:
            http_request("GET", "https://example.com/api", proxies={"http": "http://bad-proxy:8080"})
        assert "Proxy connection failed" in str(exc_info.value)
