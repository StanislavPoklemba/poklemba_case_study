from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup


# -----------------------------
# Constants / Regex
# -----------------------------

WORD_RE = re.compile(r"\b\w+\b", flags=re.UNICODE)
# Zadanie: minimálne 3 číselné údaje s jednotkami
UNITS_NUMBER_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s?(mg|g|kg|%|kcal|ml|mcg|gramov|miligramov)\b",
    flags=re.IGNORECASE | re.UNICODE,
)


# "Fluff" phrases in intros that often indicate the answer is NOT direct
BANNED_INTRO_PHRASES = [
    "v tomto článku",
    "v tomto clanku",
    "pozrieme sa",
    "poďme sa pozrieť",
    "podme sa pozriet",
    "dozviete sa",
    "zistíte",
    "zistite",
    "na úvod",
    "na uvod",
    "v dnešnom článku",
    "v dnesnom clanku",
    "predstavíme si",
    "predstavime si",
]

# Definition patterns: "X je", "X znamená", "X predstavuje"
DEFINITION_RE = re.compile(
    r"\b([A-Za-zÀ-ž][A-Za-zÀ-ž\-]{2,})\s+(je|znamená|predstavuje)\b",
    flags=re.IGNORECASE,
)

# Prevent overly generic definitions from passing
DEFINITION_STOPWORDS = {
    "toto", "to", "ten", "tá", "ta", "tieto", "tak", "taky",
    "čas", "cas", "telo", "dnes", "včera", "vcera", "zajtra",
    "život", "zivot", "človek", "clovek", "ľudia", "ludia",
    "pravda", "fakt", "fakty", "informácia", "informacia",
}

# "Sources" section hints
SOURCE_TEXT_RE = re.compile(r"\b(zdroje|references|referencie|štúdie|studie|literatúra|literatura)\b", re.IGNORECASE)

# Whitelisted authoritative sources (can be extended)
SOURCE_DOMAIN_RE = re.compile(
    r"https?://(?:www\.)?("
    r"pubmed\.ncbi\.nlm\.nih\.gov|"
    r"ncbi\.nlm\.nih\.gov|"
    r"examine\.com|"
    r"who\.int|"
    r"nih\.gov|"
    r"cdc\.gov|"
    r"efsa\.europa\.eu|"
    r"cochranelibrary\.com|"
    r"jamanetwork\.com|"
    r"nejm\.org|"
    r"nature\.com|"
    r"science\.org"
    r")\b",
    re.IGNORECASE,
)

# FAQ hints
FAQ_TEXT_RE = re.compile(r"\b(faq|časté otázky|caste otazky|najčastejšie otázky|najcastejsie otazky)\b", re.IGNORECASE)

# Remove noisy containers
NOISE_SELECTORS = ("header", "footer", "nav", "aside", "form", "noscript")


# -----------------------------
# Data structures
# -----------------------------

@dataclass(frozen=True)
class AuditResult:
    # Criteria (10)
    direct_answer: bool
    definition: bool
    headings: bool
    facts: bool
    sources: bool
    faq: bool
    lists: bool
    tables: bool
    word_count_ok: bool
    meta_ok: bool

    # Score + metadata
    score: int
    details: Dict[str, Any]
    recommendations: List[str]


# -----------------------------
# Helpers
# -----------------------------

def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _strip_noise(soup: BeautifulSoup) -> None:
    """
    Remove obvious non-content blocks to reduce false positives and inflated word count.
    """
    for tag_name in NOISE_SELECTORS:
        for node in soup.find_all(tag_name):
            node.decompose()

    # Remove common cookie banners / popups by heuristic attributes
    # (defensive: may not exist)
    for node in soup.find_all(attrs={"aria-modal": "true"}):
        node.decompose()


def _html_to_soup(content_html: str) -> BeautifulSoup:
    html = _safe_str(content_html)
    soup = BeautifulSoup(html, "html.parser")
    _strip_noise(soup)
    return soup


def _plain_text_from_soup(soup: BeautifulSoup) -> str:
    """
    Plain text used for word count, intro, facts, sources text.
    """
    return soup.get_text(" ", strip=True) if soup else ""


