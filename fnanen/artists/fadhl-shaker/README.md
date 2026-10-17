# Fadhl Shaker (فضل شاكر) — Lyrics Dataset

Complete lyrics for the 76 songs listed on
<https://fnanen.com/klmat/alaghany/f/fdhl-shakr.html>, scraped on 2026-10-17.

- **76 songs** · **315 stanzas** · **1,515 lyric lines** · ~47k characters
- Years present: 2010–2022 (65 songs have no year on the source page)
- 28 songs have no writer/composer listed on the source page (left as `null`)

## Files

| File | Description |
| --- | --- |
| `fadhl-shaker_lyrics.json` | Full dataset: metadata + array of 76 song objects |
| `fadhl-shaker_lyrics.jsonl` | One song object per line (streaming / ML friendly) |
| `fadhl-shaker_lyrics.csv` | Spreadsheet export (UTF-8 with BOM, opens in Excel) |
| `fadhl-shaker_lyrics.txt` | Human-readable plain-text collection |
| `fadhl-shaker_lyrics.db` | SQLite database with a `songs` table |

The scraper lives in
[`../../scripts/scrape_artist.py`](../../scripts/scrape_artist.py) and works for
any artist on the same website.

## Schema

Top level (`fadhl-shaker_lyrics.json`):

```json
{
  "source": "fnanen.com",
  "source_url": "https://fnanen.com/klmat/alaghany/f/fdhl-shakr.html",
  "artist": "فضل شاكر",
  "artist_name_en": "Fadhl Shaker",
  "artist_slug": "fdhl-shakr",
  "output_name": "fadhl-shaker",
  "scraped_at": "2026-10-17T06:10:22+00:00",
  "song_count": 76,
  "schema": { "...": "field descriptions" },
  "songs": [ ... ]
}
```

Each song:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | Slug used by fnanen.com, e.g. `a7aol` |
| `title` | string | Arabic song title |
| `artist` | string | `فضل شاكر` |
| `year` | string \| null | Release year (65 songs have no year on the source page) |
| `lyricist` | string \| null | Lyric writer (كلمات) |
| `composer` | string \| null | Composer (ألحان) |
| `views` | integer \| null | Page views at scrape time |
| `url` | string | Canonical source page |
| `lyrics` | string | Full lyrics; `\n` separates lines, blank line separates stanzas |
| `stanzas` | array[array[string]] | Same lyrics grouped into stanzas/lines |
| `line_count` | integer | Number of non-empty lines |
| `stanza_count` | integer | Number of stanzas |
| `char_count` | integer | Character count of `lyrics` |

## Quick usage

```python
import json

with open("fadhl-shaker_lyrics.json", encoding="utf-8") as f:
    data = json.load(f)

for song in data["songs"]:
    print(song["title"], "-", song["year"], "-", song["composer"])
    print(song["lyrics"])
```

```sql
-- SQLite
SELECT title, year, lyricist, composer FROM songs WHERE year = '2022';
SELECT title, lyrics FROM songs WHERE title LIKE '%يا حبيبي%';
```

## Notes

- Lyrics are property of their respective rights holders; the source site
  provides them for reading/educational purposes only. Check licensing before
  redistributing or using commercially.
- Missing `lyricist`/`composer`/`year` values mean the source page did not list
  them (they were not inferred). Where the song page lacks metadata but the
  index page lists it, the index value is used.
- One song (`الله واعلم`) is published on the source as a single unbroken
  paragraph, so it appears as one long line; line breaks were not invented.
- Three source layouts are handled: line-per-`<p>` pages, a single `<p>` with
  `<br>` line breaks, and a `<div>` with `<br>` line breaks. Visual `---`
  separators become stanza breaks.
- Re-run from the repository root to refresh:

  ```bash
  python3 scripts/scrape_artist.py --artist fdhl-shakr --letter f \
      --name-en "Fadhl Shaker" --output-name fadhl-shaker
  ```

  This writes to `artists/fadhl-shaker/`.

  HTML responses are cached (default: `<tmp>/opencode/fnanen-cache`) so reruns
  are fast and polite. Use `--refresh` to force a full refetch.
