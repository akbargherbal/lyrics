# Elissa (اليسا) — Lyrics Dataset

Complete lyrics for the 112 songs listed on
<https://fnanen.com/klmat/alaghany/a/alysa.html>, scraped on 2026-10-17.

- **112 songs** · **533 stanzas** · **2,203 lyric lines** · ~68k characters
- Years present: 1998–2018 (5 songs have no year on the source page)
- 6 songs have no writer/composer listed on the source page (left as `null`)

## Files

| File | Description |
| --- | --- |
| `elissa_lyrics.json` | Full dataset: metadata + array of 112 song objects |
| `elissa_lyrics.jsonl` | One song object per line (streaming / ML friendly) |
| `elissa_lyrics.csv` | Spreadsheet export (UTF-8 with BOM, opens in Excel) |
| `elissa_lyrics.txt` | Human-readable plain-text collection |
| `elissa_lyrics.db` | SQLite database with a `songs` table |

The scraper lives in
[`../../scripts/scrape_artist.py`](../../scripts/scrape_artist.py) and works for
any artist on the same website.

## Schema

Top level (`elissa_lyrics.json`):

```json
{
  "source": "fnanen.com",
  "source_url": "https://fnanen.com/klmat/alaghany/a/alysa.html",
  "artist": "اليسا",
  "artist_name_en": "Elissa",
  "artist_slug": "alysa",
  "output_name": "elissa",
  "scraped_at": "2026-10-17T06:10:22+00:00",
  "song_count": 112,
  "schema": { "...": "field descriptions" },
  "songs": [ ... ]
}
```

Each song:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | Slug used by fnanen.com, e.g. `btmon` |
| `title` | string | Arabic song title |
| `artist` | string | `اليسا` |
| `year` | string \| null | Release year (5 songs have no year on the source page) |
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

with open("elissa_lyrics.json", encoding="utf-8") as f:
    data = json.load(f)

for song in data["songs"]:
    print(song["title"], "-", song["year"], "-", song["composer"])
    print(song["lyrics"])
```

```sql
-- SQLite
SELECT title, year, lyricist, composer FROM songs WHERE year = '2008';
SELECT title, lyrics FROM songs WHERE title LIKE '%بتمون%';
```

## Notes

- Lyrics are property of their respective rights holders; the source site
  provides them for reading/educational purposes only. Check licensing before
  redistributing or using commercially.
- Missing `lyricist`/`composer`/`year` values mean the source page did not list
  them (they were not inferred).
- Three source layouts are handled: line-per-`<p>` pages, a single `<p>` with
  `<br>` line breaks, and a `<div>` with `<br>` line breaks. Visual `---`
  separators become stanza breaks.
- Re-run from the repository root to refresh:

  ```bash
  python3 scripts/scrape_artist.py --artist alysa --letter a \
      --name-en Elissa --output-name elissa
  ```

  This writes to `artists/elissa/`.

  HTML responses are cached (default: `<tmp>/opencode/fnanen-cache`) so reruns
  are fast and polite. Use `--refresh` to force a full refetch.
