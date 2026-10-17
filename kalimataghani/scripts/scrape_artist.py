#!/usr/bin/env python3
"""
Scrape an artist's complete lyrics from kalimataghani.com into a structured dataset.

Usage:
    python scripts/scrape_artist.py "https://kalimataghani.com/المطربين/51/إليسا/"
    python scripts/scrape_artist.py "<artist-url>" --slug elissa --name-en Elissa

Output (default: artists/<slug>/):
    <slug>_lyrics.json    metadata + all songs (pretty printed)
    <slug>_lyrics.jsonl   one song object per line
    <slug>_lyrics.csv     flat table (UTF-8 BOM for Excel)
    <slug>_lyrics.txt     human-readable collection
    README.md             per-artist schema documentation

Requires: requests, beautifulsoup4
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import time
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://kalimataghani.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en;q=0.8",
}

# --- Arabic transliteration (best effort, for folder names) -----------------

_ARABIC_MAP = {
    "ا": "a", "أ": "a", "إ": "i", "آ": "aa", "ٱ": "a",
    "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh",
    "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh",
    "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "", "غ": "gh",
    "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n",
    "ه": "h", "و": "w", "ي": "y", "ى": "a", "ة": "a", "ء": "",
    "ئ": "", "ؤ": "", "پ": "p", "چ": "ch", "ژ": "zh", "گ": "g",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
}
_DIACRITICS = set("ًٌٍَُِّْـ")


def transliterate(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch in _DIACRITICS:
            continue
        out.append(_ARABIC_MAP.get(ch, ch))
    return "".join(out)


def slugify(text: str) -> str:
    text = transliterate(text)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


# --- HTTP helpers -----------------------------------------------------------


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def fetch(session: requests.Session, url: str, *, timeout: float, retries: int) -> str:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            response.encoding = "utf-8"
            return response.text
        except Exception as exc:  # noqa: BLE001 - retry any network error
            last_error = exc
            if attempt < retries:
                wait = attempt * 1.5
                print(f"    ! {exc} — retrying in {wait:.1f}s", file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


# --- Parsing ----------------------------------------------------------------


def clean(text: str) -> str:
    text = text.replace("\u200e", "").replace("\u200f", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def normalize_url(href: str) -> str:
    return urllib.parse.urljoin(BASE_URL + "/", href)


def listing_pages(
    session: requests.Session,
    artist_url: str,
    *,
    timeout: float,
    retries: int,
    delay: float,
    max_pages: int = 200,
) -> tuple[str, str, int, list[dict]]:
    """Walk the artist's paginated song listing.

    Returns (artist_name, artist_path, artist_id, cards).
    """
    artist_url = artist_url.split("#")[0]
    decoded_path = urllib.parse.unquote(urllib.parse.urlparse(artist_url).path)
    if not decoded_path.endswith("/"):
        decoded_path += "/"

    artist_id = 0
    match = re.search(r"/المطربين/(\d+)/", decoded_path)
    if match:
        artist_id = int(match.group(1))

    cards: list[dict] = []
    seen_urls: set[str] = set()
    artist_name = ""
    offset = 0
    visited_offsets: set[int] = set()

    for page_num in range(1, max_pages + 1):
        page_url = artist_url
        if offset:
            page_url = f"{artist_url}?debut_articles={offset}"

        print(f"  listing page {page_num} (offset {offset}) …", flush=True)
        html = fetch(session, page_url, timeout=timeout, retries=retries)
        soup = BeautifulSoup(html, "html.parser")

        if not artist_name:
            heading = (
                soup.select_one("h1.surlignable.centrertexte")
                or soup.select_one("strong.on2")
                or soup.select_one('h1[itemprop="name"]')
            )
            if heading:
                artist_name = clean(heading.get_text(" ", strip=True))

        new_count = 0
        for card in soup.select("div.lastarticle"):
            link = card.select_one("strong a[href]") or card.select_one("a[href]")
            if not link:
                continue
            href = urllib.parse.unquote(link["href"])
            # Keep only songs belonging to this artist (hrefs are root-relative,
            # sometimes with and sometimes without the leading slash).
            relative_path = decoded_path.lstrip("/")
            if not (href.startswith(decoded_path) or href.startswith(relative_path)):
                continue
            url = normalize_url(link["href"])
            if url in seen_urls:
                continue
            seen_urls.add(url)
            new_count += 1

            title = clean(link.get_text(" ", strip=True))
            contributor = ""
            credit = card.select_one("small.info-publi")
            if credit:
                contributor = clean(credit.get_text(" ", strip=True))
                contributor = re.sub(r"^بقلم\s*", "", contributor).strip()

            cards.append({"url": url, "title": title, "contributor": contributor})

        print(f"    +{new_count} songs (total {len(cards)})")

        # Find the next pagination offset strictly greater than the current one.
        offsets: set[int] = set()
        for a in soup.select('a[href*="debut_articles="]'):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(a["href"]).query)
            for value in query.get("debut_articles", []):
                if value.isdigit():
                    offsets.add(int(value))
        candidates = sorted(o for o in offsets if o > offset and o not in visited_offsets)
        if not candidates or new_count == 0:
            break
        visited_offsets.add(offset)
        offset = candidates[0]
        time.sleep(delay)

    return artist_name, decoded_path, artist_id, cards


def parse_song(
    session: requests.Session,
    url: str,
    fallback_title: str,
    contributor: str,
    *,
    timeout: float,
    retries: int,
) -> dict:
    html = fetch(session, url, timeout=timeout, retries=retries)
    soup = BeautifulSoup(html, "html.parser")

    title = fallback_title
    title_node = soup.select_one('h1.p-name span[itemprop="name"]')
    if title_node:
        title = clean(title_node.get_text(" ", strip=True))
    else:
        title_node = soup.select_one("h1.p-name")
        if title_node:
            title = re.sub(r"^كلمات أغنية\s*", "", clean(title_node.get_text(" ", strip=True)))

    artist_node = soup.select_one('h1[itemprop="author"] a')
    artist = clean(artist_node.get_text(" ", strip=True)) if artist_node else ""

    container = soup.select_one("div.texte.surlignable.e-content")
    if container is None:
        container = soup.select_one('div[itemprop="review"]')

    lines: list[str] = []
    if container is not None:
        for br in container.find_all("br"):
            br.replace_with("\n")
        for raw_line in container.get_text("\n").split("\n"):
            line = clean(raw_line)
            if line:
                lines.append(line)
    lyrics = "\n".join(lines)

    notes = ""
    summary = soup.select_one("div.texte.surlignable.p-summary")
    if summary:
        notes = clean(summary.get_text(" ", strip=True))
        # Drop the leading artist name ("إليسا - ") so notes hold version info only.
        if artist and notes.startswith(artist):
            notes = notes[len(artist):].lstrip(" -–—:").strip()

    slug = urllib.parse.unquote(urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1])
    slug = re.sub(r"\.html$", "", slug)

    return {
        "title": title,
        "slug": slug,
        "url": url,
        "artist": artist,
        "notes": notes,
        "lyrics": lyrics,
        "lyrics_lines": lines,
        "line_count": len(lines),
        "word_count": len(lyrics.split()),
        "contributor": contributor,
    }


# --- Writers ----------------------------------------------------------------


def write_json(path: Path, dataset: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(dataset, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_jsonl(path: Path, songs: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for song in songs:
            handle.write(json.dumps(song, ensure_ascii=False) + "\n")


def write_csv(path: Path, songs: Iterable[dict]) -> None:
    fields = [
        "id", "title", "artist", "notes", "line_count", "word_count",
        "lyrics", "url", "contributor",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for song in songs:
            writer.writerow({key: song.get(key, "") for key in fields})


def write_txt(path: Path, artist_name: str, songs: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(f"{artist_name} — كلمات الأغاني\n")
        handle.write("=" * 40 + "\n\n")
        for song in songs:
            handle.write(f"{song['id']}. {song['title']}\n")
            if song["notes"]:
                handle.write(f"   ({song['notes']})\n")
            handle.write("\n" + song["lyrics"] + "\n\n" + "-" * 40 + "\n\n")


def write_readme(
    path: Path,
    *,
    artist_name: str,
    artist_name_en: str,
    prefix: str,
    dataset: dict,
) -> None:
    songs = dataset["songs"]
    total_lines = sum(song["line_count"] for song in songs)
    total_words = sum(song["word_count"] for song in songs)
    src = dataset["dataset"]["source"]
    title = f"{artist_name_en} ({artist_name})" if artist_name_en else artist_name

    duplicates = sorted(
        {s["title"] for s in songs if sum(1 for x in songs if x["title"] == s["title"]) > 1}
    )
    duplicate_note = (
        f"- Multiple songs share a title ({', '.join(duplicates)}); they are distinct "
        "versions/entries and are all retained.\n"
        if duplicates
        else ""
    )

    body = f"""# {title} — Lyrics Dataset

