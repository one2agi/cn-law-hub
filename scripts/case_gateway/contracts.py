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
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Convert to legacy format expected by case_search and mcp_server."""
        res = asdict(self)
        if self.source == "rmfyalk":
            res["gid"] = self.id
        elif self.source == "wenshu":
            res["doc_id"] = self.id
        return res


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
