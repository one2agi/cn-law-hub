"""Text and filename utility functions."""

import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .constants import EM_TAG_RE, SAFE_CHAR_RE, SPACE_RE


def sanitize_filename(name: str, fallback: str = "unnamed") -> str:
    name = SAFE_CHAR_RE.sub("_", name).strip().rstrip(".")
    return name or fallback


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def clean_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " | ".join(clean_text(item) for item in value if clean_text(item))
    text = str(value)
    text = EM_TAG_RE.sub("", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</?p\b[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def decode_filename_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    values = parse_qs(parsed.query).get("response-content-disposition")
    if not values:
        return None
    disposition = values[0]
    match = re.search(r'filename="([^"]+)"', disposition, re.IGNORECASE)
    if not match:
        return None
    filename = match.group(1)
    try:
        filename = unquote(unquote(filename))
    except Exception:
        filename = unquote(filename)
    return sanitize_filename(filename)


def redact_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def format_request_exception(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    url = getattr(response, "url", "")
    status_code = getattr(response, "status_code", None)
    if url:
        redacted = redact_url(url)
        if status_code is not None:
            return f"{exc.__class__.__name__}: status={status_code} url={redacted}"
        return f"{exc.__class__.__name__}: url={redacted}"
    return str(exc)


def extract_year(value: str) -> str:
    match = re.search(r"(\d{4})", clean_text(value))
    return match.group(1) if match else "未知"


def create_crawler_headers(accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8") -> dict:
    from .constants import DEFAULT_USER_AGENT
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": accept,
    }


def classify_legal_document_type(title: str) -> str:
    """Classify document type based on title patterns.
    Returns: 'amendment_decision', 'judicial_reply', 'judicial_interpretation', 'statute', or 'full_text'.
    """
    clean_t = clean_text(title)
    if ("修改" in clean_t and "决定" in clean_t) or "修正案" in clean_t:
        return "amendment_decision"
    if "批复" in clean_t:
        return "judicial_reply"

    base_t = re.sub(r"[（\(].*?[）\)]", "", clean_t).strip()
    if (
        any(k in clean_t for k in ["司法解释", "司法观点", "会议纪要", "纪要"])
        or (("最高人民法院" in clean_t or "最高人民检察院" in clean_t) and any(clean_t.endswith(s) or base_t.endswith(s) for s in ["规定", "解释", "通知", "意见", "办法"]))
        or base_t.endswith(("规定", "解释"))
    ):
        return "judicial_interpretation"

    if any(base_t.endswith(s) for s in ["法", "典", "条例", "通则", "准则"]):
        return "statute"

    return "full_text"


def get_amendment_warning(title: str) -> str | None:
    """Return a cautionary warning for legal professionals if the document is an amendment decision."""
    doc_type = classify_legal_document_type(title)
    if doc_type == "amendment_decision":
        return (
            "⚠️【专业律师提示】当前文档为《修改决定》（法规补丁文件），仅包含修订条文，"
            "可能存在条款增删导致的后续条号顺移。在撰写诉讼文书时，请结合全国人大库(NPC)现行有效整合版本核对最终条号，"
            "防止因条号位移导致法庭援引错误。"
        )
    return None




