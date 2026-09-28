"""Unified Case Gateway for cn-law-hub."""

from .contracts import (
    CaseDetail,
    CaseQuery,
    CaseRecord,
    CaseSearchResult,
    CaseSource,
)
from .errors import (
    AuthenticationRequiredError,
    CaseGatewayError,
    CaseNotFoundError,
    TokenExpiredError,
    UnknownSourceError,
    WafBlockedError,
)

__all__ = [
    "CaseSource",
    "CaseQuery",
    "CaseRecord",
    "CaseDetail",
    "CaseSearchResult",
    "CaseGatewayError",
    "AuthenticationRequiredError",
    "TokenExpiredError",
    "CaseNotFoundError",
    "WafBlockedError",
    "UnknownSourceError",
]
