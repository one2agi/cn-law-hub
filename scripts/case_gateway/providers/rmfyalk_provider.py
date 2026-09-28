"""Adapter for People's Court Case Database (人民法院案例库)."""

from typing import Optional
import rmfyalk_crawler
from common import get_credential
from ..contracts import CaseDetail, CaseQuery, CaseRecord, CaseSearchResult
from ..provider import CaseProvider


class RmfyalkProvider(CaseProvider):
    @property
    def name(self) -> str:
        return "rmfyalk"

    def is_available(self, token: Optional[str] = None, cookie: Optional[str] = None) -> bool:
        cred = get_credential("rmfyalk", token=token, cookie=cookie)
        return bool(cred.get("token"))

    def search(self, query: CaseQuery) -> CaseSearchResult:
        raw = rmfyalk_crawler.search_cases(
            keyword=query.keyword,
            token=query.token,
            page=query.page,
            size=query.size,
            lib=query.lib,
            no_cache=query.no_cache,
        )
        if raw.get("error"):
            return CaseSearchResult(
                source=self.name,
                query=query.keyword,
                page=query.page,
                size=query.size,
                total=0,
                count=0,
                records=[],
                error=raw.get("error"),
                message=raw.get("message"),
            )

        records = []
        for r in raw.get("records", []):
            gid = r.get("gid") or r.get("id", "")
            rec = CaseRecord(
                id=gid,
                source=self.name,
                title=r.get("title", ""),
                case_no=r.get("case_no", ""),
                court_case_no=r.get("court_case_no", ""),
                court=r.get("court", ""),
                judge_date=r.get("judge_date", ""),
                case_type=r.get("case_type", ""),
                summary=r.get("key_points") or r.get("summary", ""),
                url=r.get("url", ""),
                extra={
                    "keywords": r.get("keywords", ""),
                    "lib_type": r.get("lib_type", "参考案例"),
                },
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
        no_cache = query.no_cache if query else False
        raw = rmfyalk_crawler.fetch_case_detail(
            case_id=case_id,
            token=token,
            no_cache=no_cache,
        )
        gid = raw.get("gid") or case_id
        return CaseDetail(
            id=gid,
            source=self.name,
            title=raw.get("title", ""),
            case_no=raw.get("case_no", ""),
            court_case_no=raw.get("court_case_no", ""),
            court=raw.get("court", ""),
            judge_date=raw.get("judge_date", ""),
            keywords=raw.get("keywords", ""),
            procedure=raw.get("procedure", ""),
            key_points=raw.get("key_points", ""),
            facts=raw.get("facts", ""),
            reasoning=raw.get("reasoning", ""),
            ruling=raw.get("ruling", ""),
            full_text=raw.get("full_text", ""),
            related_laws=raw.get("related_laws", ""),
            url=raw.get("url", ""),
            extra={
                k: v
                for k, v in raw.items()
                if k
                not in (
                    "gid",
                    "title",
                    "case_no",
                    "court_case_no",
                    "court",
                    "judge_date",
                    "key_points",
                    "facts",
                    "reasoning",
                    "ruling",
                    "url",
                    "keywords",
                    "procedure",
                    "full_text",
                    "related_laws",
                )
            },
        )
