from __future__ import annotations

import argparse
import html
import json
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from bs4 import BeautifulSoup

from .analyzer import analyze_article
from .reporter import build_report_row, write_csv_report
from .html_reporter import write_html_report


# -----------------------------
# Data model
# -----------------------------

@dataclass(frozen=True)
class Article:
    url: str
    title: str
    content_html: str
    meta_description: str


# -----------------------------
# Console helpers
# -----------------------------

def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def die(msg: str, exit_code: int = 2) -> None:
    eprint(f"ERROR: {msg}")
    raise SystemExit(exit_code)


# -----------------------------
# Safe conversion / parsing
# -----------------------------

def safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # fallback for weird encodings
        return path.read_text(encoding="utf-8", errors="replace")


def html_to_text(value: Any) -> str:
    """
    Converts HTML-ish strings to plain text and unescapes entities.
    Safe for already-plain strings.
    """
    s = safe_str(value)
    if not s:
        return ""
    # Quick path: still unescape entities
    if "<" not in s and "&" not in s:
        return html.unescape(s).strip()

    soup = BeautifulSoup(s, "html.parser")
    txt = soup.get_text(" ", strip=True)
    return html.unescape(txt).strip()


def pick_main_content_html(soup: BeautifulSoup) -> str:
    """
    Best-effort extraction of main article content:
    - prefer <article>, then <main>, then <body>, otherwise full doc
    Keeps HTML because analyzer relies on tags (<h2>, <ul>, <table>...).
    """
    for tag_name in ("article", "main"):
        node = soup.find(tag_name)
        if node and node.get_text(" ", strip=True):
            return str(node)

    if soup.body and soup.body.get_text(" ", strip=True):
        return str(soup.body)

    return str(soup)


# -----------------------------
# HTTP
# -----------------------------

