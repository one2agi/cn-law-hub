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

import logging

_logger = logging.getLogger("wenshu_crawler")
_cache = get_cache("wenshu-case-db")
_session = None

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
        "User-Agent": DEFAULT_USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/website/wenshu/181217BMTKHNT2W0/index.html",
        "X-Requested-With": "XMLHttpRequest",
    }
    resolved = get_credential("wenshu", token=token, cookie=cookie)
    active_token = resolved.get("token")
    active_cookie = resolved.get("cookie")

    # If cookie is unset but token looks like a cookie string, treat it as cookie
    if not active_cookie and active_token and ("=" in active_token or ";" in active_token):
        active_cookie = active_token

    if active_cookie:
        headers["Cookie"] = active_cookie
    if active_token and active_token != active_cookie:
        if "Bearer " in active_token:
            headers["Authorization"] = active_token
        else:
            headers["Authorization"] = f"Bearer {active_token}"
            headers["RequestVerificationToken"] = active_token

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

    # Build form payload for rest.q4w
    payload = {
        "pageId": uuid.uuid4().hex,
        "s8": "02",
        "sortFields": "s50:desc",
        "ciphertext": "",
        "pageNum": str(page),
        "pageSize": str(size),
        "queryCondition": json.dumps([{"key": "s8", "value": "02"}], ensure_ascii=False),
        "cfg": "com.lawyee.judge.dc.parse.dto.SearchDataDq",
    }
    if keyword:
        payload["queryCondition"] = json.dumps([
            {"key": "qw", "value": keyword}
        ], ensure_ascii=False)

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
    msg = data.get("msg") or data.get("message") or ""
    if code in ("401", "403") or "未登录" in msg:
        return {
            "source": "wenshu",
            "keyword": keyword,
            "total": 0,
            "count": 0,
            "records": [],
            "error": "AUTHENTICATION_FAILED",
            "message": f"裁判文书网凭证已失效（响应信息: {msg or code}）。\n{WENSHU_HELP_MSG}",
        }

    res_field = data.get("result")
    data_field = data.get("data")
    if isinstance(res_field, str) or isinstance(data_field, str):
        return {
            "source": "wenshu",
            "keyword": keyword,
            "total": 0,
            "count": 0,
            "records": [],
            "error": "ENCRYPTED_OR_BLOCKED",
            "message": (
                "裁判文书网返回了密文数据或安全验证拦截，请在浏览器中重新登录并复制有效 Cookie。\n"
                f"{WENSHU_HELP_MSG}"
            ),
        }

    raw_list = []
    if isinstance(res_field, dict):
        raw_list = res_field.get("list") or []
        total = res_field.get("total") or len(raw_list)
    elif isinstance(data_field, dict):
        raw_list = data_field.get("list") or []
        total = data_field.get("total") or len(raw_list)
    elif isinstance(data.get("rows"), list):
        raw_list = data.get("rows")
        total = len(raw_list)
    else:
        total = 0

    records = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        doc_id = item.get("DocId") or item.get("id") or item.get("s0", "")
        title = clean_text(item.get("案件名称") or item.get("s1") or item.get("title", ""))
        case_no = item.get("案号") or item.get("s7") or ""
        court = item.get("审判法院") or item.get("s2") or ""
        judge_date = item.get("裁判日期") or item.get("s31") or ""
        case_type = item.get("案件类型") or item.get("s8") or ""
        reasoning = clean_text(item.get("裁判要旨") or item.get("s26") or "")

        records.append({
            "source": "wenshu",
            "doc_id": doc_id,
            "title": title,
            "case_no": case_no,
            "court": court,
            "judge_date": judge_date,
            "case_type": case_type,
            "summary": reasoning,
            "url": f"{BASE_URL}/website/wenshu/181107ANFZ0HXBR4/index.html?docId={doc_id}" if doc_id else "",
        })

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
        "ciphertext": "",
        "cfg": "com.lawyee.judge.dc.parse.dto.DocInfoDq",
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
        "title": clean_text(raw.get("s1", "")),
        "case_no": raw.get("s7", ""),
        "court": raw.get("s2", ""),
        "judge_date": raw.get("s31", ""),
        "case_type": raw.get("s8", ""),
        "full_text": clean_text(raw.get("s23", "") or raw.get("qwContent", "")),
        "url": f"{BASE_URL}/website/wenshu/181107ANFZ0HXBR4/index.html?docId={clean_id}",
    }

    if not no_cache and record.get("title"):
        _cache.set(cache_key, json.dumps(record, ensure_ascii=False))

    return record
