from __future__ import annotations

import html
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any, Optional

from bs4 import BeautifulSoup


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_text_file(path: Path) -> str:
    """
    Robust text reader (UTF-8 default with fallback replacement).
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def html_to_text(value: Any) -> str:
    """
    HTML -> plain text + unescape entities.
    Safe for already-plain strings.
    """
    s = safe_str(value)
    if not s:
        return ""
    if "<" not in s and "&" not in s:
        return html.unescape(s).strip()
    soup = BeautifulSoup(s, "html.parser")
    txt = soup.get_text(" ", strip=True)
    return html.unescape(txt).strip()


def http_get(url: str, *, timeout: int = 20) -> str:
    """
    Robust HTTP GET with UA header + charset detection.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; GEOAuditTool/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def http_get_json(url: str, *, timeout: int = 20) -> Any:
    raw = http_get(url, timeout=timeout)
    return json.loads(raw)
