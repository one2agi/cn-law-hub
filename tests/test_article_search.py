#!/usr/bin/env python3
"""Unit tests for scripts/article_search.py."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import article_search as art_search


class TestSearchArticles(unittest.TestCase):
    @mock.patch("article_search.extract_paragraphs_from_docx")
    @mock.patch("article_search._cache")
    @mock.patch("article_search._request")
    @mock.patch("article_search.get_download_url")
    @mock.patch("article_search.search_laws")
    def test_single_match(
        self, mock_search, mock_get_url, mock_request, mock_cache, mock_extract
    ):
        mock_search.return_value = {
            "code": 200,
            "total": 1,
            "rows": [{"bbbs": "id1", "title": "Test Law", "sxx": 3}],
        }
        mock_cache.get_file.return_value = b"fake docx bytes"
        mock_extract.return_value = [
            "第一条 内容一",
            "第二条 含有违约金的内容",
            "第三条 内容三",
        ]

        results = art_search.search_articles("违约金", max_laws=1, json_output=False)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Test Law")
        self.assertEqual(results[0]["matched_articles"], 1)
        match_nums = [a["article_num"] for a in results[0]["articles"] if a["is_match"]]
        self.assertEqual(match_nums, ["第二条"])

    @mock.patch("article_search.extract_paragraphs_from_docx")
    @mock.patch("article_search._cache")
    @mock.patch("article_search._request")
    @mock.patch("article_search.get_download_url")
    @mock.patch("article_search.search_laws")
    def test_context(
        self, mock_search, mock_get_url, mock_request, mock_cache, mock_extract
    ):
        mock_search.return_value = {
            "code": 200,
            "total": 1,
            "rows": [{"bbbs": "id1", "title": "Test Law", "sxx": 3}],
        }
        mock_cache.get_file.return_value = b"fake docx bytes"
        mock_extract.return_value = [
            "第一条 内容一",
            "第二条 含有违约金的内容",
            "第三条 内容三",
        ]

        results = art_search.search_articles(
            "违约金", max_laws=1, context=1, json_output=False
        )

        self.assertEqual(len(results[0]["articles"]), 3)  # 第二条 + 上下文
        nums = [a["article_num"] for a in results[0]["articles"]]
        self.assertEqual(nums, ["第一条", "第二条", "第三条"])

    @mock.patch("article_search.extract_paragraphs_from_docx")
    @mock.patch("article_search._cache")
    @mock.patch("article_search._request")
    @mock.patch("article_search.get_download_url")
    @mock.patch("article_search.search_laws")
    def test_max_laws_limit(
        self, mock_search, mock_get_url, mock_request, mock_cache, mock_extract
    ):
        mock_search.return_value = {
            "code": 200,
            "total": 3,
            "rows": [
                {"bbbs": "id1", "title": "Law 1", "sxx": 3},
                {"bbbs": "id2", "title": "Law 2", "sxx": 3},
                {"bbbs": "id3", "title": "Law 3", "sxx": 3},
            ],
        }
        mock_cache.get_file.return_value = b"fake docx bytes"
        mock_extract.return_value = [
            "第一条 含有违约金",
        ]

        results = art_search.search_articles("违约金", max_laws=2, json_output=False)

        self.assertEqual(len(results), 2)

    @mock.patch("article_search.extract_paragraphs_from_docx")
    @mock.patch("article_search._cache")
    @mock.patch("article_search._request")
    @mock.patch("article_search.get_download_url")
    @mock.patch("article_search.search_laws")
    def test_resume_mode_with_prefetch(
        self, mock_search, mock_get_url, mock_request, mock_cache, mock_extract
    ):
        mock_search.return_value = {
            "code": 200,
            "total": 3,
            "rows": [
                {"bbbs": "id1", "title": "Cached Law 1", "sxx": 3},
                {"bbbs": "id2", "title": "Uncached Law 2", "sxx": 3},
                {"bbbs": "id3", "title": "Uncached Law 3", "sxx": 3},
            ],
        }
        # Initially, only id1 is cached
        cache_store = {"docx:id1": b"cached docx"}
        mock_cache._key.side_effect = lambda prefix, b: f"{prefix}:{b}"
        mock_cache.get_file.side_effect = lambda k: cache_store.get(k)
        def set_file_mock(k, v):
            cache_store[k] = v
        mock_cache.set_file.side_effect = set_file_mock

        mock_get_url.return_value = "http://fake/download"
        mock_request.return_value.content = b"downloaded docx"
        mock_extract.return_value = ["第一条 违约金"]

        # Run with resume=True
        results = art_search.search_articles("违约金", max_laws=3, resume=True, json_output=False)

        # id1 was initially cached -> skipped by resume
        # id2 and id3 were uncached -> prefetched and searched -> returned in results
        self.assertEqual(len(results), 2)
        titles = [r["title"] for r in results]
        self.assertNotIn("Cached Law 1", titles)
        self.assertIn("Uncached Law 2", titles)
        self.assertIn("Uncached Law 3", titles)



if __name__ == "__main__":
    unittest.main()
