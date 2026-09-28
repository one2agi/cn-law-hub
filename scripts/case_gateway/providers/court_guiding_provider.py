"""Adapter for Supreme People's Court Guiding Cases (court.gov.cn/shenpan/gengduo/77.html).

Extracted from scripts/case_search.py for clean provider seam adherence.
"""

import json
import re
import urllib.parse
from typing import Optional
from urllib.parse import urljoin

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from common import (
    clean_text,
    create_crawler_headers,
    create_http_session,
    get_cache,
    http_request,
)
from ..contracts import CaseDetail, CaseQuery, CaseRecord, CaseSearchResult
from ..provider import CaseProvider

COURT_BASE_URL = "https://www.court.gov.cn"
_cache = get_cache("court-guiding-case-db")
_session = None


def _get_session():
    global _session
    if _session is None:
        _session = create_http_session()
    return _session


class CourtGuidingProvider(CaseProvider):
    @property
    def name(self) -> str:
        return "court_guiding"

    def is_available(self, token: Optional[str] = None, cookie: Optional[str] = None) -> bool:
        return BeautifulSoup is not None

    def search(self, query: CaseQuery) -> CaseSearchResult:
        if BeautifulSoup is None:
            return CaseSearchResult(
                source=self.name,
                query=query.keyword,
                total=0,
                count=0,
                records=[],
                error="MISSING_DEPENDENCY",
                message="please run 'pip install beautifulsoup4'",
            )

        sess = _get_session()
        headers = create_crawler_headers()
        cache_key = _cache._key("guiding_list", str(query.page))

        html = None
        if not query.no_cache:
            cached = _cache.get(cache_key, max_age=86400)
            if cached:
                html = cached

        if not html:
            url = (
                f"{COURT_BASE_URL}/shenpan/gengduo/77.html"
                if query.page == 1
                else f"{COURT_BASE_URL}/shenpan/gengduo/77_{query.page}.html"
            )
            try:
                resp = http_request("GET", url, headers=headers, session=sess, timeout=query.timeout)
                resp.encoding = "utf-8"
                html = resp.text
                if not query.no_cache:
                    _cache.set(cache_key, html)
            except Exception as e:
                return CaseSearchResult(
                    source=self.name,
                    query=query.keyword,
                    total=0,
                    count=0,
                    records=[],
                    error="REQUEST_FAILED",
                    message=str(e),
                )

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

            date_str = ""
            parent = a.parent
            if parent:
                i_tag = parent.find("i", class_="date")
                if i_tag:
                    date_str = clean_text(i_tag.get_text())

            if query.keyword and query.keyword.lower() not in title.lower():
                continue

            m = re.search(r"指导(?:性)?案例\s*(\d+)号", title)
            case_no = f"指导性案例{m.group(1)}号" if m else ""

            # Extract item id from URL
            item_id_m = re.search(r"/shenpan/xiangqing/(\d+)\.html", full_url)
            cid = item_id_m.group(1) if item_id_m else case_no or full_url

            records.append(
                CaseRecord(
                    id=cid,
                    source=self.name,
                    title=title,
                    case_no=case_no,
                    court="最高人民法院",
                    judge_date=date_str,
                    case_type="指导性案例",
                    url=full_url,
                )
            )

        sliced_records = records[: query.size]
        return CaseSearchResult(
            source=self.name,
            query=query.keyword,
            page=query.page,
            size=query.size,
            total=len(records),
            count=len(sliced_records),
            records=sliced_records,
            has_more=(query.page * query.size < len(records)),
        )

    def get_detail(self, case_id: str, query: Optional[CaseQuery] = None) -> CaseDetail:
        if BeautifulSoup is None:
            return CaseDetail(id=case_id, source=self.name, title="", extra={"error": "MISSING_DEPENDENCY"})

        clean_id = str(case_id or "").strip()
        if not clean_id:
            return CaseDetail(id="", source=self.name, title="", extra={"error": "INVALID_ARGUMENT"})

        if clean_id.startswith("http://") or clean_id.startswith("https://"):
            parsed = urllib.parse.urlparse(clean_id)
            if parsed.netloc.lower() not in {"court.gov.cn", "www.court.gov.cn"}:
                return CaseDetail(
                    id=clean_id,
                    source=self.name,
                    title="",
                    extra={"error": f"INVALID_URL: Only court.gov.cn domains are permitted (got {parsed.netloc})"},
                )
            full_url = clean_id
        else:
            full_url = f"{COURT_BASE_URL}/shenpan/xiangqing/{clean_id}.html"

        cache_key = _cache._key("guiding_detail", full_url)
        no_cache = query.no_cache if query else False

        if not no_cache:
            cached = _cache.get(cache_key, max_age=86400 * 7)
            if cached:
                try:
                    d = json.loads(cached)
                    return CaseDetail(
                        id=clean_id,
                        source=self.name,
                        title=d.get("title", ""),
                        case_no=d.get("case_no", ""),
                        court=d.get("court", "最高人民法院"),
                        url=d.get("url", full_url),
                        key_points=d.get("key_points", ""),
                        facts=d.get("facts", ""),
                        reasoning=d.get("reasoning", ""),
                        full_text=d.get("full_text", ""),
                    )
                except Exception:
                    pass

        sess = _get_session()
        headers = create_crawler_headers()
        try:
            resp = http_request("GET", full_url, headers=headers, session=sess, timeout=15)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            return CaseDetail(id=clean_id, source=self.name, title="", extra={"error": f"REQUEST_FAILED: {e}"})

        title_tag = soup.find("h2") or soup.find("title")
        title = clean_text(title_tag.get_text()) if title_tag else ""
        title = re.sub(r"\s*-\s*中华人民共和国最高人民法院.*$", "", title)

        m = re.search(r"指导(?:性)?案例\s*(\d+)号", title)
        case_no = f"指导性案例{m.group(1)}号" if m else ""

        body_tag = soup.find(class_="txt_txt") or soup.find(class_="txt")
        full_text = clean_text(body_tag.get_text("\n")) if body_tag else ""

        key_points = ""
        facts = ""
        reasoning = ""

        heading_pattern = r"(?:【|(?:\n|^)\s*)(裁判要点|裁判要旨|基本案情|裁判理由|相关法条|裁判结果)(?:】|[:：]|\n|\s)"
        parts = re.split(heading_pattern, full_text)
        if len(parts) > 1:
            for i in range(1, len(parts), 2):
                tag = parts[i]
                val = clean_text(parts[i + 1]) if i + 1 < len(parts) else ""
                if tag in {"裁判要点", "裁判要旨"}:
                    key_points = val
                elif tag == "基本案情":
                    facts = val
                elif tag == "裁判理由":
                    reasoning = val

        detail = CaseDetail(
            id=clean_id,
            source=self.name,
            title=title,
            case_no=case_no,
            court="最高人民法院",
            url=full_url,
            key_points=key_points,
            facts=facts,
            reasoning=reasoning,
            full_text=full_text,
        )

        if not no_cache:
            _cache.set(cache_key, json.dumps(detail.to_legacy_dict(), ensure_ascii=False))

        return detail