def http_get(url: str, *, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; GEOAuditTool/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def http_get_json(url: str, *, timeout: int = 20) -> Any:
    raw = http_get(url, timeout=timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as ex:
        raise RuntimeError(f"Invalid JSON from {url}: {ex}") from ex


# -----------------------------
# URL mode helpers
# -----------------------------

def extract_title_meta_and_content(html_str: str) -> Tuple[str, str, str]:
    soup = BeautifulSoup(html_str, "html.parser")

    # meta description
    meta = soup.find("meta", attrs={"name": "description"})
    meta_description = meta.get("content", "").strip() if meta else ""

    # pick main content HTML
    content_html = pick_main_content_html(soup)

    # title: prefer H1 in content, fallback global H1, fallback <title>
    main_soup = BeautifulSoup(content_html, "html.parser")
    h1 = main_soup.find("h1") or soup.find("h1")
    title = (h1.get_text(" ", strip=True) if h1 else "").strip()
    if not title:
        t = soup.find("title")
        title = (t.get_text(" ", strip=True) if t else "").strip()

    return title, meta_description, content_html


def load_articles_from_urls_file(path: Path) -> List[Article]:
    text = read_text_file(path)
    urls = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    if not urls:
        return []

    articles: List[Article] = []
    for url in urls:
        try:
            html_str = http_get(url)
            title, meta_description, content_html = extract_title_meta_and_content(html_str)
            articles.append(
                Article(
                    url=url,
                    title=title or url,
                    content_html=content_html,
                    meta_description=meta_description,
                )
            )
        except Exception as ex:
            # keep a row in report to avoid silent drops
            eprint(f"WARNING: failed to fetch {url}: {ex}")
            articles.append(
                Article(
                    url=url,
                    title=f"(fetch error) {url}",
                    content_html="",
                    meta_description="",
                )
            )
    return articles


# -----------------------------
# JSON / WP normalization
# -----------------------------

def normalize_article(obj: Dict[str, Any]) -> Article:
    """
    Normalize either:
      - mock JSON schema: url, title, content_html, meta_description
      - WordPress REST API post object: link, title.rendered, content.rendered, yoast_head_json.description (optional)
    """
    url = safe_str(obj.get("url")) or safe_str(obj.get("link"))

    # Title
    if isinstance(obj.get("title"), dict):
        title = html_to_text(obj["title"].get("rendered"))
    else:
        title = html_to_text(obj.get("title"))

    # Content HTML (keep HTML!)
    if isinstance(obj.get("content"), dict):
        content_html = safe_str(obj["content"].get("rendered"))
    else:
        content_html = safe_str(obj.get("content_html")) or safe_str(obj.get("content"))

    # Meta description
    meta_description = html_to_text(obj.get("meta_description"))

    # WP Yoast SEO
    if not meta_description:
        yoast = obj.get("yoast_head_json")
        if isinstance(yoast, dict):
            meta_description = html_to_text(yoast.get("description"))

    # fallback: excerpt.rendered (often HTML)
    if not meta_description and isinstance(obj.get("excerpt"), dict):
        meta_description = html_to_text(obj["excerpt"].get("rendered"))

    if not url:
        raise ValueError("Article missing url/link")

    if not title:
        title = "(no title)"

    if content_html is None:
        content_html = ""

    return Article(
        url=url.strip(),
        title=title.strip(),
        content_html=content_html,
        meta_description=(meta_description or "").strip(),
    )


def load_articles_from_json(path: Path) -> List[Article]:
    raw = read_text_file(path)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as ex:
        raise RuntimeError(f"Invalid JSON file {path}: {ex}") from ex

    if isinstance(data, dict) and "articles" in data:
        data = data["articles"]

    if not isinstance(data, list):
        raise RuntimeError("JSON input must be a list of articles (or dict with 'articles').")

    articles: List[Article] = []
    for i, obj in enumerate(data):
        if not isinstance(obj, dict):
            eprint(f"WARNING: skipping non-object item at index {i}")
            continue
        try:
            articles.append(normalize_article(obj))
        except Exception as ex:
            eprint(f"WARNING: bad article at index {i}: {ex}")
            # keep placeholder to preserve visibility
            articles.append(
                Article(
                    url=f"(invalid) index={i}",
                    title=f"(invalid article) index={i}",
                    content_html="",
                    meta_description="",
                )
            )
    return articles


def _wp_build_url(base: str, *, per_page: int, page: int) -> str:
    """
    Builds wp-json/wp/v2/posts endpoint with paging.
    Accepts either direct endpoint or a site base.
    """
    b = base.strip()
    if not b:
        raise ValueError("Empty WordPress base URL/endpoint")

    # If user passed a site root, expand to wp endpoint
    if "/wp-json/" not in b:
        b = b.rstrip("/") + "/wp-json/wp/v2/posts"

    # Ensure query parameters
    parts = urllib.parse.urlsplit(b)
    q = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
    q["per_page"] = [str(per_page)]
    q["page"] = [str(page)]
    # you can add additional filters here if needed (e.g. status=publish)
    new_query = urllib.parse.urlencode(q, doseq=True)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def load_articles_from_wp(endpoint_or_site: str, *, max_pages: int = 50, per_page: int = 100, sleep_s: float = 0.2) -> List[Article]:
    """
    Loads WordPress posts via REST API with paging.
    Defensive:
      - stops when page returns empty list
      - respects max_pages to avoid infinite loops
      - per-page clamped to WP typical range [1..100]
    """
    per_page = max(1, min(int(per_page), 100))
    max_pages = max(1, int(max_pages))
    sleep_s = max(0.0, float(sleep_s))

    articles: List[Article] = []

    for page in range(1, max_pages + 1):
        url = _wp_build_url(endpoint_or_site, per_page=per_page, page=page)
        try:
            data = http_get_json(url)
        except Exception as ex:
            eprint(f"WARNING: failed WP fetch page {page}: {ex}")
            break

        if not isinstance(data, list):
            eprint(f"WARNING: WP response is not a list on page {page}; stopping.")
            break

        if not data:
            break

        for i, obj in enumerate(data):
            if not isinstance(obj, dict):
                continue
            try:
                articles.append(normalize_article(obj))
            except Exception as ex:
                eprint(f"WARNING: bad WP post on page {page} idx {i}: {ex}")
                articles.append(
                    Article(
                        url=f"(invalid) wp_page={page} idx={i}",
                        title=f"(invalid wp post) page={page} idx={i}",
                        content_html="",
                        meta_description="",
                    )
                )

        if sleep_s > 0:
            time.sleep(sleep_s)

    return articles


# -----------------------------
# CLI
# -----------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="geo-audit",
        description="GEO Audit Tool – audits articles for 10 GEO criteria and outputs CSV/HTML reports.",
    )
    p.add_argument("--source", choices=["json", "wp", "urls"], required=True, help="Input source type.")
    p.add_argument("--input", required=True, help="Path to JSON/URLs file OR WP endpoint/site URL.")
    p.add_argument("--output", default="output/report.csv", help="Output CSV path.")
    p.add_argument("--html", default="", help="Optional HTML report output path (e.g. output/report.html).")
    p.add_argument("--page-size", type=int, default=10, help="HTML report page size (default 10).")
    p.add_argument("--strict", action="store_true", help="Enable stricter heuristics to reduce false positives.")

    # WP options
    p.add_argument("--wp-max-pages", type=int, default=50, help="Max WP pages to fetch (safety limit).")
    p.add_argument("--wp-per-page", type=int, default=100, help="WP per_page (1..100).")
    p.add_argument("--wp-sleep", type=float, default=0.2, help="Sleep between WP page requests (seconds).")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    out_csv = Path(args.output)
    out_html = Path(args.html) if args.html else None

    # Load articles
    try:
        if args.source == "json":
            in_path = Path(args.input)
            if not in_path.exists():
                die(f"Input JSON not found: {in_path}")
            articles = load_articles_from_json(in_path)

        elif args.source == "urls":
            in_path = Path(args.input)
            if not in_path.exists():
                die(f"Input URLs file not found: {in_path}")
            articles = load_articles_from_urls_file(in_path)

        elif args.source == "wp":
            # input is endpoint or site
            endpoint = args.input
            articles = load_articles_from_wp(
                endpoint,
                max_pages=args.wp_max_pages,
                per_page=args.wp_per_page,
                sleep_s=args.wp_sleep,
            )
        else:
            die(f"Unknown source: {args.source}")
    except SystemExit:
        raise
    except Exception as ex:
        die(str(ex))

    # Analyze and build rows (never crash per article)
    rows: List[Dict[str, Any]] = []
    for idx, a in enumerate(articles):
        try:
            res = analyze_article(a.content_html, a.meta_description, title=a.title, strict=args.strict)
            rows.append(build_report_row(a.url, a.title, res))
        except Exception as ex:
            eprint(f"WARNING: analysis failed at idx={idx} url={a.url}: {ex}")
            rows.append(
                {
                    "url": a.url,
                    "title": a.title,
                    "score": 0,
                    "direct_answer": 0,
                    "definition": 0,
                    "headings": 0,
                    "facts": 0,
                    "sources": 0,
                    "faq": 0,
                    "lists": 0,
                    "tables": 0,
                    "word_count_ok": 0,
                    "meta_ok": 0,
                    "word_count": 0,
                    "h2_count": 0,
                    "list_count": 0,
                    "table_count": 0,
                    "meta_len": 0,
                    "recommendations": f"Analysis error: {ex}",
                }
            )

    # Output CSV (always)
    try:
        write_csv_report(out_csv, rows)
        print(f"CSV report written: {out_csv}")
    except Exception as ex:
        die(f"Failed to write CSV report: {ex}")

    # Optional HTML report
    if out_html is not None:
        try:
            write_html_report(out_html, rows, page_size=args.page_size)
            print(f"HTML report written: {out_html}")
        except Exception as ex:
            die(f"Failed to write HTML report: {ex}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
