"""Adapter for China Judgements Online (中国裁判文书网)."""

from typing import Optional
import wenshu_crawler
from common import get_credential
from ..contracts import CaseDetail, CaseQuery, CaseRecord, CaseSearchResult
from ..provider import CaseProvider


class WenshuProvider(CaseProvider):
    @property
    def name(self) -> str:
        return "wenshu"

    def is_available(self, token: Optional[str] = None, cookie: Optional[str] = None) -> bool:
        cred = get_credential("wenshu", token=token, cookie=cookie)
        return bool(cred.get("cookie") or cred.get("token"))

    def search(self, query: CaseQuery) -> CaseSearchResult:
        raw = wenshu_crawler.search_cases(
            keyword=query.keyword,
            token=query.token,
            cookie=query.cookie,
            page=query.page,
            size=query.size,
            no_cache=query.no_cache,
        )
        if raw.get("error"):
            err = raw.get("error")
            if err in ("AUTHENTICATION_FAILED", "AUTH_REQUIRED"):
                err = "AUTHENTICATION_REQUIRED"
            return CaseSearchResult(
                source=self.name,
                query=query.keyword,
                page=query.page,
                size=query.size,
                total=0,
                count=0,
                records=[],
                error=err,
                message=raw.get("message"),
            )

        records = []
        for r in raw.get("records", []):
            doc_id = r.get("doc_id") or r.get("id", "")
            rec = CaseRecord(
                id=doc_id,
                source=self.name,
                title=r.get("title", ""),
                case_no=r.get("case_no", ""),
                court=r.get("court", ""),
                judge_date=r.get("judge_date", ""),
                case_type=r.get("case_type", ""),
                summary=r.get("summary") or r.get("key_points", ""),
                url=r.get("url", ""),
            )
            records.append(rec)

        return CaseSearchResult(
            source=self.name,
            query=query.keyword,
            page=query.page,
            size=query.size,
            total=raw.get("total", 0),
            count=len(records),
            records=records,
            has_more=(query.page * query.size < raw.get("total", 0)),
        )

    def get_detail(self, case_id: str, query: Optional[CaseQuery] = None) -> CaseDetail:
        token = query.token if query else None
        cookie = query.cookie if query else None
        no_cache = query.no_cache if query else False
        raw = wenshu_crawler.fetch_case_detail(
            doc_id=case_id,
            token=token,
            cookie=cookie,
            no_cache=no_cache,
        )
        doc_id = raw.get("doc_id") or case_id
        return CaseDetail(
            id=doc_id,
            source=self.name,
            title=raw.get("title", ""),
            case_no=raw.get("case_no", ""),
            court=raw.get("court", ""),
            judge_date=raw.get("judge_date", ""),
            case_type=raw.get("case_type", ""),
            full_text=raw.get("full_text", ""),
            key_points=raw.get("key_points") or raw.get("summary", ""),
            url=raw.get("url", ""),
            extra={k: v for k, v in raw.items() if k not in ("doc_id", "title", "case_no", "court", "judge_date", "full_text", "url")},
        )
