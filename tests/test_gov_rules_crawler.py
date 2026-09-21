"""Tests for scripts/gov_rules_crawler.py — 国家规章库.

These are offline tests: ``search_page`` is mocked, so no network or Athena
auth is required. They cover the pagination control flow of
``search_category``, which the MCP routing tests do not reach (they mock
``search_category`` itself).
"""

from unittest import mock

import pytest

from gov_rules_crawler import search_category


def make_item(title="测试管理办法", url="https://www.gov.cn/zhengce/xxgk/gjgzk/1.htm"):
    """Build one raw record as returned by the upstream search API."""
    return {
        "f_202321360426": title,
        "doc_pub_url": url,
        "f_202323394765": "财政部",
        "f_202321807875": "部门规章",
        "f_202344311304": "财政部令第100号",
        "f_202321915922": "2024-01-01",
        "f_202328191239": "财政部",
        "f_202321758948": "第一条 为了规范……",
    }


def make_page(items, total=None, page_count=1):
    """Build one raw search response."""
    return {
        "pager": {
            "total": len(items) if total is None else total,
            "pageCount": page_count,
        },
        "list": items,
    }


class TestSearchCategoryPagination:
    def test_first_page_request_and_conversion(self):
        """Regression: the request must run inside the loop, not after `break`.

        Before the fix this raised UnboundLocalError at `data["pager"]`.
        """
        page = make_page([make_item()])
        with mock.patch("gov_rules_crawler.search_page", return_value=page) as sp:
            records = search_category(
                "AUTH",
                "部门规章",
                keyword="管理办法",
                page_size=100,
                timeout=15,
            )

        sp.assert_called_once_with(
            "AUTH",
            "部门规章",
            1,
            page_size=100,
            keyword="管理办法",
            timeout=15,
        )
        assert len(records) == 1
        record = records[0]
        assert record["title"] == "测试管理办法"
        assert record["category"] == "部门规章"
        assert record["detail_url"] == (
            "https://www.gov.cn/zhengce/xxgk/gjgzk/1.htm"
        )
        assert record["source"] == "gov_rules"

    def test_max_pages_stops_before_extra_request(self):
        """`max_pages` must be checked before the request, not after."""
        page = make_page([make_item()], total=600, page_count=3)
        with mock.patch("gov_rules_crawler.search_page", return_value=page) as sp:
            search_category("AUTH", "部门规章", max_pages=1)

        assert sp.call_count == 1
        assert sp.call_args.args[2] == 1

    def test_multiple_pages_are_merged(self):
        pages = {
            1: make_page([make_item("第一页办法")], total=2, page_count=2),
            2: make_page([make_item("第二页办法")], total=2, page_count=2),
        }
        seen = []

        def fake_search(auth, category_name, page_no, **kwargs):
            seen.append(page_no)
            return pages[page_no]

        with mock.patch("gov_rules_crawler.search_page", side_effect=fake_search):
            records = search_category("AUTH", "部门规章")

        assert seen == [1, 2]
        assert [r["title"] for r in records] == ["第一页办法", "第二页办法"]

    def test_empty_page_terminates(self):
        page = make_page([], total=0, page_count=5)
        with mock.patch("gov_rules_crawler.search_page", return_value=page) as sp:
            records = search_category("AUTH", "部门规章")

        assert records == []
        assert sp.call_count == 1

    def test_keyword_filters_records_not_requests(self):
        """Client-side title filter drops non-matching rows of the same page."""
        page = make_page([make_item("管理办法"), make_item("无关条目")])
        with mock.patch("gov_rules_crawler.search_page", return_value=page) as sp:
            records = search_category("AUTH", "部门规章", keyword="管理办法")

        assert [r["title"] for r in records] == ["管理办法"]
        assert sp.call_count == 1

    def test_max_items_stops_early(self):
        page = make_page([make_item(f"办法{i}") for i in range(10)],
                         total=10, page_count=3)
        with mock.patch("gov_rules_crawler.search_page", return_value=page) as sp:
            records = search_category("AUTH", "部门规章", max_items=2)

        assert len(records) == 2
        assert sp.call_count == 1


class FakeAuth:
    base_url = "https://example.invalid"
    _headers = {"X-Test": "1"}

    def headers(self):
        return dict(self._headers)


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class TestSearchPage:
    """The layer that ``search_category`` mocks, exercised for real."""

    def _call_and_capture(self, **kwargs):
        import gov_rules_crawler as g

        captured = {}

        def fake_request(method, url, **req_kwargs):
            captured.update(req_kwargs)
            return FakeResponse(
                {"resultCode": {"code": 200}, "result": {"data": make_page([])}}
            )

        g._cache.clear()
        with mock.patch.object(g, "http_request", side_effect=fake_request):
            g.search_page(FakeAuth(), "部门规章", 1, page_size=10, **kwargs)
        g._cache.clear()
        return captured

    def test_keyword_goes_into_payload(self):
        captured = self._call_and_capture(keyword="财政")
        title_field = next(
            f
            for f in captured["json"]["searchFields"]
            if f["fieldName"] == "f_202321360426"
        )
        assert title_field["searchWord"] == "财政"
        assert captured["json"]["pageSize"] == 10

    def test_no_keyword_omits_search_word(self):
        captured = self._call_and_capture()
        title_field = next(
            f
            for f in captured["json"]["searchFields"]
            if f["fieldName"] == "f_202321360426"
        )
        assert "searchWord" not in title_field

    def test_title_keyword_uses_match_not_term(self):
        """TERM on the title field only matches a single-token keyword.

        With TERM, `--search "管理办法"` returned 0 records even though the
        upstream index holds 1228 matches for it.
        """
        captured = self._call_and_capture(keyword="管理办法")
        title_field = next(
            f
            for f in captured["json"]["searchFields"]
            if f["fieldName"] == "f_202321360426"
        )
        assert title_field["searchType"] == "MATCH"

    def test_category_field_stays_term(self):
        """The category field is a controlled vocabulary — TERM is correct."""
        captured = self._call_and_capture(keyword="管理办法")
        category_field = next(
            f
            for f in captured["json"]["searchFields"]
            if f["fieldName"] == "f_202321807875"
        )
        assert category_field["searchType"] == "TERM"
        assert category_field["searchWord"] == "部门规章"

    def test_keyword_partitions_cache(self):
        import gov_rules_crawler as g

        with_keyword = g._cache._key("search_page", "部门规章", "1", "10", "财政")
        without = g._cache._key("search_page", "部门规章", "1", "10", "")
        assert with_keyword != without
