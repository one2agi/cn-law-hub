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
from .gateway import CaseGateway, get_default_gateway
from .provider import CaseProvider

__all__ = [
    "CaseGateway",
    "get_default_gateway",
    "CaseProvider",
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
