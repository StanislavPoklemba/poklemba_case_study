from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .analyzer import AuditResult


# -----------------------------
# Stable CSV schema
# -----------------------------

CSV_BASE_HEADER: List[str] = [
    "url",
    "title",
    "score",
    "direct_answer",
    "definition",
    "headings",
    "facts",
    "sources",
    "faq",
    "lists",
    "tables",
    "word_count_ok",
    "meta_ok",
    "recommendations",
    "word_count",
    "h2_count",
    "list_count",
    "table_count",
    "meta_len",
]



# -----------------------------
# Helpers
# -----------------------------

def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _as_bool01(value: Any) -> int:
    return 1 if bool(value) else 0


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _join_recommendations(recs: Any) -> str:
    """
    Store recommendations as a single cell to keep CSV flat.
    """
    if not recs:
        return ""
    if isinstance(recs, (list, tuple)):
        # Avoid line breaks that can confuse some CSV consumers
        parts = [_safe_str(x).replace("\n", " ").replace("\r", " ").strip() for x in recs]
        parts = [p for p in parts if p]
        return " | ".join(parts)
    return _safe_str(recs).replace("\n", " ").replace("\r", " ").strip()


def _compute_header(rows_list: List[Dict[str, Any]]) -> List[str]:
    """
    Deterministic CSV header:
    - start with CSV_BASE_HEADER
    - append any extra keys found in rows (future-proof)
    """
    header = list(CSV_BASE_HEADER)
    extras: List[str] = []
    for row in rows_list:
        for k in row.keys():
            if k not in header and k not in extras:
                extras.append(k)
    return header + extras


def _details_get_int(details: Mapping[str, Any], key: str, field: str, default: int = 0) -> int:
    """
    Extract nested integer fields from AuditResult.details safely.
    Example: details["word_count_ok"]["word_count"]
    """
    try:
        d = details.get(key, {})
        if isinstance(d, Mapping):
            v = d.get(field, default)
            return int(v) if v is not None else default
    except Exception:
        pass
    return default


# -----------------------------
# Public API
# -----------------------------

def build_report_row(url: str, title: str, result: AuditResult) -> Dict[str, Any]:
    """
    Converts AuditResult into a flat dict for CSV/HTML reporting.
    Safe against missing/partial detail keys.
    """
    details = result.details or {}

    row: Dict[str, Any] = {
        "url": _safe_str(url).strip(),
        "title": _safe_str(title).strip(),
        "score": int(result.score),

        # 10 criteria as 0/1 (CSV-friendly)
        "direct_answer": _as_bool01(result.direct_answer),
        "definition": _as_bool01(result.definition),
        "headings": _as_bool01(result.headings),
        "facts": _as_bool01(result.facts),
        "sources": _as_bool01(result.sources),
        "faq": _as_bool01(result.faq),
        "lists": _as_bool01(result.lists),
        "tables": _as_bool01(result.tables),
        "word_count_ok": _as_bool01(result.word_count_ok),
        "meta_ok": _as_bool01(result.meta_ok),

        # Common metrics (safe extraction)
        "word_count": _details_get_int(details, "word_count_ok", "word_count", default=0),
        "h2_count": _details_get_int(details, "headings", "h2_count", default=0),
        "list_count": _details_get_int(details, "lists", "list_count", default=0),
        "table_count": _details_get_int(details, "tables", "table_count", default=0),
        "meta_len": _details_get_int(details, "meta_ok", "meta_len", default=0),

        "recommendations": _join_recommendations(result.recommendations),
    }

    return row


def write_csv_report(
    output_path: Path,
    rows: Iterable[Dict[str, Any]],
    *,
    delimiter: str = ",",
) -> None:
    """
    Writes a CSV report.
    Guarantees:
    - file is created even if rows is empty
    - header is always present
    - stable base columns + future-proof extra columns
    - UTF-8-SIG encoding for Excel compatibility (diacritics)
    """
    ensure_parent_dir(output_path)

    rows_list = list(rows)
    header = _compute_header(rows_list)

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=header,
            delimiter=delimiter,
            quotechar='"',
            quoting=csv.QUOTE_MINIMAL,
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows_list:
            # Ensure no raw newlines in cells that can break some CSV readers
            safe_row = {k: (_safe_str(v).replace("\n", " ").replace("\r", " ").strip()) for k, v in row.items()}
            writer.writerow(safe_row)
