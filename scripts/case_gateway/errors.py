"""Standardized error hierarchy for CaseGateway."""

from typing import Optional


class CaseGatewayError(Exception):
    """Base exception for all case gateway errors."""

    def __init__(self, message: str, source: str = "", error_code: str = "GATEWAY_ERROR"):
        super().__init__(message)
        self.message = message
        self.source = source
        self.error_code = error_code

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "error": self.error_code,
            "message": self.message,
        }


class AuthenticationRequiredError(CaseGatewayError):
    """Raised when authentication credentials (Token/Cookie) are missing."""

    def __init__(self, source: str, message: str):
        super().__init__(message, source=source, error_code="AUTHENTICATION_REQUIRED")


class TokenExpiredError(CaseGatewayError):
    """Raised when authentication credentials have expired or are rejected by the remote server."""

    def __init__(self, source: str, message: str):
        super().__init__(message, source=source, error_code="TOKEN_EXPIRED_OR_INVALID")


class CaseNotFoundError(CaseGatewayError):
    """Raised when a specific case ID or document cannot be found."""

    def __init__(self, source: str, case_id: str, message: Optional[str] = None):
        msg = message or f"未在 {source} 中找到 ID 为 '{case_id}' 的案例。"
        super().__init__(msg, source=source, error_code="CASE_NOT_FOUND")
        self.case_id = case_id


class WafBlockedError(CaseGatewayError):
    """Raised when request is intercepted by remote WAF or CAPTCHA challenge."""

    def __init__(self, source: str, message: str):
        super().__init__(message, source=source, error_code="WAF_OR_SESSION_BLOCKED")


class UnknownSourceError(CaseGatewayError):
    """Raised when an unsupported source identifier is requested."""

    def __init__(self, source: str):
        msg = f"不支持的案例库来源: '{source}'. 支持的选项: rmfyalk, wenshu, court_guiding, auto"
        super().__init__(msg, source=source, error_code="UNKNOWN_SOURCE")
