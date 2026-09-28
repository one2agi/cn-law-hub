#!/usr/bin/env python3
"""
Unified Case Search CLI and Router for cn-law-hub.

Supported Sources:
  - rmfyalk: 人民法院案例库 (https://rmfyalk.court.gov.cn) - 需要认证凭证 (Token)
  - wenshu: 中国裁判文书网 (https://wenshu.court.gov.cn) - 可配置凭证 (Token/Cookie)
  - court_guiding: 最高人民法院指导性案例 (https://www.court.gov.cn/shenpan/gengduo/77.html) - 免密公开

Usage:
  # 检索人民法院案例库 (需Token)
  python case_search.py --source rmfyalk --search "民间借贷" --token "xxx"
  
  # 保存 Token 到本地持久化配置
  python case_search.py --set-token rmfyalk "xxx"
  python case_search.py --set-token wenshu "xxx"

  # 检索最高法指导性案例 (免密)
  python case_search.py --source court_guiding --search "著作权" --size 5

  # 获取案例详情
  python case_search.py --source rmfyalk --info "12345"
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

# Ensure scripts root is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import rmfyalk_crawler
import wenshu_crawler
from common import (
    DEFAULT_USER_AGENT,
    clean_text,
    clear_credential,
    create_crawler_headers,
    create_http_session,
    ensure_dir,
    get_cache,
    get_credential,
    http_request,
    set_credential,
    setup_logger,
    write_json,
    write_text,
)

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

import logging

_logger = logging.getLogger("case_search")
_cache = get_cache("court-guiding-case-db")
_session = None

COURT_BASE_URL = "https://www.court.gov.cn"


def _get_session():
    global _session
    if _session is None:
        _session = create_http_session()
    return _session


# ---------------------------------------------------------------------------
# court_guiding (最高法公开指导性案例 - 免密)
# ---------------------------------------------------------------------------


def fetch_court_guiding_cases(
    keyword: str = "",
    page: int = 1,
    size: int = 10,
    no_cache: bool = False,
) -> Dict[str, Any]:
    """Fetch Supreme People's Court Guiding Cases (court.gov.cn/shenpan/gengduo/77.html)."""
    if BeautifulSoup is None:
        return {
            "source": "court_guiding",
            "keyword": keyword,
            "total": 0,
            "count": 0,
            "records": [],
            "error": "MISSING_DEPENDENCY: please run 'pip install beautifulsoup4'",
        }

    sess = _get_session()
    headers = create_crawler_headers()
    cache_key = _cache._key("guiding_list", str(page))

    html = None
    if not no_cache:
        cached = _cache.get(cache_key, max_age=86400)
        if cached:
            html = cached

    if not html:
        url = (
            f"{COURT_BASE_URL}/shenpan/gengduo/77.html"
            if page == 1
            else f"{COURT_BASE_URL}/shenpan/gengduo/77_{page}.html"
        )
        try:
            resp = http_request("GET", url, headers=headers, session=sess, timeout=15)
            resp.encoding = "utf-8"
            html = resp.text
            if not no_cache:
                _cache.set(cache_key, html)
        except Exception as e:
            return {
                "source": "court_guiding",
                "keyword": keyword,
                "total": 0,
                "count": 0,
                "records": [],
                "error": f"REQUEST_FAILED: {e}",
            }

    soup = BeautifulSoup(html, "html.parser")
    records = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/shenpan/xiangqing/" not in href:
            continue
        title = clean_text(a.get("title") or a.get_text(" ", strip=True))
        if not title or len(title) < 5:
            continue

        full_url = urljoin(COURT_BASE_URL, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # Extract date from adjacent <i> or sibling
        date_str = ""
        parent = a.parent
        if parent:
            i_tag = parent.find("i", class_="date")
            if i_tag:
                date_str = clean_text(i_tag.get_text())

        # Filter by keyword if provided
        if keyword and keyword.lower() not in title.lower():
            continue

        # Extract guiding case number if present (e.g. 指导性案例279号)
        m = re.search(r"指导(?:性)?案例\s*(\d+)号", title)
        case_no = f"指导性案例{m.group(1)}号" if m else ""

        records.append({
            "source": "court_guiding",
            "title": title,
            "case_no": case_no,
            "court": "最高人民法院",
            "judge_date": date_str,
            "case_type": "指导性案例",
            "url": full_url,
        })

    # Slice page size
    sliced_records = records[:size]

    return {
        "source": "court_guiding",
        "keyword": keyword,
        "page": page,
        "size": size,
        "total": len(records),
        "count": len(sliced_records),
        "records": sliced_records,
    }


def fetch_court_guiding_detail(url_or_id: str, no_cache: bool = False) -> Dict[str, Any]:
    """Fetch full text of a Supreme Court Guiding Case from court.gov.cn."""
    if BeautifulSoup is None:
        return {"error": "MISSING_DEPENDENCY: please run 'pip install beautifulsoup4'"}

    full_url = url_or_id
    if not full_url.startswith("http"):
        full_url = f"{COURT_BASE_URL}/shenpan/xiangqing/{url_or_id}.html"

    cache_key = _cache._key("guiding_detail", full_url)
    if not no_cache:
        cached = _cache.get(cache_key, max_age=86400 * 7)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

    sess = _get_session()
    headers = create_crawler_headers()
    try:
        resp = http_request("GET", full_url, headers=headers, session=sess, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        return {"error": f"REQUEST_FAILED: {e}"}

    title_tag = soup.find("h2") or soup.find("title")
    title = clean_text(title_tag.get_text()) if title_tag else ""
    title = re.sub(r"\s*-\s*中华人民共和国最高人民法院.*$", "", title)

    body_tag = soup.find(class_="txt_txt") or soup.find(class_="txt")
    full_text = clean_text(body_tag.get_text("\n")) if body_tag else ""

    # Parse common sections
    key_points = ""
    facts = ""
    reasoning = ""

    if "【裁判要点】" in full_text:
        parts = re.split(r"【(裁判要点|基本案情|裁判理由|相关法条)】", full_text)
        # parts structure: [preamble, '裁判要点', text, '基本案情', text, ...]
        for i in range(1, len(parts), 2):
            tag = parts[i]
            val = clean_text(parts[i + 1]) if i + 1 < len(parts) else ""
            if tag == "裁判要点":
                key_points = val
            elif tag == "基本案情":
                facts = val
            elif tag == "裁判理由":
                reasoning = val

    record = {
        "source": "court_guiding",
        "title": title,
        "url": full_url,
        "key_points": key_points,
        "facts": facts,
        "reasoning": reasoning,
        "full_text": full_text,
    }

    if not no_cache:
        _cache.set(cache_key, json.dumps(record, ensure_ascii=False))

    return record


# ---------------------------------------------------------------------------
# Unified Router Functions
# ---------------------------------------------------------------------------


def search_cases(
    source: str = "rmfyalk",
    keyword: str = "",
    token: Optional[str] = None,
    cookie: Optional[str] = None,
    page: int = 1,
    size: int = 10,
    lib: str = "cpwsAl_qb",
    no_cache: bool = False,
) -> Dict[str, Any]:
    """Unified case search router across all supported sources.

    Args:
        source: 'rmfyalk' (人民法院案例库), 'wenshu' (中国裁判文书网), 'court_guiding' (最高法指导案例).
        keyword: Search query.
        token: Optional explicit token.
        cookie: Optional explicit cookie.
        page: Page number (1-indexed).
        size: Result limit.
        lib: Case category filter for rmfyalk.
        no_cache: Bypass cache.
    """
    src = source.lower().strip()
    if src in ("rmfyalk", "case_db", "al", "alk"):
        return rmfyalk_crawler.search_cases(
            keyword=keyword,
            token=token,
            page=page,
            size=size,
            lib=lib,
            no_cache=no_cache,
        )
    elif src in ("wenshu", "cpws", "judgements"):
        return wenshu_crawler.search_cases(
            keyword=keyword,
            token=token,
            cookie=cookie,
            page=page,
            size=size,
            no_cache=no_cache,
        )
    elif src in ("court_guiding", "guiding", "zdxal"):
        return fetch_court_guiding_cases(
            keyword=keyword,
            page=page,
            size=size,
            no_cache=no_cache,
        )
    else:
        return {
            "source": source,
            "error": "UNKNOWN_SOURCE",
            "message": f"不支持的案例库来源: '{source}'. 支持的选项: rmfyalk (人民法院案例库), wenshu (中国裁判文书网), court_guiding (最高法指导案例)",
            "records": [],
            "count": 0,
        }


def get_case_detail(
    source: str = "rmfyalk",
    case_id: str = "",
    token: Optional[str] = None,
    cookie: Optional[str] = None,
    no_cache: bool = False,
) -> Dict[str, Any]:
    """Unified case detail router."""
    src = source.lower().strip()
    if src in ("rmfyalk", "case_db", "al", "alk"):
        return rmfyalk_crawler.fetch_case_detail(
            case_id=case_id,
            token=token,
            no_cache=no_cache,
        )
    elif src in ("wenshu", "cpws", "judgements"):
        return wenshu_crawler.fetch_case_detail(
            doc_id=case_id,
            token=token,
            cookie=cookie,
            no_cache=no_cache,
        )
    elif src in ("court_guiding", "guiding", "zdxal"):
        return fetch_court_guiding_detail(
            url_or_id=case_id,
            no_cache=no_cache,
        )
    else:
        return {
            "error": "UNKNOWN_SOURCE",
            "message": f"不支持的案例库来源: '{source}'.",
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Unified Case Search CLI (人民法院案例库、中国裁判文书网、最高法指导案例)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        choices=["rmfyalk", "wenshu", "court_guiding"],
        default="rmfyalk",
        help="案例数据源: rmfyalk (人民法院案例库), wenshu (中国裁判文书网), court_guiding (最高法指导案例)",
    )
    parser.add_argument("-s", "--search", help="检索关键词（如'民间借贷'、'保证人追偿权'）")
    parser.add_argument("--info", help="查看指定案例详情（传入案例 GID / DocId 或页面 URL）")
    parser.add_argument("--page", type=int, default=1, help="页码（默认: 1）")
    parser.add_argument("--size", type=int, default=10, help="每页返回数量（默认: 10）")
    parser.add_argument("--token", help="临时传入凭证 Token（覆盖环境变量和配置文件）")
    parser.add_argument("--cookie", help="临时传入 Cookie（用于 wenshu）")
    parser.add_argument("--set-token", nargs=2, metavar=("SOURCE", "TOKEN"), help="保存凭证到本地配置文件 (例: --set-token rmfyalk 'xxx')")
    parser.add_argument("--clear-token", metavar="SOURCE", help="清除本地保存的凭证 (例: --clear-token rmfyalk)")
    parser.add_argument("-o", "--output", help="输出结果文件路径 (.json, .jsonl, .md)")
    parser.add_argument("--no-cache", action="store_true", help="忽略本地缓存")

    args = parser.parse_args()

    # Handle token management commands
    if args.set_token:
        src, tok = args.set_token
        success = set_credential(src, token=tok)
        if success:
            print(f"✅ 成功保存 {src} 凭证到本地配置文件！")
        else:
            print(f"❌ 保存 {src} 凭证失败。")
        return

    if args.clear_token:
        success = clear_credential(args.clear_token)
        if success:
            print(f"✅ 成功清除 {args.clear_token} 凭证！")
        else:
            print(f"❌ 清除凭证失败。")
        return

    # Handle detail request
    if args.info:
        detail = get_case_detail(
            source=args.source,
            case_id=args.info,
            token=args.token,
            cookie=args.cookie,
            no_cache=args.no_cache,
        )
        if "error" in detail and detail.get("error"):
            print(f"❌ 获取案例详情失败: {detail.get('error')}")
            if "message" in detail:
                print(f"\n{detail['message']}")
            sys.exit(1)

        print(f"\n【标题】: {detail.get('title')}")
        if detail.get("case_no"):
            print(f"【案号/编号】: {detail.get('case_no')}")
        if detail.get("court"):
            print(f"【审理法院】: {detail.get('court')}")
        if detail.get("judge_date"):
            print(f"【裁判日期】: {detail.get('judge_date')}")
        if detail.get("key_points"):
            print(f"\n【裁判要点】:\n{detail.get('key_points')}")
        if detail.get("facts"):
            print(f"\n【基本案情】:\n{detail.get('facts')}")
        if detail.get("reasoning"):
            print(f"\n【裁判理由】:\n{detail.get('reasoning')}")
        if detail.get("full_text"):
            print(f"\n【正文节选】:\n{detail.get('full_text')[:1000]}...")

        if args.output:
            write_json(args.output, detail)
            print(f"\n完整详情已保存至: {args.output}")
        return

    # Handle search request
    if args.search is not None or (not args.info and not args.set_token and not args.clear_token):
        kw = args.search or ""
        result = search_cases(
            source=args.source,
            keyword=kw,
            token=args.token,
            cookie=args.cookie,
            page=args.page,
            size=args.size,
            no_cache=args.no_cache,
        )

        if result.get("error"):
            print(f"❌ 检索失败 [{result.get('error')}]:")
            if result.get("message"):
                print(f"\n{result['message']}")
            sys.exit(1)

        records = result.get("records", [])
        total = result.get("total", 0)
        kw_display = f"'{kw}'" if kw else "全部/最新"
        print(f"\n🔍 检索来源: {args.source} | 关键词: {kw_display} | 命中数: {total} | 当前展示: {len(records)} 篇\n")

        for idx, r in enumerate(records, 1):
            title = r.get("title", "未命名案例")
            case_no = r.get("case_no") or r.get("court_case_no") or ""
            court = r.get("court", "")
            date_str = r.get("judge_date", "")
            key_pts = r.get("key_points") or r.get("summary") or ""

            print(f"{idx}. {title}")
            meta_parts = [p for p in [case_no, court, date_str] if p]
            if meta_parts:
                print(f"   ℹ️  {' | '.join(meta_parts)}")
            if key_pts:
                print(f"   💡 【裁判要点】: {key_pts[:120]}...")
            if r.get("url"):
                print(f"   🔗 {r.get('url')}")
            elif r.get("gid"):
                print(f"   🆔 GID: {r.get('gid')}")
            print()

        if args.output:
            write_json(args.output, result)
            print(f"检索结果已写入: {args.output}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