Complete lyrics scraped from [kalimataghani.com]({src}) — {len(songs)} songs, {total_lines:,} lines, ~{total_words:,} words.

## Files

| File | Description |
|---|---|
| `{prefix}_lyrics.json` | Main dataset with metadata + all songs (pretty-printed, UTF-8) |
| `{prefix}_lyrics.jsonl` | One song object per line (JSON Lines) |
| `{prefix}_lyrics.csv` | Flat table (UTF-8 with BOM for Excel) |
| `{prefix}_lyrics.txt` | Human-readable plain-text collection |

Regenerate with:

```bash
python scripts/scrape_artist.py "{src}" --slug {prefix}{f' --name-en "{artist_name_en}"' if artist_name_en else ''}
```

## JSON schema

```json
{{
  "dataset": {{
    "name": "{title} — Complete Lyrics",
    "artist_ar": "{artist_name}",
    "artist_en": "{artist_name_en}",
    "artist_id": {dataset["dataset"]["artist_id"]},
    "source": "{src}",
    "language": "ar",
    "direction": "rtl",
    "song_count": {len(songs)},
    "scraped_at": "{dataset["dataset"]["scraped_at"]}",
    "notes": "..."
  }},
  "songs": [
    {{
      "id": 1,
      "title": "…",
      "slug": "…",
      "url": "…",
      "artist": "{artist_name}",
      "notes": "remix/version info (may be empty)",
      "lyrics": "line one\\nline two",
      "lyrics_lines": ["line one", "line two"],
      "line_count": 24,
      "word_count": 96,
      "contributor": "…"
    }}
  ]
}}
```

