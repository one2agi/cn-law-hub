#!/usr/bin/env python3
"""
Crawler and client for People's Court Case Database (人民法院案例库).

Source: https://rmfyalk.court.gov.cn
Requires authentication token ('faxin-cpws-al-token') passed via --token,
RMFYALK_TOKEN environment variable, or stored in ~/.config/cn-law-hub/config.json.
"""

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure scripts root is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from common import (
    DEFAULT_USER_AGENT,
    clean_text,
    create_http_session,
    ensure_dir,
    get_cache,
    get_credential,
    http_request,
    sanitize_filename,
    setup_logger,
    write_json,
    write_text,
)

BASE_URL = "https://rmfyalk.court.gov.cn"
SEARCH_API = f"{BASE_URL}/cpws_al_api/api/cpwsAl/search"
CONTENT_API = f"{BASE_URL}/cpws_al_api/api/cpwsAl/content"

import logging

_logger = logging.getLogger("rmfyalk_crawler")
_cache = get_cache("rmfyalk-case-db")
_session = None

TOKEN_HELP_MSG = (
    "人民法院案例库需要认证凭证（Token）。\n"
    "【获取方法】：\n"
    "1. 登录 https://rmfyalk.court.gov.cn\n"
    "2. 按 F12 打开控制台（Console），粘贴运行：\n"
    "   fetch('/cpws_al_api/api/user/getUserInfo',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})\n"
    "     .then(r=>r.json()).then(d=>console.log(d.data.alUser.userToken));\n"
    "3. 使用以下任意一种方式配置：\n"
    "   - 命令行参数：--token <Token>\n"
    "   - 环境变量：export RMFYALK_TOKEN=\"<Token>\"\n"
    "   - 本地持久化：python scripts/case_search.py --set-token rmfyalk <Token>"
)


def _get_session():
    global _session
    if _session is None:
        _session = create_http_session()
    return _session


def _build_headers(token: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/view/list.html",
    }
    resolved_cred = get_credential("rmfyalk", token=token)
    active_token = resolved_cred.get("token")
    if active_token:
        headers["faxin-cpws-al-token"] = active_token
    if resolved_cred.get("cookie"):
        headers["Cookie"] = resolved_cred["cookie"]
    return headers


