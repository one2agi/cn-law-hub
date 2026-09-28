import pytest
from case_gateway.contracts import (
    CaseSource,
    CaseQuery,
    CaseRecord,
    CaseDetail,
    CaseSearchResult,
)
from case_gateway.errors import (
    CaseGatewayError,
    AuthenticationRequiredError,
    TokenExpiredError,
    CaseNotFoundError,
)


def test_case_record_legacy_dict_rmfyalk():
    rec = CaseRecord(
        id="test_gid_123",
        source="rmfyalk",
        title="张三诉李四案",
        case_no="2024-01-1-001",
        court_case_no="（2023）最高法民终1号",
        court="最高人民法院",
        judge_date="2023-12-01",
        case_type="民事",
        summary="民间借贷审判规则",
        url="https://rmfyalk.court.gov.cn/view/content.html?id=test_gid_123",
        extra={"keywords": "民间借贷;本金", "lib_type": "指导性案例"},
    )
    legacy = rec.to_legacy_dict()
    assert legacy["gid"] == "test_gid_123"
    assert legacy["id"] == "test_gid_123"
    assert legacy["source"] == "rmfyalk"
    assert legacy["title"] == "张三诉李四案"
    assert legacy["court_case_no"] == "（2023）最高法民终1号"
    assert legacy["key_points"] == "民间借贷审判规则"
    assert legacy["keywords"] == "民间借贷;本金"
    assert legacy["lib_type"] == "指导性案例"


def test_case_record_legacy_dict_wenshu():
    rec = CaseRecord(
        id="doc_abc",
        source="wenshu",
        title="某银行借款案",
        case_no="（2023）京01民终2号",
        court="北京市第一中级人民法院",
        judge_date="2023-10-15",
        case_type="民事案件",
        summary="罚息标准",
        url="https://wenshu.court.gov.cn/doc_abc",
    )
    legacy = rec.to_legacy_dict()
    assert legacy["doc_id"] == "doc_abc"
    assert legacy["id"] == "doc_abc"
    assert legacy["source"] == "wenshu"
    assert legacy["summary"] == "罚息标准"


def test_case_search_result_legacy_dict():
    rec = CaseRecord(
        id="guid_1",
        source="court_guiding",
        title="指导案例1号",
        case_no="指导性案例1号",
        court="最高人民法院",
        judge_date="2020-01-01",
        summary="要点摘要",
    )
    res = CaseSearchResult(
        source="court_guiding",
        query="借款",
        page=1,
        size=10,
        total=1,
        count=1,
        records=[rec],
        degraded=True,
        warning="Token未配置，已降级至公开指导案例",
    )
    legacy = res.to_legacy_dict()
    assert legacy["source"] == "court_guiding"
    assert legacy["keyword"] == "借款"
    assert legacy["total"] == 1
    assert legacy["count"] == 1
    assert legacy["degraded"] is True
    assert legacy["warning"] == "Token未配置，已降级至公开指导案例"
    assert len(legacy["records"]) == 1
    assert legacy["records"][0]["title"] == "指导案例1号"


def test_case_detail_legacy_dict():
    detail = CaseDetail(
        id="test_gid_123",
        source="rmfyalk",
        title="案例正文",
        case_no="2024-01-1",
        court="最高法",
        key_points="要点",
        facts="案情",
        reasoning="理由",
        ruling="判决",
        full_text="正文全文",
    )
    legacy = detail.to_legacy_dict()
    assert legacy["gid"] == "test_gid_123"
    assert legacy["key_points"] == "要点"
    assert legacy["facts"] == "案情"
    assert legacy["full_text"] == "正文全文"


def test_error_hierarchy():
    err = AuthenticationRequiredError("rmfyalk", "请配置Token")
    assert isinstance(err, CaseGatewayError)
    assert err.source == "rmfyalk"
    assert err.error_code == "AUTHENTICATION_REQUIRED"
    assert "请配置Token" in str(err)


def test_from_legacy_dict_roundtrip():
    # CaseRecord roundtrip
    rec = CaseRecord(
        id="test_gid_888",
        source="rmfyalk",
        title="测试借贷案",
        case_no="2024-02-1",
        court_case_no="（2024）京01民初1号",
        court="北京市第一中级人民法院",
        judge_date="2024-01-01",
        case_type="民事",
        summary="民间借贷裁判要旨",
        url="https://rmfyalk.court.gov.cn/888",
    )
    legacy_rec = rec.to_legacy_dict()
    reconstructed_rec = CaseRecord.from_legacy_dict(legacy_rec)
    assert reconstructed_rec.id == "test_gid_888"
    assert reconstructed_rec.source == "rmfyalk"
    assert reconstructed_rec.title == "测试借贷案"
    assert reconstructed_rec.summary == "民间借贷裁判要旨"

    # CaseDetail roundtrip
    detail = CaseDetail(
        id="doc_777",
        source="wenshu",
        title="详细判决",
        case_no="（2023）沪01民终10号",
        key_points="关键要点",
        facts="查明事实",
        error="TEST_ERROR",
        message="Test Message",
    )
    legacy_detail = detail.to_legacy_dict()
    assert legacy_detail["doc_id"] == "doc_777"
    assert legacy_detail["error"] == "TEST_ERROR"
    reconstructed_detail = CaseDetail.from_legacy_dict(legacy_detail)
    assert reconstructed_detail.id == "doc_777"
    assert reconstructed_detail.source == "wenshu"
    assert reconstructed_detail.facts == "查明事实"
    assert reconstructed_detail.error == "TEST_ERROR"

    # CaseSearchResult roundtrip
    search_res = CaseSearchResult(
        source="rmfyalk",
        query="民间借贷",
        page=1,
        size=10,
        total=1,
        count=1,
        records=[rec],
        degraded=True,
        warning="Degraded mode active",
    )
    legacy_res = search_res.to_legacy_dict()
    reconstructed_res = CaseSearchResult.from_legacy_dict(legacy_res)
    assert reconstructed_res.source == "rmfyalk"
    assert reconstructed_res.query == "民间借贷"
    assert reconstructed_res.degraded is True
    assert reconstructed_res.warning == "Degraded mode active"
    assert len(reconstructed_res.records) == 1
    assert reconstructed_res.records[0].id == "test_gid_888"
