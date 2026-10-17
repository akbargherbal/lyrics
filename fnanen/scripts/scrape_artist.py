#!/usr/bin/env python3
"""Scrape lyrics for any artist from fnanen.com into a structured dataset.

The artist index on fnanen.com follows this pattern:

    https://fnanen.com/klmat/alaghany/<letter>/<artist-slug>.html

where <letter> is the transliterated Arabic letter used by the site
(a, b, t, 7, 3, 9, sh, gh, ...). Every artist page lists all songs, and each
song page contains the full lyrics plus writer/composer/year metadata.

Examples
--------
    # Elissa (اليسا) -> ./artists/elissa/
    python3 scripts/scrape_artist.py --artist alysa --letter a --name-en Elissa

    # Fairuz (فيروز) -> ./artists/fyroz/
    python3 scripts/scrape_artist.py --artist fyroz --letter f --name-en Fairuz

    # Or pass the full index URL (slug is inferred from it)
    python3 scripts/scrape_artist.py \
        --url "https://fnanen.com/klmat/alaghany/a/alysa.html" \
        --name-en Elissa

Outputs per artist (in --out-dir, default: ./artists/<output-name>/):
    <slug>_lyrics.json   full dataset with metadata + songs
    <slug>_lyrics.jsonl  one JSON object per song
    <slug>_lyrics.csv    spreadsheet export (UTF-8 BOM)
    <slug>_lyrics.txt    human-readable plain-text collection
    <slug>_lyrics.db     SQLite database (songs table)

The scraper is polite: responses are cached on disk and requests are throttled.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

BASE = "https://fnanen.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en;q=0.8",
}

SCHEMA = {
    "id": "slug used by fnanen.com",
    "title": "song title in Arabic",
    "artist": "performer",
    "year": "release year (string, may be null)",
    "lyricist": "lyrics writer (كلمات)",
    "composer": "composer (ألحان)",
    "views": "page view count at scrape time",
    "url": "canonical fnanen.com song page",
    "lyrics": "full lyrics, newline separated, blank line = stanza break",
    "stanzas": "array of stanzas, each an array of lines",
    "line_count": "number of non-empty lyric lines",
    "stanza_count": "number of stanzas",
    "char_count": "number of characters in lyrics",
}


def clean_text(value: str) -> str:
    value = html.unescape(value).replace("\u200f", "").replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", value).strip()


class Fetcher:
    """HTTP GET with on-disk cache, retries and throttling."""

    def __init__(self, cache_dir: Path, delay: float = 0.35, refresh: bool = False):
        self.cache_dir = cache_dir
        self.delay = delay
        self.refresh = refresh
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _cache_path(self, url: str) -> Path:
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", url.replace(BASE, ""))[:180]
        return self.cache_dir / (name + ".html")

    def get(self, url: str, tries: int = 4) -> str:
        path = self._cache_path(url)
        if not self.refresh and path.exists() and path.stat().st_size > 500:
            return path.read_text(encoding="utf-8")

        last_error = None
        for attempt in range(tries):
            try:
                response = self.session.get(url, timeout=30)
                if response.status_code == 200 and len(response.text) > 500:
                    path.write_text(response.text, encoding="utf-8")
                    time.sleep(self.delay)
                    return response.text
                last_error = f"HTTP {response.status_code}"
            except requests.RequestException as exc:  # network errors
                last_error = repr(exc)
            time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def build_list_url(artist: str, letter: str) -> str:
    return f"{BASE}/klmat/alaghany/{letter}/{artist}.html"


def infer_slug(list_url: str) -> str:
    name = Path(urlparse(list_url).path).name
    slug = re.sub(r"\.html?$", "", name)
    if not slug:
        raise ValueError(f"Could not infer artist slug from URL: {list_url}")
    return slug


def song_prefix(list_url: str) -> str:
    """URL path prefix shared by all song pages of this artist."""
    path = re.sub(r"\.html?$", "", urlparse(list_url).path)
    return path.rstrip("/") + "/"


def with_page(url: str, page: int) -> str:
    if page == 1:
        return url
    parts = urlparse(url)
    query = parse_qs(parts.query)
    query["page"] = [str(page)]
    return urlunparse(parts._replace(query=urlencode(query, doseq=True)))


def detect_artist_name(page_html: str) -> str | None:
    soup = BeautifulSoup(page_html, "html.parser")

    breadcrumbs = soup.select_one("#breadcrumbs")
    if breadcrumbs:
        names = [clean_text(a.get_text()) for a in breadcrumbs.find_all("a")]
        names = [n for n in names if n]
        if len(names) >= 3:
            return names[-1]

    title = soup.select_one("h1")
    if title:
        text = clean_text(title.get_text())
        match = re.match(r"^أغاني\s+(.+?)\s*(?:[:(]|$)", text)
        if match:
            return match.group(1)
        if text:
            return text
    return None


def parse_listing(page_html: str, prefix: str) -> list[dict]:
    soup = BeautifulSoup(page_html, "html.parser")
    rows: list[dict] = []

    for tr in soup.select("tr"):
        anchor = None
        for candidate in tr.select("a[href]"):
            path = urlparse(urljoin(BASE, candidate["href"])).path
            if path.startswith(prefix) and path != prefix.rstrip("/") + ".html":
                anchor = candidate
                break
        if anchor is None:
            continue

        href = urljoin(BASE, anchor["href"])
        anchor_copy = BeautifulSoup(str(anchor), "html.parser")
        for span in anchor_copy.select("span"):
            span.decompose()
        title = clean_text(anchor_copy.get_text(" "))
        if not title:
            continue

        cells = tr.find_all("td")
        views = None
        views_tag = tr.select_one("span.hits")
        if views_tag:
            digits = re.sub(r"[^\d]", "", views_tag.get_text())
            views = int(digits) if digits else None

        year = lyricist = composer = None
        if len(cells) >= 5:
            year = clean_text(cells[2].get_text()) or None
            lyricist = clean_text(cells[3].get_text()) or None
            composer = clean_text(cells[4].get_text()) or None

        rows.append(
            {
                "title": title,
                "url": href.split("?")[0],
                "views": views,
                "year": year,
                "lyricist": lyricist,
                "composer": composer,
            }
        )

    return rows


def extract_lyrics(lyrics_div: BeautifulSoup) -> str:
    """Normalize the three lyric layouts used by fnanen.com into stanzas."""
    # On some malformed pages div.lyrics is never closed, so metadata and
    # forms end up nested inside it. Keep only the nodes before .lrxData.
    nodes = []
    for child in lyrics_div.children:
        classes = getattr(child, "get", lambda *_: None)("class") or []
        if getattr(child, "name", None) == "div" and "lrxData" in classes:
            break
        nodes.append(str(child))
    fragment = BeautifulSoup("".join(nodes), "html.parser")

    # Layouts: one <p> with <br> breaks, one <p> per line, or a <div> with
    # <br> breaks. Empty <p>&nbsp;</p> marks a stanza break.
    paragraphs = fragment.find_all("p", recursive=False) or [fragment]

    blocks: list[list[str] | None] = []
    for paragraph in paragraphs:
        raw = paragraph.decode_contents()
        raw = re.sub(r"\s*<br\s*/?>\s*", "\n", raw, flags=re.I)
        raw = re.sub(r"<[^>]+>", "", raw)
        text = html.unescape(raw).replace("\xa0", " ").replace("\u200f", "")
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]

        # "-" / "---" are visual separators on the site -> stanza break
        if lines and all((not line) or set(line) <= {"-"} for line in lines):
            lines = []
        else:
            lines = [("" if line and set(line) <= {"-"} else line) for line in lines]

        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()

        collapsed: list[str] = []
        for line in lines:
            if line == "" and (not collapsed or collapsed[-1] == ""):
                continue
            collapsed.append(line)

        blocks.append(collapsed or None)

    nonempty = [block for block in blocks if block]
    single_line = sum(1 for block in nonempty if len(block) == 1)
    line_per_p = bool(nonempty) and single_line / len(nonempty) >= 0.8

    if line_per_p:
        lines: list[str] = []
        for block in blocks:
            if not block:
                lines.append("")
            else:
                lines.extend(block)
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()
        out: list[str] = []
        for line in lines:
            if line == "" and (not out or out[-1] == ""):
                continue
            out.append(line)
        lyrics = "\n".join(out)
    else:
        lyrics = "\n\n".join("\n".join(block) for block in blocks if block)

    return re.sub(r"\n{3,}", "\n\n", lyrics).strip()


def parse_song(page_html: str, entry: dict, artist: str) -> dict:
    soup = BeautifulSoup(page_html, "html.parser")

    title_tag = soup.select_one("h1.itemTitle")
    title = clean_text(title_tag.get_text()) if title_tag else entry["title"]

    lyrics_div = soup.select_one("div.lyrics")
    lyrics = extract_lyrics(lyrics_div) if lyrics_div else ""

    meta = {"lyricist": None, "composer": None, "year": None}
    labels = {
        "كلمات": "lyricist",
        "ألحان": "composer",
        "الحان": "composer",
        "تاريخ": "year",
    }
    for span in soup.select("div.lrxData span.extLbl"):
        label = clean_text(span.get_text()).strip(": ").strip()
        key = labels.get(label)
        if not key:
            continue
        value_tag = span.find_next_sibling("span", class_="extTxt")
        if value_tag:
            value = clean_text(value_tag.get_text())
            if value:
                meta[key] = value

    views = entry["views"]
    hits = soup.select_one("div.hits")
    if hits:
        digits = re.sub(r"[^\d]", "", hits.get_text())
        if digits:
            views = int(digits)

    year = meta["year"] or entry["year"]
    if year:
        match = re.search(r"\d{4}", year)
        year = match.group(0) if match else year

    slug = Path(urlparse(entry["url"]).path).stem
    lines = [line for line in lyrics.split("\n") if line.strip()]
    stanzas = [
        [line for line in block.split("\n") if line.strip()]
        for block in re.split(r"\n\s*\n", lyrics)
        if block.strip()
    ]

    return {
        "id": slug,
        "title": title,
        "artist": artist,
        "year": year,
        "lyricist": meta["lyricist"] or entry["lyricist"],
        "composer": meta["composer"] or entry["composer"],
        "views": views,
        "url": entry["url"],
        "lyrics": lyrics,
        "stanzas": stanzas,
        "line_count": len(lines),
        "stanza_count": len(stanzas),
        "char_count": len(lyrics),
    }


def scrape(
    list_url: str,
    artist: str | None = None,
    name_en: str | None = None,
    cache_dir: Path | None = None,
    delay: float = 0.35,
    refresh: bool = False,
    max_pages: int = 100,
    max_songs: int | None = None,
) -> dict:
    slug = infer_slug(list_url)
    prefix = song_prefix(list_url)
    fetcher = Fetcher(cache_dir or default_cache_dir(), delay=delay, refresh=refresh)

    first_page = fetcher.get(list_url)
    artist = artist or detect_artist_name(first_page) or slug

    entries: list[dict] = []
    seen: set[str] = set()
    page = 1
    while page <= max_pages:
        page_html = first_page if page == 1 else fetcher.get(with_page(list_url, page))
        rows = parse_listing(page_html, prefix)
        fresh = [row for row in rows if row["url"] not in seen]
        if not fresh:
            break
        for row in fresh:
            seen.add(row["url"])
            entries.append(row)
        print(f"listing page {page}: {len(fresh)} songs", flush=True)
        page += 1

    if max_songs:
        entries = entries[:max_songs]

    print(f"{slug}: {len(entries)} songs to fetch", flush=True)
    songs: list[dict] = []
    for index, entry in enumerate(entries, 1):
        try:
            song = parse_song(fetcher.get(entry["url"]), entry, artist)
        except Exception as exc:  # noqa: BLE001 - keep going on a bad page
            print(f"[{index}/{len(entries)}] FAILED {entry['title']}: {exc}", flush=True)
            song = {
                **entry,
                "id": Path(urlparse(entry["url"]).path).stem,
                "artist": artist,
                "error": str(exc),
            }
        songs.append(song)
        print(
            f"[{index}/{len(entries)}] {song.get('title')} "
            f"({song.get('line_count', 0)} lines)",
            flush=True,
        )

    return {
        "source": "fnanen.com",
        "source_url": list_url,
        "artist": artist,
        "artist_name_en": name_en,
        "artist_slug": slug,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "song_count": len(songs),
        "schema": SCHEMA,
        "songs": songs,
    }


def default_cache_dir() -> Path:
    root = Path(tempfile.gettempdir()) / "opencode" / "fnanen-cache"
    return root


def write_outputs(dataset: dict, out_dir: Path, output_name: str | None = None) -> list[Path]:
    prefix = output_name or dataset["artist_slug"]
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    json_path = out_dir / f"{prefix}_lyrics.json"
    json_path.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    paths.append(json_path)

    jsonl_path = out_dir / f"{prefix}_lyrics.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for song in dataset["songs"]:
            handle.write(json.dumps(song, ensure_ascii=False) + "\n")
    paths.append(jsonl_path)

    csv_path = out_dir / f"{prefix}_lyrics.csv"
    columns = [
        "id", "title", "artist", "year", "lyricist", "composer",
        "views", "url", "lyrics", "line_count", "stanza_count", "char_count",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for song in dataset["songs"]:
            writer.writerow({column: song.get(column) for column in columns})
    paths.append(csv_path)

    txt_path = out_dir / f"{prefix}_lyrics.txt"
    with txt_path.open("w", encoding="utf-8") as handle:
        handle.write(f"{dataset['artist']} — كلمات الأغاني\n")
        handle.write("=" * 40 + "\n\n")
        for index, song in enumerate(dataset["songs"], 1):
            handle.write(f"{index}. {song['title']}\n")
            details = []
            if song.get("year"):
                details.append(str(song["year"]))
            if song.get("lyricist"):
                details.append(f"كلمات: {song['lyricist']}")
            if song.get("composer"):
                details.append(f"ألحان: {song['composer']}")
            if details:
                handle.write(f"   {' · '.join(details)}\n")
            handle.write("\n")
            handle.write(song["lyrics"].strip() + "\n")
            handle.write("\n" + "-" * 40 + "\n\n")
    paths.append(txt_path)

    db_path = out_dir / f"{prefix}_lyrics.db"
    write_sqlite(dataset, db_path)
    paths.append(db_path)

    return paths


def write_sqlite(dataset: dict, db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute("DROP TABLE IF EXISTS songs")
        cursor.execute(
            """
            CREATE TABLE songs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                artist TEXT,
                year TEXT,
                lyricist TEXT,
                composer TEXT,
                views INTEGER,
                url TEXT,
                lyrics TEXT,
                stanzas TEXT,
                line_count INTEGER,
                stanza_count INTEGER,
                char_count INTEGER
            )
            """
        )
        for song in dataset["songs"]:
            cursor.execute(
                "INSERT INTO songs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    song.get("id"),
                    song.get("title"),
                    song.get("artist"),
                    song.get("year"),
                    song.get("lyricist"),
                    song.get("composer"),
                    song.get("views"),
                    song.get("url"),
                    song.get("lyrics"),
                    json.dumps(song.get("stanzas"), ensure_ascii=False),
                    song.get("line_count"),
                    song.get("stanza_count"),
                    song.get("char_count"),
                ),
            )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_songs_year ON songs(year)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_songs_lyricist ON songs(lyricist)"
        )
        connection.commit()
    finally:
        connection.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape all lyrics for an artist from fnanen.com.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --artist alysa --letter a --name-en Elissa\n"
            "  %(prog)s --url https://fnanen.com/klmat/alaghany/f/fyroz.html "
            "--name-en Fairuz\n"
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--artist",
        help="artist slug used by the site, e.g. alysa (from .../a/alysa.html)",
    )
    source.add_argument(
        "--url", help="full artist index URL; overrides --artist/--letter"
    )
    parser.add_argument(
        "--letter",
        default="a",
        help="transliterated Arabic letter segment in the URL (default: a). "
        "Only used with --artist.",
    )
    parser.add_argument("--name-en", default=None, help="English artist name")
    parser.add_argument(
        "--output-name",
        default=None,
        help="folder/file prefix (default: artist slug, e.g. alysa)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="output directory (default: ./artists/<output-name>)",
    )
    parser.add_argument("--cache", type=Path, default=None, help="HTML cache directory")
    parser.add_argument(
        "--delay", type=float, default=0.35, help="seconds between requests (default: 0.35)"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="ignore cached HTML and refetch"
    )
    parser.add_argument(
        "--max-pages", type=int, default=100, help="safety limit for index pages"
    )
    parser.add_argument(
        "--max-songs", type=int, default=None, help="only scrape the first N songs"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    list_url = args.url or build_list_url(args.artist, args.letter)
    slug = infer_slug(list_url)
    output_name = args.output_name or slug
    out_dir = args.out_dir or Path.cwd() / "artists" / output_name

    dataset = scrape(
        list_url=list_url,
        artist=None,
        name_en=args.name_en,
        cache_dir=args.cache,
        delay=args.delay,
        refresh=args.refresh,
        max_pages=args.max_pages,
        max_songs=args.max_songs,
    )
    dataset["output_name"] = output_name

    paths = write_outputs(dataset, out_dir, output_name)
    print(
        f"wrote {dataset['song_count']} songs for {dataset['artist']} to {out_dir}",
        flush=True,
    )
    for path in paths:
        print(f"  {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
