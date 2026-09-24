"""Tests for Chinese legal citation formatting standard (PRC judicial rules)."""

import pytest
from scripts.common.text_utils import format_legal_citation


def test_format_basic_statute():
    res = format_legal_citation("中华人民共和国民法典", 667)
    assert res["formatted_citation"] == "《中华人民共和国民法典》第六百六十七条"
    assert res["article"] == "第六百六十七条"
    assert res["paragraph"] is None
    assert res["item"] is None


def test_format_already_bracketed_title():
    res = format_legal_citation("《中华人民共和国民事诉讼法》", "第六十七条")
    assert res["formatted_citation"] == "《中华人民共和国民事诉讼法》第六十七条"
    assert res["law_title"] == "《中华人民共和国民事诉讼法》"


def test_format_with_paragraph_and_item():
    res = format_legal_citation(
        "最高人民法院关于审理民间借贷案件适用法律若干问题的规定",
        article=13,
        paragraph=1,
        item=4,
    )
    assert res["formatted_citation"] == "《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》第十三条第一款第（四）项"
    assert res["article"] == "第十三条"
    assert res["paragraph"] == "第一款"
    assert res["item"] == "第（四）项"


def test_format_subparagraph_and_large_article():
    res = format_legal_citation(
        "中华人民共和国民法典",
        article=1010,
        paragraph=2,
    )
    assert res["formatted_citation"] == "《中华人民共和国民法典》第一千零一十条第二款"
    assert res["article"] == "第一千零一十条"
    assert res["paragraph"] == "第二款"


def test_format_chinese_string_inputs():
    res = format_legal_citation(
        "民间借贷规定",
        article="第二十八条",
        paragraph="第二款",
        item="（一）",
    )
    assert res["formatted_citation"] == "《民间借贷规定》第二十八条第二款第（一）项"
    assert res["item"] == "第（一）项"


def test_format_law_title_with_official_document_number():
    res = format_legal_citation(
        "《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》（法释〔2020〕17号）",
        article=13,
        paragraph=1,
        item=4,
    )
    assert res["formatted_citation"] == "《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》（法释〔2020〕17号）第十三条第一款第（四）项"
    assert res["law_title"] == "《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》（法释〔2020〕17号）"


def test_format_sub_article():
    res1 = format_legal_citation("中华人民共和国刑法", "第一百三十三条之一")
    assert res1["formatted_citation"] == "《中华人民共和国刑法》第一百三十三条之一"
    assert res1["article"] == "第一百三十三条之一"

    res2 = format_legal_citation("中华人民共和国刑法", "133-1")
    assert res2["formatted_citation"] == "《中华人民共和国刑法》第一百三十三条之一"
    assert res2["article"] == "第一百三十三条之一"

