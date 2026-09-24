"""Tests for pure-Python MS-DOC parsing and article extraction."""

import os
from unittest.mock import patch
import pytest

from scripts.common.docx_utils import (
    extract_paragraphs_from_docx,
    split_into_articles,
    is_article_line,
    match_article_query,
)


@pytest.fixture
def sample_doc_bytes():
    fixture_path = os.path.join(
        os.path.dirname(__file__), "fixtures", "sample_doc.doc"
    )
    with open(fixture_path, "rb") as f:
        return f.read()


def test_doc_extraction_without_external_tools(sample_doc_bytes):
    """Ensure .doc files parse successfully even if antiword/catdoc are missing."""
    with patch("subprocess.run", side_effect=FileNotFoundError("Tool missing")):
        paragraphs = extract_paragraphs_from_docx(sample_doc_bytes)

    assert len(paragraphs) > 20
    text_content = "\n".join(paragraphs)
    assert "民间借贷" in text_content
    assert "第十三条" in text_content
    assert "第二十八条" in text_content


def test_split_articles_from_doc_paragraphs(sample_doc_bytes):
    """Ensure articles are cleanly split with accurate numbering."""
    with patch("subprocess.run", side_effect=FileNotFoundError("Tool missing")):
        paragraphs = extract_paragraphs_from_docx(sample_doc_bytes)

    articles = split_into_articles(paragraphs)
    article_dict = dict(articles)

    assert "第十三条" in article_dict
    assert "合同无效" in article_dict["第十三条"]
    assert "（四）出借人事先知道或者应当知道借款人借款用于违法犯罪活动仍然提供借款的" in article_dict["第十三条"]

    assert "第二十八条" in article_dict
    assert "逾期利率" in article_dict["第二十八条"]
    assert "一年期贷款市场报价利率四倍" in article_dict["第二十八条"]


def test_corrupted_doc_raises_runtime_error():
    """Ensure corrupted OLE files raise clear RuntimeError instead of unhandled crash."""
    corrupted_doc = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x00\x00corrupted"
    with patch("subprocess.run", side_effect=FileNotFoundError("Tool missing")):
        with pytest.raises(RuntimeError) as exc_info:
            extract_paragraphs_from_docx(corrupted_doc)
        assert "extraction methods failed" in str(exc_info.value)