def search_cases(
    keyword: str = "",
    token: Optional[str] = None,
    page: int = 1,
    size: int = 10,
    lib: str = "cpwsAl_qb",
    session=None,
    no_cache: bool = False,
) -> Dict[str, Any]:
    """Search cases in the People's Court Case Database.

    Args:
        keyword: Search keyword (searches full text).
        token: Optional explicit token.
        page: Page number (1-indexed).
        size: Results per page.
        lib: Case category: 'cpwsAl_qb' (全部), 'cpwsAl_01' (指导性案例), 'cpwsAl_02' (参考案例).
        session: Optional requests session.
        no_cache: Bypass local cache if True.

    Returns:
        Dict with keys: source, keyword, page, size, total, count, records, error (if any).
    """
    sess = session or _get_session()
    headers = _build_headers(token=token)

    if "faxin-cpws-al-token" not in headers:
        return {
            "source": "rmfyalk",
            "keyword": keyword,
            "total": 0,
            "count": 0,
            "records": [],
            "error": "AUTHENTICATION_REQUIRED",
            "message": TOKEN_HELP_MSG,
        }

    cache_key = _cache._key("search", keyword, str(page), str(size), lib)
    if not no_cache:
        cached = _cache.get(cache_key, max_age=3600)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

    kw_clean = keyword.strip() if keyword else ""
    is_case_no = bool(re.match(r"^\d{4}(-\d+)+$", kw_clean))
    is_court_no = "号" in kw_clean and any(c in kw_clean for c in ["（", "）", "(", ")", "民", "刑", "行", "执", "再", "终", "初"])

    if is_case_no:
        search_params = {
            "userSearchType": 1,
            "isAdvSearch": "1",
            "lib": lib,
            "sort_field": "",
            "cpws_al_no": kw_clean,
        }
    elif is_court_no:
        search_params = {
            "userSearchType": 1,
            "isAdvSearch": "1",
            "lib": lib,
            "sort_field": "",
            "cpws_al_ajzh": kw_clean,
        }
    else:
        search_params = {
            "userSearchType": 1,
            "isAdvSearch": "0",
            "selectValue": ["qw"],
            "lib": lib,
            "sort_field": "",
            "keyTitle": [kw_clean] if kw_clean else [],
        }

    payload = {
        "page": page,
        "size": size,
        "lib": "qb",
        "searchParams": search_params,
    }

    try:
        resp = http_request(
            "POST",
            SEARCH_API,
            headers=headers,
            json=payload,
            session=sess,
            timeout=15,
            allowed_statuses=(401, 403),
        )
        data = resp.json()
    except Exception as e:
        err_str = str(e)
        if "401" in err_str:
            return {
                "source": "rmfyalk",
                "keyword": keyword,
                "total": 0,
                "count": 0,
                "records": [],
                "error": "TOKEN_EXPIRED_OR_INVALID",
                "message": f"Token 已过期或无效。\n{TOKEN_HELP_MSG}",
            }
        return {
            "source": "rmfyalk",
            "keyword": keyword,
            "total": 0,
            "count": 0,
            "records": [],
            "error": f"REQUEST_FAILED: {e}",
        }

    # Handle unauthenticated / expired token response
    code = str(data.get("code", ""))
    msg = data.get("msg", "")
    if code == "401" or "未登录" in msg:
        return {
            "source": "rmfyalk",
            "keyword": keyword,
            "total": 0,
            "count": 0,
            "records": [],
            "error": "TOKEN_EXPIRED_OR_INVALID",
            "message": f"Token 已过期或无效（接口响应：{msg}）。\n{TOKEN_HELP_MSG}",
        }

    if code != "0" and code != "200":
        return {
            "source": "rmfyalk",
            "keyword": keyword,
            "total": 0,
            "count": 0,
            "records": [],
            "error": f"API_ERROR: {msg} (code: {code})",
        }

    res_data = data.get("data") or {}
    total = res_data.get("totalCount") or res_data.get("total") or 0
    raw_rows = res_data.get("datas") or res_data.get("rows") or []

    records = []
    for row in raw_rows:
        raw_id = row.get("id") or row.get("cpws_al_id") or row.get("gid", "")
        gid = urllib.parse.unquote(str(raw_id)) if raw_id else ""
        quoted_id = urllib.parse.quote(gid) if gid else ""
        title = clean_text(row.get("cpws_al_title") or row.get("title", ""))
        case_no = row.get("cpws_al_no", "")
        court_case_no = row.get("cpws_al_ajzh", "")
        court = row.get("cpws_al_slfy_name") or row.get("cpws_al_sf") or row.get("cpws_al_slfy", "")
        judge_date = row.get("cpws_al_zs_date", "")
        case_type = row.get("cpws_al_case_sort_name") or row.get("case_sort_name", "")
        raw_kw = row.get("cpws_al_keyword") or row.get("keyword_cpwsAl", "")
        keywords = ", ".join(raw_kw) if isinstance(raw_kw, list) else str(raw_kw)
        key_points = clean_text(row.get("cpws_al_cpyz") or row.get("cpws_al_cpyt", ""))
        lib_type = row.get("lib", "参考案例")
        detail_url = f"{BASE_URL}/view/content.html?id={quoted_id}&lib={lib}" if quoted_id else ""
        records.append({
            "source": "rmfyalk",
            "gid": gid,
            "title": title,
            "case_no": case_no,
            "court_case_no": court_case_no,
            "court": court,
            "judge_date": judge_date,
            "case_type": case_type,
            "keywords": keywords,
            "key_points": key_points,
            "lib_type": lib_type,
            "url": detail_url,
        })

    if not records and " " in keyword.strip():
        primary_kw = keyword.strip().split()[0]
        if primary_kw and primary_kw != keyword.strip():
            fallback_res = search_cases(
                keyword=primary_kw,
                token=token,
                page=page,
                size=size,
                lib=lib,
                session=sess,
                no_cache=no_cache,
            )
            if fallback_res.get("records"):
                fallback_res["keyword"] = keyword
                return fallback_res

    result = {
        "source": "rmfyalk",
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
    case_id: str,
    token: Optional[str] = None,
    session=None,
    no_cache: bool = False,
) -> Dict[str, Any]:
    """Fetch full case content by case GID or URL.

    Args:
        case_id: Case GID (e.g. '12345') or content page URL.
        token: Optional explicit token.
        session: Optional requests session.
        no_cache: Bypass cache if True.

    Returns:
        Dict with full case metadata and text sections.
    """
    raw_case_id = str(case_id).strip()
    gid = urllib.parse.unquote(raw_case_id)
    if "id=" in gid:
        parsed = urllib.parse.urlparse(gid)
        q = urllib.parse.parse_qs(parsed.query)
        if "id" in q:
            gid = urllib.parse.unquote(q["id"][0])

    # If gid is not a 44-character Base64 hash (e.g. is an in-library case_no or court case number)
    if not (len(gid) == 44 and gid.endswith("=")) and ("-" in gid or "号" in gid):
        search_res = search_cases(
            keyword=gid,
            token=token,
            session=session,
            no_cache=no_cache,
            size=1,
        )
        if search_res.get("records"):
            gid = search_res["records"][0]["gid"]

    sess = session or _get_session()
    headers = _build_headers(token=token)

    if "faxin-cpws-al-token" not in headers:
        return {
            "source": "rmfyalk",
            "gid": gid,
            "error": "AUTHENTICATION_REQUIRED",
            "message": TOKEN_HELP_MSG,
        }

    cache_key = _cache._key("detail", gid)
    if not no_cache:
        cached = _cache.get(cache_key, max_age=86400)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

    try:
        resp = http_request(
            "POST",
            CONTENT_API,
            headers=headers,
            json={"gid": gid},
            session=sess,
            timeout=15,
            allowed_statuses=(401, 403),
        )
        data = resp.json()
    except Exception as e:
        err_str = str(e)
        if "401" in err_str:
            return {
                "source": "rmfyalk",
                "gid": gid,
                "error": "TOKEN_EXPIRED_OR_INVALID",
                "message": f"Token 已过期或无效。\n{TOKEN_HELP_MSG}",
            }
        return {
            "source": "rmfyalk",
            "gid": gid,
            "error": f"REQUEST_FAILED: {e}",
        }

    code = str(data.get("code", ""))
    msg = data.get("msg", "")
    if code == "401" or "未登录" in msg:
        return {
            "source": "rmfyalk",
            "gid": gid,
            "error": "TOKEN_EXPIRED_OR_INVALID",
            "message": f"Token 已过期或无效（接口响应：{msg}）。\n{TOKEN_HELP_MSG}",
        }

    if code != "0" and code != "200":
        return {
            "source": "rmfyalk",
            "gid": gid,
            "error": f"API_ERROR: {msg} (code: {code})",
        }

    raw_data = data.get("data") or {}
    d = raw_data.get("data") if isinstance(raw_data, dict) and isinstance(raw_data.get("data"), dict) else raw_data
    record = {
        "source": "rmfyalk",
        "gid": gid,
        "title": clean_text(d.get("cpws_al_title") or d.get("title", "")),
        "case_no": d.get("cpws_al_no", ""),
        "court_case_no": d.get("cpws_al_ajzh", ""),
        "court": d.get("cpws_al_slfy_name") or d.get("cpws_al_sf") or d.get("cpws_al_slfy", ""),
        "judge_date": d.get("cpws_al_zs_date", ""),
        "keywords": ", ".join(d.get("cpws_al_keyword")) if isinstance(d.get("cpws_al_keyword"), list) else (d.get("cpws_al_keyword") or d.get("keyword_cpwsAl", "")),
        "procedure": d.get("cpws_al_slcx_name") or d.get("cpws_al_cpxz", ""),
        "key_points": clean_text(d.get("cpws_al_cpyz") or d.get("cpws_al_cpyt", "")),
        "facts": clean_text(d.get("cpws_al_jbaq", "")),
        "reasoning": clean_text(d.get("cpws_al_cply", "")),
        "ruling": clean_text(d.get("cpws_al_cpjg") or d.get("cpws_al_jg", "")),
        "related_laws": clean_text(d.get("cpws_al_glsy", "")),
        "url": f"{BASE_URL}/view/content.html?id={gid}",
    }

    if not no_cache:
        _cache.set(cache_key, json.dumps(record, ensure_ascii=False))

    return record