## Field notes

- `lyrics` — full lyrics as a single string, lines separated by `\\n`.
- `lyrics_lines` — the same content pre-split into an array of non-empty lines.
- `notes` — version/remix info shown above the lyrics on the source page (empty when absent).
- `contributor` — person credited for submitting the lyrics on the source site (empty when absent).
- Diacritics (تشكيل) are preserved exactly as published on the source.
{duplicate_note}
## Usage

```python
import json

data = json.load(open("{prefix}_lyrics.json", encoding="utf-8"))
for song in data["songs"]:
    print(song["title"], song["line_count"])
```

## Copyright

Lyrics are the property of their respective rights holders. This dataset is provided for
personal/research use; verify licensing before redistributing.
"""
    path.write_text(body, encoding="utf-8")


# --- Main -------------------------------------------------------------------


def build_dataset(
    session: requests.Session,
    artist_url: str,
    *,
    slug: str | None,
    name_en: str,
    out_root: Path,
    delay: float,
    timeout: float,
    retries: int,
    limit: int | None,
    overwrite: bool,
) -> Path:
    print("Discovering songs …")
    artist_name, artist_path, artist_id, cards = listing_pages(
        session, artist_url, timeout=timeout, retries=retries, delay=delay
    )
    if not artist_name:
        raise RuntimeError("Could not detect the artist name from the page.")
    if not cards:
        raise RuntimeError(
            "No songs found. Check that the URL is an artist page on kalimataghani.com."
        )

    artist_slug = slug or slugify(artist_name) or f"artist-{artist_id}"
    artist_slug = slugify(artist_slug)
    out_dir = out_root / artist_slug
    if out_dir.exists() and not overwrite:
        raise SystemExit(
            f"Output folder already exists: {out_dir}\n"
            "Re-run with --overwrite to replace it."
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    if limit is not None:
        cards = cards[:limit]

    songs: list[dict] = []
    total = len(cards)
    for index, card in enumerate(cards, 1):
        print(f"  [{index}/{total}] {card['title']}", flush=True)
        try:
            song = parse_song(
                session,
                card["url"],
                card["title"],
                card["contributor"],
                timeout=timeout,
                retries=retries,
            )
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"    ! skipped: {exc}", file=sys.stderr)
            continue
        if not song["lyrics"]:
            print("    ! no lyrics found — skipped", file=sys.stderr)
            continue
        song["id"] = len(songs) + 1
        songs.append(song)
        if delay and index < total:
            time.sleep(delay)

    if not songs:
        raise RuntimeError("Every song page failed; nothing was written.")

    dataset = {
        "dataset": {
            "name": f"{name_en or artist_name} ({artist_name}) — Complete Lyrics",
            "artist_ar": artist_name,
            "artist_en": name_en,
            "artist_id": artist_id,
            "artist_path": artist_path,
            "source": artist_url,
            "language": "ar",
            "direction": "rtl",
            "song_count": len(songs),
            "scraped_at": dt.date.today().isoformat(),
            "notes": (
                "Lyrics as published on kalimataghani.com; diacritics preserved as on "
                "source. Copyright remains with the respective rights holders."
            ),
        },
        "songs": songs,
    }

    prefix = artist_slug
    write_json(out_dir / f"{prefix}_lyrics.json", dataset)
    write_jsonl(out_dir / f"{prefix}_lyrics.jsonl", songs)
    write_csv(out_dir / f"{prefix}_lyrics.csv", songs)
    write_txt(out_dir / f"{prefix}_lyrics.txt", artist_name, songs)
    write_readme(
        out_dir / "README.md",
        artist_name=artist_name,
        artist_name_en=name_en,
        prefix=prefix,
        dataset=dataset,
    )

    print(
        f"\nDone: {len(songs)} songs, "
        f"{sum(s['line_count'] for s in songs):,} lines → {out_dir}"
    )
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape an artist's lyrics from kalimataghani.com."
    )
    parser.add_argument("artist_url", help="Artist page URL on kalimataghani.com")
    parser.add_argument("--slug", help="Folder/file slug (default: transliterated name)")
    parser.add_argument("--name-en", default="", help="Artist name in Latin script")
    parser.add_argument(
        "--out", default="artists", help="Output root folder (default: artists)"
    )
    parser.add_argument("--delay", type=float, default=0.4, help="Delay between requests")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--limit", type=int, help="Only scrape the first N songs (testing)")
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace an existing artist folder"
    )
    args = parser.parse_args()

    session = make_session()
    try:
        build_dataset(
            session,
            args.artist_url,
            slug=args.slug,
            name_en=args.name_en,
            out_root=Path(args.out),
            delay=args.delay,
            timeout=args.timeout,
            retries=args.retries,
            limit=args.limit,
            overwrite=args.overwrite,
        )
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    main()
