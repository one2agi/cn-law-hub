"""Tests for legal document classification and amendment decision warning."""

import pytest
from scripts.common.text_utils import (
    classify_legal_document_type,
    get_amendment_warning,
)


def test_classify_amendment_decision():
    title = "最高人民法院关于修改《关于审理民间借贷案件适用法律若干问题的规定》的决定"
    doc_type = classify_legal_document_type(title)
    assert doc_type == "amendment_decision"

    warning = get_amendment_warning(title)
    assert warning is not None
    assert "修改决定" in warning
    assert "条号顺移" in warning or "整合版本" in warning


def test_classify_full_text():
    title = "最高人民法院关于审理民间借贷案件适用法律若干问题的规定"
    doc_type = classify_legal_document_type(title)
    assert doc_type in ["judicial_interpretation", "full_text"]

    warning = get_amendment_warning(title)
    assert warning is None


def test_classify_reply():
    title = "最高人民法院关于新民间借贷司法解释适用范围问题的批复"
    doc_type = classify_legal_document_type(title)
    assert doc_type == "judicial_reply"


def test_classify_statute():
    title = "中华人民共和国民法典"
    doc_type = classify_legal_document_type(title)
    assert doc_type == "statute"
