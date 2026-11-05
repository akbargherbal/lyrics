"""Quality analysis, Arabic normalization and scoring for lyrics candidates."""

from __future__ import annotations

import html
import re
import unicodedata

TASHKEEL_RE = re.compile(r"[\u064B-\u065F\u0670\u0640]")
BIDI_RE = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
HTML_TAG_RE = re.compile(r"<[^>]+>")
ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
LATIN_RE = re.compile(r"[A-Za-z]")
SPACE_RE = re.compile(r"[ \t]+")
LRC_TIMESTAMP_RE = re.compile(r"\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]")
LRC_META_RE = re.compile(r"^\[(ar|al|ti|au|by|offset|re|ve|length):.*\]$", re.IGNORECASE)


def clean_text(text: str | None) -> str:
    """Remove HTML, bidi controls, weird spaces and normalize line endings."""
    if not text:
        return ""
    value = html.unescape(str(text))
    value = HTML_TAG_RE.sub(" ", value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = BIDI_RE.sub("", value)
    value = value.replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")
    value = SPACE_RE.sub(" ", value)

    lines: list[str] = []
    blank = 0
    for raw_line in value.split("\n"):
        line = raw_line.strip()
        if line:
            lines.append(line)
            blank = 0
        else:
            if blank == 0:
                lines.append("")
            blank += 1
    return "\n".join(lines).strip()


def strip_lrc(text: str | None) -> str:
    """Return lyric text without LRC timestamps/metadata tags."""
    lines = []
    for line in (text or "").splitlines():
        line = LRC_META_RE.sub("", line).strip()
        line = LRC_TIMESTAMP_RE.sub("", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def normalize_arabic(text: str | None) -> str:
    """Normalize Arabic for matching only (not for display)."""
    value = unicodedata.normalize("NFKC", text or "")
    value = TASHKEEL_RE.sub("", value)
    value = (
        value.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )
    value = value.lower()
    value = re.sub(r"[^\w\u0600-\u06FF]+", " ", value)
    return " ".join(value.split())


def normalize_latin(text: str | None) -> str:
    value = unicodedata.normalize("NFKD", text or "")
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def latin_key(text: str | None) -> str:
    """A loose transliteration key for Arabic names written in Latin.

    Examples:
        Fadel / Fadhl / Fadhel -> fdl
        Shaker / Chaker / Shakir -> shkr
        Majid Al Mohandis / Majed Al Muhandis -> mjd l mhnds
    """
    value = normalize_latin(text)
    value = (
        value.replace("kh", "k")
        .replace("ch", "sh")
        .replace("dh", "d")
        .replace("th", "t")
        .replace("ph", "f")
        .replace("q", "k")
    )
    value = re.sub(r"[aeiouy]", "", value)
    value = re.sub(r"(.)\1+", r"\1", value)
    return " ".join(value.split())


def key_is_safe(key: str) -> bool:
    """Avoid single-token/short keys that could cause false positives."""
    return len(key.replace(" ", "")) >= 6 and len(key.split()) >= 2


def tokenize(text: str | None) -> list[str]:
    return [token for token in normalize_arabic(text).split() if token]


def line_set(text: str | None) -> set[str]:
    return {
        normalize_arabic(line)
        for line in (text or "").splitlines()
        if normalize_arabic(line)
    }


def jaccard(left: set | list, right: set | list) -> float:
    a = set(left)
    b = set(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def analyze_lyrics(text: str | None, *, duplicate_title: bool = False) -> dict:
    cleaned = clean_text(text)
    lines = [line for line in cleaned.splitlines() if line.strip()]
    tokens = tokenize(cleaned)
    line_lengths = [len(line) for line in lines]
    max_line_len = max(line_lengths) if line_lengths else 0
    avg_line_len = round(sum(line_lengths) / len(line_lengths), 1) if line_lengths else 0.0

    flags: list[str] = []
    if len(lines) <= 1 and len(tokens) > 20:
        flags.append("one_line")
    if len(lines) < 8 or len(tokens) < 40:
        flags.append("short_lyrics")
    if duplicate_title:
        flags.append("duplicate_title")
    if LATIN_RE.search(cleaned):
        flags.append("latin_chars")
    if TASHKEEL_RE.search(cleaned):
        flags.append("tashkeel")
    if max_line_len > 180:
        flags.append("long_lines")
    if cleaned and not ARABIC_RE.search(cleaned):
        flags.append("no_arabic")

    return {
        "text": cleaned,
        "line_count": len(lines),
        "token_count": len(tokens),
        "avg_line_len": avg_line_len,
        "max_line_len": max_line_len,
        "flags": flags,
    }


def completeness_score(token_count: int, baseline: int | None) -> float:
    if not baseline or baseline <= 0:
        return 1.0
    return round(max(0.0, min(1.0, token_count / baseline)), 3)


def format_score(analysis: dict) -> float:
    score = 1.0
    lines = analysis["line_count"]
    if analysis.get("one_line"):
        score = 0.35
    elif lines < 4:
        score = 0.50
    elif lines < 8:
        score = 0.75
    if analysis.get("max_line_len", 0) > 180:
        score -= 0.20
    if analysis.get("max_line_len", 0) > 320:
        score -= 0.20
    if "no_arabic" in analysis.get("flags", []):
        score -= 0.30
    return round(max(0.0, min(1.0, score)), 3)


def metadata_score(lyricist: str | None, composer: str | None, year: str | None) -> float:
    values = [lyricist, composer, year]
    present = sum(1 for value in values if value)
    return round(present / 3.0, 3)


def snippet_agreement(lyrics_text: str | None, snippet: str | None, limit: int = 60) -> float | None:
    if not snippet:
        return None
    left = tokenize(lyrics_text)[:limit]
    right = tokenize(snippet)[:limit]
    if not left or not right:
        return None
    return round(jaccard(left, right), 3)


def compute_quality(
    *,
    completeness: float,
    agreement: float,
    format_s: float,
    metadata_s: float,
    flags: list[str],
) -> float:
    score = (
        0.35 * completeness
        + 0.30 * agreement
        + 0.20 * format_s
        + 0.15 * metadata_s
    )
    if "snippet_mismatch" in flags:
        score -= 0.25
    if "one_line" in flags:
        score -= 0.10
    if "no_arabic" in flags:
        score -= 0.20
    return round(max(0.0, min(1.0, score)), 3)


REVIEW_FLAGS = {
    "one_line",
    "short_lyrics",
    "snippet_mismatch",
    "duplicate_title",
    "low_agreement",
    "no_arabic",
}


def needs_review(quality: float, flags: list[str]) -> bool:
    return quality < 0.60 or bool(REVIEW_FLAGS & set(flags))
