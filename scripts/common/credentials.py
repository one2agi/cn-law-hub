"""Credential and token management for cn-law-hub data sources."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path.home() / ".config" / "cn-law-hub"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _read_config() -> Dict[str, Any]:
    """Read the credentials configuration file safely."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_config(config: Dict[str, Any]) -> bool:
    """Save the credentials configuration file safely."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_credential(
    source: str,
    token: Optional[str] = None,
    cookie: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Resolve credentials for a given data source.

    Precedence order:
      1. Explicit arguments (token, cookie)
      2. Environment variables (e.g. RMFYALK_TOKEN, WENSHU_TOKEN, WENSHU_COOKIE)
      3. Local config file (~/.config/cn-law-hub/config.json)

    Args:
        source: Data source key ('rmfyalk', 'wenshu', etc.)
        token: Optional explicit token passed at call time.
        cookie: Optional explicit cookie string.

    Returns:
        Dict with keys 'token' and 'cookie'.
    """
    source = source.lower().strip()
    config = _read_config().get(source, {})

    resolved_token = token
    resolved_cookie = cookie

    if source == "rmfyalk":
        if not resolved_token:
            resolved_token = (
                os.getenv("RMFYALK_TOKEN")
                or os.getenv("CN_LAW_RMFYALK_TOKEN")
                or config.get("token")
            )
        if not resolved_cookie:
            resolved_cookie = os.getenv("RMFYALK_COOKIE") or config.get("cookie")

    elif source == "wenshu":
        if not resolved_token:
            resolved_token = (
                os.getenv("WENSHU_TOKEN")
                or os.getenv("CN_LAW_WENSHU_TOKEN")
                or config.get("token")
            )
        if not resolved_cookie:
            resolved_cookie = (
                os.getenv("WENSHU_COOKIE")
                or os.getenv("CN_LAW_WENSHU_COOKIE")
                or config.get("cookie")
            )

    else:
        # Generic source resolution
        if not resolved_token:
            prefix = source.upper()
            resolved_token = os.getenv(f"{prefix}_TOKEN") or config.get("token")
        if not resolved_cookie:
            prefix = source.upper()
            resolved_cookie = os.getenv(f"{prefix}_COOKIE") or config.get("cookie")

    return {
        "token": resolved_token.strip() if resolved_token else None,
        "cookie": resolved_cookie.strip() if resolved_cookie else None,
    }


def set_credential(
    source: str,
    token: Optional[str] = None,
    cookie: Optional[str] = None,
) -> bool:
    """Store credentials for a data source into the local config file.

    Args:
        source: Data source key ('rmfyalk', 'wenshu', etc.)
        token: Token string to store.
        cookie: Cookie string to store.

    Returns:
        True if successfully written, False otherwise.
    """
    source = source.lower().strip()
    config = _read_config()
    current = config.get(source, {})

    if token is not None:
        if token.strip():
            current["token"] = token.strip()
        else:
            current.pop("token", None)

    if cookie is not None:
        if cookie.strip():
            current["cookie"] = cookie.strip()
        else:
            current.pop("cookie", None)

    config[source] = current
    return _write_config(config)


def clear_credential(source: str) -> bool:
    """Clear stored credentials for a data source."""
    source = source.lower().strip()
    config = _read_config()
    if source in config:
        del config[source]
        return _write_config(config)
    return True
