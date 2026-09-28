"""Normalized domain contracts for CaseGateway."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class CaseSource(str, Enum):
    RMFYALK = "rmfyalk"
    WENSHU = "wenshu"
    COURT_GUIDING = "court_guiding"
    AUTO = "auto"


@dataclass
class CaseRecord:
    """Normalized search result item across all judicial databases."""

    id: str
    source: str
    title: str
    case_no: str = ""
    court_case_no: str = ""
    court: str = ""
    judge_date: str = ""
    case_type: str = ""
    summary: str = ""
    url: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Backward-compatible dict matching legacy crawler output format."""
        d: Dict[str, Any] = {
            "source": self.source,
            "id": self.id,
            "title": self.title,
            "case_no": self.case_no,
            "court": self.court,
            "judge_date": self.judge_date,
            "case_type": self.case_type,
            "url": self.url,
        }
        if self.source == "rmfyalk":
            d.update({
                "gid": self.id,
                "court_case_no": self.court_case_no,
                "keywords": self.extra.get("keywords", ""),
                "key_points": self.summary,
                "lib_type": self.extra.get("lib_type", "参考案例"),
            })
        elif self.source == "wenshu":
            d.update({
                "doc_id": self.id,
                "summary": self.summary,
            })
        elif self.source == "court_guiding":
            d.update({
                "key_points": self.summary,
            })
        return d

    @classmethod
    def from_legacy_dict(cls, d: Dict[str, Any]) -> "CaseRecord":
        """Reconstruct CaseRecord from a legacy dictionary."""
        cid = d.get("id") or d.get("gid") or d.get("doc_id") or ""
        source = d.get("source", "rmfyalk")
        summary = d.get("summary") or d.get("key_points") or ""
        reserved = {
            "id", "gid", "doc_id", "source", "title", "case_no", "court_case_no",
            "court", "judge_date", "case_type", "summary", "key_points", "url",
        }
        extra = {k: v for k, v in d.items() if k not in reserved}
        return cls(
            id=str(cid),
            source=source,
            title=d.get("title", ""),
            case_no=d.get("case_no", ""),
            court_case_no=d.get("court_case_no", ""),
            court=d.get("court", ""),
            judge_date=d.get("judge_date", "") or d.get("ref_date", ""),
            case_type=d.get("case_type", ""),
            summary=summary,
            url=d.get("url", ""),
            extra=extra,
        )


@dataclass
class CaseDetail:
    """Normalized full case content."""

    id: str
    source: str
    title: str
    case_no: str = ""
    court_case_no: str = ""
    court: str = ""
    judge_date: str = ""
    case_type: str = ""
    keywords: str = ""
    procedure: str = ""
    key_points: str = ""
    facts: str = ""
    reasoning: str = ""
    ruling: str = ""
    full_text: str = ""
    related_laws: str = ""
    url: str = ""
    error: Optional[str] = None
    message: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Convert to legacy format expected by case_search and mcp_server."""
        res = asdict(self)
        if self.source == "rmfyalk":
            res["gid"] = self.id
        elif self.source == "wenshu":
            res["doc_id"] = self.id
        if self.error:
            res["error"] = self.error
        if self.message:
            res["message"] = self.message
        return res

    @classmethod
    def from_legacy_dict(cls, d: Dict[str, Any]) -> "CaseDetail":
        """Reconstruct CaseDetail from a legacy dictionary."""
        cid = d.get("id") or d.get("gid") or d.get("doc_id") or ""
        source = d.get("source", "rmfyalk")
        extra = dict(d.get("extra") or {})
        reserved = {
            "id", "gid", "doc_id", "source", "title", "case_no", "court_case_no",
            "court", "judge_date", "case_type", "keywords", "procedure",
            "key_points", "facts", "reasoning", "ruling", "full_text",
            "related_laws", "url", "extra", "error", "message",
        }
        for k, v in d.items():
            if k not in reserved:
                extra[k] = v
        return cls(
            id=str(cid),
            source=source,
            title=d.get("title", ""),
            case_no=d.get("case_no", ""),
            court_case_no=d.get("court_case_no", ""),
            court=d.get("court", ""),
            judge_date=d.get("judge_date", ""),
            case_type=d.get("case_type", ""),
            keywords=d.get("keywords", ""),
            procedure=d.get("procedure", ""),
            key_points=d.get("key_points", ""),
            facts=d.get("facts", ""),
            reasoning=d.get("reasoning", ""),
            ruling=d.get("ruling", ""),
            full_text=d.get("full_text", ""),
            related_laws=d.get("related_laws", ""),
            url=d.get("url", ""),
            error=d.get("error") or extra.get("error"),
            message=d.get("message") or extra.get("message"),
            extra=extra,
        )


@dataclass
class CaseSearchResult:
    """Normalized search response."""

    source: str
    query: str
    page: int = 1
    size: int = 10
    total: int = 0
    count: int = 0
    records: List[CaseRecord] = field(default_factory=list)
    has_more: bool = False
    degraded: bool = False
    warning: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None

    def to_legacy_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {
            "source": self.source,
            "keyword": self.query,
            "page": self.page,
            "size": self.size,
            "total": self.total,
            "count": self.count,
            "records": [r.to_legacy_dict() for r in self.records],
        }
        if self.degraded:
            res["degraded"] = True
        if self.warning:
            res["warning"] = self.warning
        if self.error:
            res["error"] = self.error
        if self.message:
            res["message"] = self.message
        return res

    @classmethod
    def from_legacy_dict(cls, d: Dict[str, Any]) -> "CaseSearchResult":
        """Reconstruct CaseSearchResult from a legacy dictionary."""
        raw_records = d.get("records", [])
        records = [
            CaseRecord.from_legacy_dict(r) if isinstance(r, dict) else r
            for r in raw_records
        ]
        return cls(
            source=d.get("source", "rmfyalk"),
            query=d.get("keyword") or d.get("query") or "",
            page=d.get("page", 1),
            size=d.get("size", len(records) or 10),
            total=d.get("total", len(records)),
            count=d.get("count", len(records)),
            records=records,
            has_more=d.get("has_more", False),
            degraded=d.get("degraded", False),
            warning=d.get("warning"),
            error=d.get("error"),
            message=d.get("message"),
        )


@dataclass
class CaseQuery:
    """Input query specification."""

    keyword: str = ""
    source: Union[CaseSource, str] = CaseSource.RMFYALK
    page: int = 1
    size: int = 10
    token: Optional[str] = None
    cookie: Optional[str] = None
    lib: str = "cpwsAl_qb"
    no_cache: bool = False
    fallback: bool = True
    timeout: int = 15