def _count_words(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def _first_sentence(text: str) -> str:
    """
    Very lightweight sentence split. Robust to empty input.
    """
    t = (text or "").strip()
    if not t:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", t)
    return (parts[0] if parts else t)[:400].strip()


# -----------------------------
# Criterion checks
# -----------------------------

def check_direct_answer(plain_text: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Criterion #1: Priama odpoveď v úvode (heuristic).
    We try to avoid "fluff intros" and intros that are questions.
    Rules:
      - First sentence exists
      - First sentence not a question
      - No banned fluff phrases in first 150 characters
      - First sentence >= 6 words
    """
    text = (plain_text or "").strip()
    intro_150 = text[:150]
    lowered = intro_150.lower()

    banned_hits = [p for p in BANNED_INTRO_PHRASES if p in lowered]

    first = _first_sentence(text)
    first_words = WORD_RE.findall(first) if first else []
    looks_like_question = first.endswith("?") or ("?" in first[:120])

    passed = bool(first) and not banned_hits and not looks_like_question and (len(first_words) >= 6)
    return passed, {
        "intro_150": intro_150,
        "first_sentence": first,
        "first_sentence_words": len(first_words),
        "banned_hits": banned_hits,
        "looks_like_question": looks_like_question,
    }


def check_definition(plain_text: str, *, title: str = "", strict: bool = False, window_chars: int = 1200) -> Tuple[bool, Dict[str, Any]]:
    """
    Criterion #2: Obsahuje definíciu (heuristic).
    Looks for patterns like: "X je / X znamená / X predstavuje" in the first window_chars.
    Strict:
      - Requires that detected term appears in title (case-insensitive) if title is provided.
    """
    text = (plain_text or "").strip()
    window = text[: max(0, int(window_chars))]

    title_l = (title or "").lower().strip()

    for m in DEFINITION_RE.finditer(window):
        term = (m.group(1) or "").strip()
        if not term:
            continue
        if term.lower() in DEFINITION_STOPWORDS:
            continue
        if strict and title_l and term.lower() not in title_l:
            continue

        return True, {
            "definition_match": m.group(0),
            "term": term,
            "strict": strict,
            "window_chars": window_chars,
        }

    return False, {
        "definition_match": "",
        "term": "",
        "strict": strict,
        "window_chars": window_chars,
    }


def check_h2_headings(soup: BeautifulSoup, *, min_h2: int = 3) -> Tuple[bool, Dict[str, Any]]:
    """
    Criterion #3: Má podnadpisy (H2).
    Default: at least 3 H2 headings.
    """
    h2s = soup.find_all("h2") if soup else []
    count = len(h2s)
    return (count >= int(min_h2)), {"h2_count": count, "min_h2": int(min_h2)}


def check_facts(plain_text: str, *, min_numbers_with_units: int = 3) -> Tuple[bool, Dict[str, Any]]:
    """
    Criterion #4: Obsahuje fakty a čísla (zadanie).
    Pass if at least min_numbers_with_units matches of number+unit exist in text.
    Regex: \\d+\\s?(mg|g|kg|%|kcal|ml|mcg|gramov|miligramov)
    """
    matches = UNITS_NUMBER_RE.findall(plain_text or "")
    count = len(matches)
    return (count >= int(min_numbers_with_units)), {
        "numbers_with_units_found": count,
        "min_numbers_with_units": int(min_numbers_with_units),
        "units_regex": r"\\d+\\s?(mg|g|kg|%|kcal|ml|mcg|gramov|miligramov)",
    }


def check_sources(plain_text: str, soup: BeautifulSoup, *, strict: bool = False) -> Tuple[bool, Dict[str, Any]]:
    """
    Criterion #5: Má zdroje.
    Non-strict:
      - has source section hint OR whitelisted source link
    Strict:
      - requires whitelisted link OR (source section hint AND at least one http(s) link)
    """
    text = plain_text or ""
    has_source_section = SOURCE_TEXT_RE.search(text) is not None

    hrefs: List[str] = []
    if soup:
        for a in soup.find_all("a", href=True):
            hrefs.append(_safe_str(a.get("href")))

    joined = " ".join(hrefs)
    whitelisted = SOURCE_DOMAIN_RE.findall(joined)
    whitelisted_count = len(whitelisted)

    http_links_count = sum(1 for h in hrefs if h.lower().startswith(("http://", "https://")))

    if strict:
        passed = (whitelisted_count > 0) or (has_source_section and http_links_count > 0)
    else:
        passed = has_source_section or (whitelisted_count > 0)

    return passed, {
        "has_source_section": has_source_section,
        "whitelisted_links_count": whitelisted_count,
        "http_links_count": http_links_count,
        "strict": strict,
    }


def check_faq(plain_text: str, soup: BeautifulSoup) -> Tuple[bool, Dict[str, Any]]:
    """
    Criterion #6: FAQ sekcia.
    Heuristic:
      - textual hint "FAQ / časté otázky" OR
      - has <dl> (definition list) OR
      - has JSON-LD schema for FAQPage
    """
    text = plain_text or ""
    text_hint = FAQ_TEXT_RE.search(text) is not None

    has_dl = bool(soup.find("dl")) if soup else False

    has_faq_schema = False
    if soup:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            content = _safe_str(script.string)
            if "FAQPage" in content:
                has_faq_schema = True
                break

    passed = text_hint or has_dl or has_faq_schema
    return passed, {"text_hint": text_hint, "has_dl": has_dl, "has_faq_schema": has_faq_schema}


def check_lists(soup: BeautifulSoup, *, min_lists: int = 1) -> Tuple[bool, Dict[str, Any]]:
    """
    Criterion #7: Obsahuje zoznamy.
    Pass if at least min_lists <ul>/<ol>.
    """
    if not soup:
        return False, {"list_count": 0, "min_lists": int(min_lists)}
    ul_count = len(soup.find_all("ul"))
    ol_count = len(soup.find_all("ol"))
    count = ul_count + ol_count
    return (count >= int(min_lists)), {"list_count": count, "ul": ul_count, "ol": ol_count, "min_lists": int(min_lists)}


def check_tables(soup: BeautifulSoup, *, min_tables: int = 1) -> Tuple[bool, Dict[str, Any]]:
    """
    Criterion #8: Obsahuje tabuľky.
    Pass if at least min_tables <table>.
    """
    if not soup:
        return False, {"table_count": 0, "min_tables": int(min_tables)}
    count = len(soup.find_all("table"))
    return (count >= int(min_tables)), {"table_count": count, "min_tables": int(min_tables)}


def check_word_count(plain_text: str, *, min_words: int = 500) -> Tuple[bool, Dict[str, Any]]:
    """
    Criterion #9: Dostatočná dĺžka (zadanie).
    Pass if word count >= 500 (no upper bound in assignment).
    """
    wc = _count_words(plain_text)
    passed = wc >= int(min_words)
    return passed, {"word_count": wc, "min_words": int(min_words)}


def check_meta_description(meta_description: str, *, min_len: int = 120, max_len: int = 160) -> Tuple[bool, Dict[str, Any]]:
    """
    Criterion #10: Meta description má vhodnú dĺžku.
    Default: 120–160 znakov (heuristic).
    """
    md = (meta_description or "").strip()
    n = len(md)
    passed = (n >= int(min_len)) and (n <= int(max_len))
    return passed, {"meta_len": n, "min_len": int(min_len), "max_len": int(max_len)}


# -----------------------------
# Recommendations
# -----------------------------

RECOMMENDATIONS_TEXT: Dict[str, str] = {
    "direct_answer": "Pridaj priamu odpoveď hneď do úvodu (1–2 vety), bez vaty a bez otázok.",
    "definition": "Doplň stručnú definíciu hlavného pojmu (napr. „X je … / X znamená …“), ideálne v úvode.",
    "headings": "Pridaj viac H2 podnadpisov (článok sa bude lepšie skenovať a segmentovať).",
    "facts": "Doplň merateľné fakty (čísla, percentá, dávkovanie, štúdie), aby bol obsah konkrétnejší.",
    "sources": "Doplň citácie zdrojov (odkazy) alebo sekciu „Zdroje/References/Štúdie“ s reálnymi linkami.",
    "faq": "Pridaj FAQ blok (FAQ/Časté otázky) – ideálne s konkrétnymi otázkami a odpoveďami.",
    "lists": "Pridaj zoznamy (<ul>/<ol>) pre lepšiu čitateľnosť (napr. kroky, tipy, výhody/nevýhody).",
    "tables": "Ak dáva zmysel, pridaj tabuľku (porovnanie, dávkovanie, prehľad) pre rýchle skenovanie.",
   "word_count_ok": "Doplň obsah – článok má mať aspoň 500 slov (word count z čistého textu bez HTML).",
    "meta_ok": "Uprav meta description na ~120–160 znakov (jasne, s benefitom a kľúčovým pojmom).",
}


# -----------------------------
# Public API
# -----------------------------

def analyze_article(
    content_html: str,
    meta_description: str,
    *,
    title: str = "",
    strict: bool = False,
) -> AuditResult:
    """
    Runs all 10 GEO checks and returns structured result.
    Defensive by design: never raises on malformed HTML; returns failed checks instead.
    """
    try:
        soup = _html_to_soup(content_html)
    except Exception:
        soup = BeautifulSoup("", "html.parser")

    try:
        plain = _plain_text_from_soup(soup)
    except Exception:
        plain = ""

    # Run checks (10)
    direct_ok, direct_d = check_direct_answer(plain)
    def_ok, def_d = check_definition(plain, title=title, strict=strict)
    h2_ok, h2_d = check_h2_headings(soup)
    facts_ok, facts_d = check_facts(plain)
    sources_ok, sources_d = check_sources(plain, soup, strict=strict)
    faq_ok, faq_d = check_faq(plain, soup)
    lists_ok, lists_d = check_lists(soup)
    tables_ok, tables_d = check_tables(soup)
    wc_ok, wc_d = check_word_count(plain)
    meta_ok, meta_d = check_meta_description(meta_description)

    # Score: sum of booleans (deterministic, 0–10)
    flags = [
        direct_ok,
        def_ok,
        h2_ok,
        facts_ok,
        sources_ok,
        faq_ok,
        lists_ok,
        tables_ok,
        wc_ok,
        meta_ok,
    ]
    score = sum(1 for x in flags if x)

    details: Dict[str, Any] = {
        "direct_answer": direct_d,
        "definition": def_d,
        "headings": h2_d,
        "facts": facts_d,
        "sources": sources_d,
        "faq": faq_d,
        "lists": lists_d,
        "tables": tables_d,
        "word_count_ok": wc_d,
        "meta_ok": meta_d,
    }

    recommendations: List[str] = []
    if not direct_ok:
        recommendations.append(RECOMMENDATIONS_TEXT["direct_answer"])
    if not def_ok:
        recommendations.append(RECOMMENDATIONS_TEXT["definition"])
    if not h2_ok:
        recommendations.append(RECOMMENDATIONS_TEXT["headings"])
    if not facts_ok:
        recommendations.append(RECOMMENDATIONS_TEXT["facts"])
    if not sources_ok:
        recommendations.append(RECOMMENDATIONS_TEXT["sources"])
    if not faq_ok:
        recommendations.append(RECOMMENDATIONS_TEXT["faq"])
    if not lists_ok:
        recommendations.append(RECOMMENDATIONS_TEXT["lists"])
    if not tables_ok:
        recommendations.append(RECOMMENDATIONS_TEXT["tables"])
    if not wc_ok:
        recommendations.append(RECOMMENDATIONS_TEXT["word_count_ok"])
    if not meta_ok:
        recommendations.append(RECOMMENDATIONS_TEXT["meta_ok"])

    return AuditResult(
        direct_answer=direct_ok,
        definition=def_ok,
        headings=h2_ok,
        facts=facts_ok,
        sources=sources_ok,
        faq=faq_ok,
        lists=lists_ok,
        tables=tables_ok,
        word_count_ok=wc_ok,
        meta_ok=meta_ok,
        score=score,
        details=details,
        recommendations=recommendations,
    )
