import json
from pathlib import Path
from common.credentials import clear_credential, get_credential, set_credential


def test_get_credential_from_arg():
    res = get_credential("rmfyalk", token="custom-token-123")
    assert res["token"] == "custom-token-123"


def test_get_credential_from_env(monkeypatch):
    monkeypatch.setenv("RMFYALK_TOKEN", "env-token-456")
    res = get_credential("rmfyalk")
    assert res["token"] == "env-token-456"


def test_get_credential_wenshu_cookie(monkeypatch):
    monkeypatch.setenv("WENSHU_COOKIE", "session_id=abc; wzws_cid=123")
    res = get_credential("wenshu")
    assert res["cookie"] == "session_id=abc; wzws_cid=123"


def test_set_and_clear_credential(tmp_path, monkeypatch):
    test_config_file = tmp_path / "config.json"
    monkeypatch.setattr("common.credentials.CONFIG_FILE", test_config_file)
    monkeypatch.setattr("common.credentials.CONFIG_DIR", tmp_path)

    # Set
    success = set_credential("rmfyalk", token="stored-token-789")
    assert success is True
    assert test_config_file.exists()

    # Read back
    res = get_credential("rmfyalk")
    assert res["token"] == "stored-token-789"

    # Clear
    clear_credential("rmfyalk")
    res2 = get_credential("rmfyalk")
    assert res2["token"] is None


def test_null_config_entries(tmp_path, monkeypatch):
    test_config_file = tmp_path / "config.json"
    monkeypatch.setattr("common.credentials.CONFIG_FILE", test_config_file)
    monkeypatch.setattr("common.credentials.CONFIG_DIR", tmp_path)

    # Write malformed config with null entry
    test_config_file.write_text(json.dumps({"rmfyalk": None, "wenshu": None}), encoding="utf-8")

    # Should not crash with AttributeError
    res = get_credential("rmfyalk")
    assert res["token"] is None
    assert res["cookie"] is None

    # Setting on null entry should not crash with TypeError
    success = set_credential("rmfyalk", token="recovered-token")
    assert success is True
    res2 = get_credential("rmfyalk")
    assert res2["token"] == "recovered-token"

