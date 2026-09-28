"""Base CaseProvider seam interface."""

from abc import ABC, abstractmethod
from typing import Optional
from .contracts import CaseDetail, CaseQuery, CaseSearchResult


class CaseProvider(ABC):
    """Abstract provider adapter for judicial case data sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier: 'rmfyalk', 'wenshu', 'court_guiding'."""
        pass

    @abstractmethod
    def is_available(self, token: Optional[str] = None, cookie: Optional[str] = None) -> bool:
        """Check if provider has required credentials or network dependencies."""
        pass

    @abstractmethod
    def search(self, query: CaseQuery) -> CaseSearchResult:
        """Execute case search against this provider."""
        pass

    @abstractmethod
    def get_detail(self, case_id: str, query: Optional[CaseQuery] = None) -> CaseDetail:
        """Fetch full case detail from this provider."""
        pass
