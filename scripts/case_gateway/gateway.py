"""Deep CaseGateway module."""

import logging
import re
from typing import Any, Dict, Optional, Union

from .contracts import (
    CaseDetail,
    CaseQuery,
    CaseRecord,
    CaseSearchResult,
    CaseSource,
)
from .errors import UnknownSourceError
from .provider import CaseProvider
from .providers.court_guiding_provider import CourtGuidingProvider
from .providers.rmfyalk_provider import RmfyalkProvider
from .providers.wenshu_provider import WenshuProvider

_logger = logging.getLogger("case_gateway")


class CaseGateway:
    """Unified, deep judicial case retrieval gateway.

    Encapsulates multi-source routing, provider adapters, credential checking,
    graceful degradation, and legacy serialization behind two small methods:
    `search(query)` and `get_detail(id_or_url)`.
    """

    SOURCE_ALIASES = {
        "rmfyalk": "rmfyalk",
        "case_db": "rmfyalk",
        "al": "rmfyalk",
        "alk": "rmfyalk",
        "wenshu": "wenshu",
        "cpws": "wenshu",
        "judgements": "wenshu",
        "court_guiding": "court_guiding",
        "guiding": "court_guiding",
        "zdxal": "court_guiding",
        "auto": "auto",
    }

    def __init__(self):
        self._providers: Dict[str, CaseProvider] = {}
        # Register default built-in providers
        self.register_provider("rmfyalk", RmfyalkProvider())
        self.register_provider("wenshu", WenshuProvider())
        self.register_provider("court_guiding", CourtGuidingProvider())

    def register_provider(self, name: str, provider: CaseProvider):
        """Register or replace a provider adapter (useful for testing and extensions)."""
        self._providers[name.lower()] = provider

    def get_provider(self, name: str) -> Optional[CaseProvider]:
        normalized = self.canonicalize_source(name)
        return self._providers.get(normalized)

    def canonicalize_source(self, source: str) -> str:
        s = str(source or "rmfyalk").strip().lower()
        return self.SOURCE_ALIASES.get(s, s)

    def search(
        self,
        query: Union[str, CaseQuery],
        source: str = "rmfyalk",
        token: Optional[str] = None,
        cookie: Optional[str] = None,
        page: int = 1,
        size: int = 10,
        lib: str = "cpwsAl_qb",
        no_cache: bool = False,
        fallback: bool = True,
        **kwargs,
    ) -> CaseSearchResult:
        """Search judicial cases across sources with automatic degradation."""
        if isinstance(query, CaseQuery):
            q = query
        else:
            q = CaseQuery(
                keyword=str(query or ""),
                source=source,
                page=page,
                size=size,
                token=token,
                cookie=cookie,
                lib=lib,
                no_cache=no_cache,
                fallback=fallback,
            )

        src = self.canonicalize_source(q.source)

        if src not in self._providers and src != "auto":
            return CaseSearchResult(
                source=q.source,
                query=q.keyword,
                error="UNKNOWN_SOURCE",
                message=f"不支持的案例库来源: '{q.source}'. 支持的选项: rmfyalk, wenshu, court_guiding, auto",
            )

        # Handle 'auto' source: pick best available provider
        if src == "auto":
            rmfyalk = self._providers.get("rmfyalk")
            if rmfyalk and rmfyalk.is_available(token=q.token, cookie=q.cookie):
                res = rmfyalk.search(q)
                if not res.error:
                    return res

            guiding = self._providers.get("court_guiding")
            if guiding:
                res = guiding.search(q)
                res.degraded = True
                res.warning = "未配置案例库凭证，已自动检索最高法公开指导性案例库（免密）。"
                return res

            return CaseSearchResult(
                source="auto",
                query=q.keyword,
                error="NO_PROVIDER_AVAILABLE",
                message="没有可用且已认证的案例数据源。",
            )

        provider = self._providers[src]

        # Check availability before executing
        if not provider.is_available(token=q.token, cookie=q.cookie) and q.fallback and src != "court_guiding":
            guiding = self._providers.get("court_guiding")
            if guiding:
                _logger.info("Provider '%s' unavailable, falling back to 'court_guiding'", src)
                fallback_res = guiding.search(q)
                fallback_res.degraded = True
                fallback_res.warning = (
                    f"数据源 '{src}' 未配置有效凭证（Token/Cookie），"
                    f"已自动为您兜底检索最高法公开指导性案例（共 {fallback_res.total} 篇）。"
                )
                return fallback_res

        res = provider.search(q)

        # Fallback on auth failure if enabled
        if res.error in ("AUTHENTICATION_REQUIRED", "TOKEN_EXPIRED_OR_INVALID") and q.fallback and src != "court_guiding":
            guiding = self._providers.get("court_guiding")
            if guiding:
                _logger.info("Provider '%s' failed auth, falling back to 'court_guiding'", src)
                fallback_res = guiding.search(q)
                fallback_res.degraded = True
                fallback_res.warning = (
                    f"数据源 '{src}' 认证失败（{res.error}），"
                    f"已自动为您兜底检索最高法公开指导性案例。如需查阅全量案库，请配置相关凭证。\n"
                    f"{res.message or ''}"
                )
                return fallback_res

        return res

    def get_detail(
        self,
        case_id: str,
        source: str = "auto",
        token: Optional[str] = None,
        cookie: Optional[str] = None,
        no_cache: bool = False,
        **kwargs,
    ) -> CaseDetail:
        """Fetch case detail, automatically routing by URL or ID format when source='auto'."""
        cid = str(case_id or "").strip()
        src = self.canonicalize_source(source)

        if src == "auto":
            src = self._detect_source_from_id(cid)

        provider = self._providers.get(src)
        if not provider:
            return CaseDetail(
                id=cid,
                source=src,
                title="",
                extra={"error": "UNKNOWN_SOURCE", "message": f"不支持的案例数据源: '{src}'"},
            )

        q = CaseQuery(token=token, cookie=cookie, no_cache=no_cache)
        return provider.get_detail(cid, query=q)

    def _detect_source_from_id(self, cid: str) -> str:
        """Heuristically determine case source from ID or URL."""
        if "court.gov.cn/shenpan/" in cid:
            return "court_guiding"
        if "wenshu.court.gov.cn" in cid or "docId=" in cid:
            return "wenshu"
        if "rmfyalk.court.gov.cn" in cid:
            return "rmfyalk"
        if len(cid) == 44 and cid.endswith("="):
            return "rmfyalk"
        # Default fallback to rmfyalk
        return "rmfyalk"


_default_gateway: Optional[CaseGateway] = None


def get_default_gateway() -> CaseGateway:
    global _default_gateway
    if _default_gateway is None:
        _default_gateway = CaseGateway()
    return _default_gateway
