#!/usr/bin/env python3
"""
Client for China Judgements Online (中国裁判文书网).

Source: https://wenshu.court.gov.cn
Supports configurable authentication credentials (Cookie / Token) passed via:
  --cookie / --token
  WENSHU_COOKIE / WENSHU_TOKEN environment variables
  ~/.config/cn-law-hub/config.json
"""

import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure scripts root is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from common import (
    DEFAULT_USER_AGENT,
    clean_text,
    create_http_session,
    get_cache,
    get_credential,
    http_request,
    setup_logger,
)

BASE_URL = "https://wenshu.court.gov.cn"
SEARCH_API = f"{BASE_URL}/website/parse/rest.q4w"

import base64
import logging
import os
import random
import string
import time
from datetime import datetime

import warnings
from cryptography.utils import CryptographyDeprecationWarning
warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)

_logger = logging.getLogger("wenshu_crawler")
_cache = get_cache("wenshu-case-db")
_session = None

WENSHU_USER_AGENT = os.getenv(
    "WENSHU_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)


def _get_triple_des_alg():
    try:
        from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
        return TripleDES
    except ImportError:
        from cryptography.hazmat.primitives.ciphers import algorithms
        return algorithms.TripleDES


def _des3_encrypt(plain_text: str, key_str: str, iv_str: str) -> str:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, modes
        from cryptography.hazmat.primitives import padding
        alg = _get_triple_des_alg()
        key = key_str.encode("utf-8")
        iv = iv_str.encode("utf-8")
        padder = padding.PKCS7(64).padder()
        padded_data = padder.update(plain_text.encode("utf-8")) + padder.finalize()
        cipher = Cipher(alg(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        ct = encryptor.update(padded_data) + encryptor.finalize()
        return base64.b64encode(ct).decode("utf-8")
    except Exception as e:
        _logger.warning("des3_encrypt failed: %s", e)
        return ""


def _des3_decrypt(cipher_b64: str, key_str: str, iv_str: str) -> str:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, modes
        from cryptography.hazmat.primitives import padding
        alg = _get_triple_des_alg()
        key = key_str.encode("utf-8")
        iv = iv_str.encode("utf-8")
        cipher_bytes = base64.b64decode(cipher_b64)
        cipher = Cipher(alg(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded_plain = decryptor.update(cipher_bytes) + decryptor.finalize()
        unpadder = padding.PKCS7(64).unpadder()
        plain = unpadder.update(padded_plain) + unpadder.finalize()
        return plain.decode("utf-8")
    except Exception as e:
        _logger.warning("des3_decrypt failed: %s", e)
        return ""


def _generate_ciphertext() -> str:
    now = datetime.now()
    timestamp = str(int(time.time() * 1000))
    chars = string.ascii_letters + string.digits
    salt = "".join(random.choice(chars) for _ in range(24))
    iv = now.strftime("%Y%m%d")
    enc = _des3_encrypt(timestamp, salt, iv)
    combined = salt + iv + enc
    return " ".join(bin(ord(c))[2:] for c in combined)


WENSHU_HELP_MSG = (
    "中国裁判文书网需要用户登录凭证（Cookie/Token）。\n"
    "【配置方法】：\n"
    "1. 使用电脑浏览器打开并登录 https://wenshu.court.gov.cn\n"
    "2. 按 F12 打开开发者工具 -> Network（网络）标签页\n"
    "3. 在页面检索并找到任意请求，复制 Request Headers 中的 Cookie 或 Authorization\n"
    "4. 使用以下任意一种方式配置：\n"
    "   - 命令行参数：--cookie \"<您的Cookie>\" 或 --token \"<Token>\"\n"
    "   - 环境变量：export WENSHU_COOKIE=\"<您的Cookie>\" 或 export WENSHU_TOKEN=\"<Token>\"\n"
    "   - 本地持久化：python scripts/case_search.py --set-token wenshu \"<Token/Cookie>\""
)


def _get_session():
    global _session
    if _session is None:
        _session = create_http_session()
    return _session


def _build_headers(
    token: Optional[str] = None,
    cookie: Optional[str] = None,
) -> Dict[str, str]:
    headers = {
        "User-Agent": WENSHU_USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/website/wenshu/181217BMTKHNT2W0/index.html",
        "X-Requested-With": "XMLHttpRequest",
    }
    resolved = get_credential("wenshu", token=token, cookie=cookie)
    active_token = resolved.get("token")
    active_cookie = resolved.get("cookie")

    # If cookie is unset but token looks like a cookie string or UUID, treat as cookie
    if not active_cookie and active_token:
        if "=" in active_token or ";" in active_token:
            active_cookie = active_token
        elif len(active_token) == 36 and "-" in active_token:
            active_cookie = f"SESSION={active_token}"

    if active_cookie:
        if "SESSION=" not in active_cookie and len(active_cookie) == 36 and "-" in active_cookie:
            active_cookie = f"SESSION={active_cookie}"
        headers["Cookie"] = active_cookie
    elif active_token:
        if "Bearer " in active_token:
            headers["Authorization"] = active_token
        elif len(active_token) == 36 and "-" in active_token:
            headers["Cookie"] = f"SESSION={active_token}"
        else:
            headers["Authorization"] = f"Bearer {active_token}"

    return headers


def search_cases(
    keyword: str = "",
    token: Optional[str] = None,
    cookie: Optional[str] = None,
    page: int = 1,
    size: int = 10,
    session=None,
    no_cache: bool = False,
) -> Dict[str, Any]:
    """Search judgements in China Judgements Online.

    Args:
        keyword: Full-text or title search keyword.
        token: Optional explicit auth token.
        cookie: Optional explicit session cookie.
        page: Page index (1-indexed).
        size: Results per page.
        session: Optional requests session.
        no_cache: Bypass cache if True.

    Returns:
        Dict with keys: source, keyword, page, size, total, count, records, error (if any).
    """
    sess = session or _get_session()
    headers = _build_headers(token=token, cookie=cookie)

    has_auth = bool(headers.get("Cookie") or headers.get("Authorization"))
    if not has_auth:
        return {
            "source": "wenshu",
            "keyword": keyword,
            "total": 0,
            "count": 0,
            "records": [],
            "error": "AUTHENTICATION_REQUIRED",
            "message": WENSHU_HELP_MSG,
        }

    cache_key = _cache._key("search", keyword, str(page), str(size))
    if not no_cache:
        cached = _cache.get(cache_key, max_age=3600)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

    # Build form payload for rest.q4w with dynamic ciphertext
    # Wenshu backend requires pageSize to be 5 or 10
    api_size = 5 if size <= 5 else 10
    cond = [{"key": "s1", "value": keyword}] if keyword else []
    payload = {
        "sortFields": "s50:desc",
        "ciphertext": _generate_ciphertext(),
        "pageNum": str(page),
        "pageSize": str(api_size),
        "queryCondition": json.dumps(cond, ensure_ascii=False),
        "cfg": "com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO@queryDoc",
        "wh": "724",
        "ww": "1298",
        "cs": "0",
    }

    try:
        resp = http_request(
            "POST",
            SEARCH_API,
            headers=headers,
            data=payload,
            session=sess,
            timeout=15,
            allowed_statuses=(401, 403, 502),
        )
        # Check if response is HTML (WAF block / redirect)
        resp_text = resp.text.strip()
        if resp_text.startswith("<") or "<html>" in resp_text.lower():
            return {
                "source": "wenshu",
                "keyword": keyword,
                "total": 0,
                "count": 0,
                "records": [],
                "error": "WAF_OR_SESSION_BLOCKED",
                "message": (
                    "裁判文书网安全网关（WAF）拦截了当前请求或凭证已失效（返回了HTML页面而非数据）。\n"
                    "请在浏览器刷新访问 wenshu.court.gov.cn 验证通过后，重新获取最新 Cookie。\n"
                    f"{WENSHU_HELP_MSG}"
                ),
            }

        data = resp.json()
    except Exception as e:
        return {
            "source": "wenshu",
            "keyword": keyword,
            "total": 0,
            "count": 0,
            "records": [],
            "error": f"REQUEST_FAILED: {e}",
        }

    if not isinstance(data, dict):
        return {
            "source": "wenshu",
            "keyword": keyword,
            "total": 0,
            "count": 0,
            "records": [],
            "error": "INVALID_RESPONSE",
            "message": f"裁判文书网返回了非字典响应格式: {type(data).__name__}",
        }

    # Check for authentication or error code in response
    code = str(data.get("code") or data.get("status") or "")
    msg = data.get("msg") or data.get("message") or data.get("description") or ""
    if code in ("401", "403") or "未登录" in msg or "没有权限" in msg:
        return {
            "source": "wenshu",
            "keyword": keyword,
            "total": 0,
            "count": 0,
            "records": [],
            "error": "AUTHENTICATION_FAILED",
            "message": f"裁判文书网凭证已失效或未登录（响应信息: {msg or code}）。\n{WENSHU_HELP_MSG}",
        }

    # Decrypt response if secretKey and result are returned
    if data.get("secretKey") and data.get("result"):
        iv = datetime.now().strftime("%Y%m%d")
        try:
            decrypted_str = _des3_decrypt(data["result"], data["secretKey"], iv)
            data = json.loads(decrypted_str)
        except Exception as e:
            _logger.warning("Failed to decrypt wenshu search response: %s", e)

    raw_list = []
    total = 0
    query_result = data.get("queryResult")
    if isinstance(query_result, dict):
        raw_list = query_result.get("resultList") or []
        total = query_result.get("resultCount") or len(raw_list)
    elif isinstance(data.get("result"), dict):
        res_field = data.get("result")
        raw_list = res_field.get("list") or []
        total = res_field.get("total") or len(raw_list)
    elif isinstance(data.get("data"), dict):
        data_field = data.get("data")
        raw_list = data_field.get("list") or []
        total = data_field.get("total") or len(raw_list)
    elif isinstance(data.get("rows"), list):
        raw_list = data.get("rows")
        total = len(raw_list)

    records = []
    for item in raw_list:
        if isinstance(item, list):
            doc_id = str(item[0]) if len(item) > 0 else ""
            title = clean_text(item[1]) if len(item) > 1 else ""
            court = str(item[2]) if len(item) > 2 else ""
            case_no = str(item[7]) if len(item) > 7 else ""
            case_type = str(item[8]) if len(item) > 8 else ""
            judge_date = str(item[31]) if len(item) > 31 else ""
            reasoning = clean_text(item[26]) if len(item) > 26 else ""
        elif isinstance(item, dict):
            doc_id = item.get("rowkey") or item.get("DocId") or item.get("id") or item.get("s0", "")
            title = clean_text(item.get("1") or item.get("s1") or item.get("案件名称") or item.get("title", ""))
            case_no = item.get("7") or item.get("s7") or item.get("案号") or ""
            court = item.get("2") or item.get("s2") or item.get("审判法院") or ""
            judge_date = item.get("31") or item.get("s31") or item.get("裁判日期") or ""
            case_type = item.get("8") or item.get("s8") or item.get("案件类型") or ""
            reasoning = clean_text(item.get("26") or item.get("s26") or item.get("裁判要旨") or "")
        else:
            continue

        records.append({
            "source": "wenshu",
            "doc_id": doc_id,
            "title": title,
            "case_no": case_no,
            "court": court,
            "judge_date": judge_date,
            "case_type": case_type,
            "summary": reasoning,
            "url": f"{BASE_URL}/website/wenshu/181107ANFZ0BXSK4/index.html?docId={doc_id}" if doc_id else "",
        })

    if size and len(records) > size:
        records = records[:size]

    result = {
        "source": "wenshu",
        "keyword": keyword,
        "page": page,
        "size": size,
        "total": total,
        "count": len(records),
        "records": records,
    }

    if not no_cache and records:
        _cache.set(cache_key, json.dumps(result, ensure_ascii=False))

    return result


def fetch_case_detail(
    doc_id: str,
    token: Optional[str] = None,
    cookie: Optional[str] = None,
    session=None,
    no_cache: bool = False,
) -> Dict[str, Any]:
    """Fetch full text of a judgement by its DocId or URL.

    Args:
        doc_id: Document ID or detail page URL.
        token: Optional explicit token.
        cookie: Optional explicit cookie.
        session: Optional requests session.
        no_cache: Bypass cache if True.

    Returns:
        Dict with full judgement content.
    """
    clean_id = doc_id
    if "docId=" in clean_id:
        m = re.search(r"docId=([a-zA-Z0-9_-]+)", clean_id)
        if m:
            clean_id = m.group(1)

    sess = session or _get_session()
    headers = _build_headers(token=token, cookie=cookie)

    has_auth = bool(headers.get("Cookie") or headers.get("Authorization"))
    if not has_auth:
        return {
            "source": "wenshu",
            "doc_id": clean_id,
            "error": "AUTHENTICATION_REQUIRED",
            "message": WENSHU_HELP_MSG,
        }

    cache_key = _cache._key("detail", clean_id)
    if not no_cache:
        cached = _cache.get(cache_key, max_age=86400)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

    payload = {
        "docId": clean_id,
        "ciphertext": _generate_ciphertext(),
        "cfg": "com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO@docInfoSearch",
    }

    try:
        resp = http_request(
            "POST",
            SEARCH_API,
            headers=headers,
            data=payload,
            session=sess,
            timeout=15,
            allowed_statuses=(401, 403, 502),
        )
        resp_text = resp.text.strip()
        if resp_text.startswith("<") or "<html>" in resp_text.lower():
            return {
                "source": "wenshu",
                "doc_id": clean_id,
                "error": "WAF_OR_SESSION_BLOCKED",
                "message": (
                    "裁判文书网安全网关（WAF）拦截了当前请求或凭证已失效。\n"
                    f"{WENSHU_HELP_MSG}"
                ),
            }
        data = resp.json()
    except Exception as e:
        return {
            "source": "wenshu",
            "doc_id": clean_id,
            "error": f"REQUEST_FAILED: {e}",
        }

    code = data.get("code")
    msg = data.get("msg") or data.get("message") or data.get("description")
    if code in (1, 9, 401, 403) or "没有权限" in str(msg) or "失效" in str(msg) or "请登录" in str(msg):
        return {
            "source": "wenshu",
            "doc_id": clean_id,
            "error": "AUTH_REQUIRED",
            "message": f"裁判文书网凭证已失效或未登录（响应信息: {msg or code}）。\n{WENSHU_HELP_MSG}",
        }

    if isinstance(data, dict) and data.get("secretKey") and data.get("result"):
        iv = datetime.now().strftime("%Y%m%d")
        try:
            decrypted_str = _des3_decrypt(data["result"], data["secretKey"], iv)
            raw = json.loads(decrypted_str)
        except Exception as e:
            _logger.warning("Failed to decrypt wenshu detail: %s", e)
            raw = data.get("result") or data.get("data") or {}
    else:
        raw = data.get("result") or data.get("data") or {}

    if not isinstance(raw, dict):
        return {
            "source": "wenshu",
            "doc_id": clean_id,
            "error": "ENCRYPTED_OR_BLOCKED",
            "message": "裁判文书网返回了密文或拦截信息，请在浏览器中重新登录并复制有效 Cookie。",
        }
    record = {
        "source": "wenshu",
        "doc_id": clean_id,
        "title": clean_text(raw.get("s1") or raw.get("title", "")),
        "case_no": raw.get("s7") or raw.get("case_no", ""),
        "court": raw.get("s2") or raw.get("court", ""),
        "judge_date": raw.get("s31") or raw.get("judge_date", ""),
        "case_type": raw.get("s8") or raw.get("case_type", ""),
        "procedure": raw.get("s9") or raw.get("procedure", ""),
        "key_points": clean_text(raw.get("s26") or raw.get("key_points", "")),
        "facts": clean_text(raw.get("s25") or raw.get("facts", "")),
        "reasoning": clean_text(raw.get("s26") or raw.get("reasoning", "")),
        "ruling": clean_text(raw.get("s27") or raw.get("ruling", "")),
        "full_text": clean_text(raw.get("qwContent") or raw.get("s23") or raw.get("full_text", "")),
        "url": f"{BASE_URL}/website/wenshu/181107ANFZ0BXSK4/index.html?docId={clean_id}",
    }

    if not no_cache and record.get("title"):
        _cache.set(cache_key, json.dumps(record, ensure_ascii=False))

    return record
