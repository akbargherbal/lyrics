# Fadhl Shaker (فضل شاكر) — Lyrics Dataset

Complete lyrics scraped from [kalimataghani.com](https://kalimataghani.com/%D8%A7%D9%84%D9%85%D8%B7%D8%B1%D8%A8%D9%8A%D9%86/71/%D9%81%D8%B6%D9%84-%D8%B4%D8%A7%D9%83%D8%B1/) — 26 songs, 630 lines, ~3,430 words.

## Files

| File | Description |
|---|---|
| `fadhl-shaker_lyrics.json` | Main dataset with metadata + all songs (pretty-printed, UTF-8) |
| `fadhl-shaker_lyrics.jsonl` | One song object per line (JSON Lines) |
| `fadhl-shaker_lyrics.csv` | Flat table (UTF-8 with BOM for Excel) |
| `fadhl-shaker_lyrics.txt` | Human-readable plain-text collection |

Regenerate with:

```bash
python scripts/scrape_artist.py "https://kalimataghani.com/%D8%A7%D9%84%D9%85%D8%B7%D8%B1%D8%A8%D9%8A%D9%86/71/%D9%81%D8%B6%D9%84-%D8%B4%D8%A7%D9%83%D8%B1/" --slug fadhl-shaker --name-en "Fadhl Shaker"
```

## JSON schema

```json
{
  "dataset": {
    "name": "Fadhl Shaker (فضل شاكر) — Complete Lyrics",
    "artist_ar": "فضل شاكر",
    "artist_en": "Fadhl Shaker",
    "artist_id": 71,
    "source": "https://kalimataghani.com/%D8%A7%D9%84%D9%85%D8%B7%D8%B1%D8%A8%D9%8A%D9%86/71/%D9%81%D8%B6%D9%84-%D8%B4%D8%A7%D9%83%D8%B1/",
    "language": "ar",
    "direction": "rtl",
    "song_count": 26,
    "scraped_at": "2026-10-17",
    "notes": "..."
  },
  "songs": [
    {
      "id": 1,
      "title": "…",
      "slug": "…",
      "url": "…",
      "artist": "فضل شاكر",
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
- Multiple songs share a title (كنت مفكر); they are distinct versions/entries and are all retained.

## Usage

```python
import json

data = json.load(open("fadhl-shaker_lyrics.json", encoding="utf-8"))
for song in data["songs"]:
    print(song["title"], song["line_count"])
```

## Copyright

Lyrics are the property of their respective rights holders. This dataset is provided for
personal/research use; verify licensing before redistributing.
