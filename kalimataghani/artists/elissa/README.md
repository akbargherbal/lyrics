# Elissa (إليسا) — Lyrics Dataset

Complete lyrics scraped from [kalimataghani.com](https://kalimataghani.com/%D8%A7%D9%84%D9%85%D8%B7%D8%B1%D8%A8%D9%8A%D9%86/51/%D8%A5%D9%84%D9%8A%D8%B3%D8%A7/) — 46 songs, 1,014 lines, ~6,061 words.

## Files

| File | Description |
|---|---|
| `elissa_lyrics.json` | Main dataset with metadata + all songs (pretty-printed, UTF-8) |
| `elissa_lyrics.jsonl` | One song object per line (JSON Lines) |
| `elissa_lyrics.csv` | Flat table (UTF-8 with BOM for Excel) |
| `elissa_lyrics.txt` | Human-readable plain-text collection |

Regenerate with:

```bash
python scripts/scrape_artist.py "https://kalimataghani.com/%D8%A7%D9%84%D9%85%D8%B7%D8%B1%D8%A8%D9%8A%D9%86/51/%D8%A5%D9%84%D9%8A%D8%B3%D8%A7/" --slug elissa --name-en "Elissa"
```

## JSON schema

```json
{
  "dataset": {
    "name": "Elissa (إليسا) — Complete Lyrics",
    "artist_ar": "إليسا",
    "artist_en": "Elissa",
    "artist_id": 51,
    "source": "https://kalimataghani.com/%D8%A7%D9%84%D9%85%D8%B7%D8%B1%D8%A8%D9%8A%D9%86/51/%D8%A5%D9%84%D9%8A%D8%B3%D8%A7/",
    "language": "ar",
    "direction": "rtl",
    "song_count": 46,
    "scraped_at": "2026-10-17",
    "notes": "..."
  },
  "songs": [
    {
      "id": 1,
      "title": "…",
      "slug": "…",
      "url": "…",
      "artist": "إليسا",
      "notes": "remix/version info (may be empty)",
      "lyrics": "line one\nline two",
      "lyrics_lines": ["line one", "line two"],
      "line_count": 24,
      "word_count": 96,
      "contributor": "…"
    }
  ]
}
```

## Field notes

- `lyrics` — full lyrics as a single string, lines separated by `\n`.
- `lyrics_lines` — the same content pre-split into an array of non-empty lines.
- `notes` — version/remix info shown above the lyrics on the source page (empty when absent).
- `contributor` — person credited for submitting the lyrics on the source site (empty when absent).
- Diacritics (تشكيل) are preserved exactly as published on the source.
- Multiple songs share a title (افتكرت); they are distinct versions/entries and are all retained.

## Usage

```python
import json

data = json.load(open("elissa_lyrics.json", encoding="utf-8"))
for song in data["songs"]:
    print(song["title"], song["line_count"])
```

## Copyright

Lyrics are the property of their respective rights holders. This dataset is provided for
personal/research use; verify licensing before redistributing.
