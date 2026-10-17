# fnanen Lyrics Archive

Structured lyric datasets scraped from [fnanen.com](https://fnanen.com), plus a
reusable scraper for adding more artists.

## Layout

```
fnanen/
├── README.md
├── scripts/
│   ├── scrape_artist.py      # reusable scraper (any artist page)
│   └── requirements.txt
└── artists/
    ├── elissa/               # اليسا
    │   ├── README.md         # dataset schema + stats
    │   ├── elissa_lyrics.json
    │   ├── elissa_lyrics.jsonl
    │   ├── elissa_lyrics.csv
    │   ├── elissa_lyrics.txt
    │   └── elissa_lyrics.db  # SQLite export
    └── fadhl-shaker/         # فضل شاكر
        ├── README.md
        ├── fadhl-shaker_lyrics.json
        ├── fadhl-shaker_lyrics.jsonl
        ├── fadhl-shaker_lyrics.csv
        ├── fadhl-shaker_lyrics.txt
        └── fadhl-shaker_lyrics.db
```

Dataset filenames use the folder name (`<slug>_lyrics.*`). The site's own artist
slug is preserved in the data as `artist_slug` (e.g. `alysa`).

## Quick start

```bash
pip install -r scripts/requirements.txt

# Scrape an artist -> artists/<slug>/
python scripts/scrape_artist.py --artist alysa --letter a \
    --name-en Elissa --output-name elissa
```

Each run writes JSON, JSONL, CSV, TXT, and SQLite into `artists/<slug>/`.

## Adding another artist

Artist index URLs look like:

```
https://fnanen.com/klmat/alaghany/<letter>/<artist-slug>.html
```

`<letter>` is the site's transliterated Arabic letter (`a`, `b`, `t`, `7`, `3`,
`9`, `sh`, `gh`, ...). Pass the slug and letter:

```bash
# Elissa (اليسا)
python scripts/scrape_artist.py --artist alysa --letter a \
    --name-en Elissa --output-name elissa

# Fairuz (فيروز)
python scripts/scrape_artist.py --artist fyroz --letter f --name-en Fairuz
```

Or give the full index URL (the site slug is inferred):

```bash
python scripts/scrape_artist.py \
    --url "https://fnanen.com/klmat/alaghany/a/alysa.html" \
    --name-en Elissa --output-name elissa
```

### Useful options

| Option | Purpose |
| --- | --- |
| `--out-dir DIR` | Output directory (default `artists/<output-name>`) |
| `--output-name NAME` | Folder/file prefix (default: site artist slug) |
| `--name-en NAME` | English artist name stored in the dataset |
| `--cache DIR` | HTML cache directory |
| `--refresh` | Ignore cached pages and refetch |
| `--delay SECONDS` | Throttle between requests (default `0.35`) |
| `--max-pages N` | Safety limit for index pagination |
| `--max-songs N` | Only fetch the first N songs (useful for testing) |

## Dataset schema

Each artist folder has a `README.md` with its own schema and stats. Common fields
per song:

- `id` — site slug (e.g. `btmon`)
- `title` — Arabic title
- `artist` — performer
- `year` — release year when listed
- `lyricist` — كلمات
- `composer` — ألحان
- `views` — view count at scrape time
- `url` — canonical song page
- `lyrics` — full text; `\n` separates lines, blank line separates stanzas
- `stanzas` — same content as an array of stanzas (`array[array[string]]`)
- `line_count`, `stanza_count`, `char_count`

Top-level JSON also includes `source`, `source_url`, `artist`, `artist_name_en`,
`artist_slug`, `output_name`, `scraped_at`, `song_count`, a `schema`
description, and the `songs` array.

The parser normalizes the three lyric layouts used by the site (line-per-`<p>`,
one `<p>` with `<br>`, and a `<div>` with `<br>`), handles malformed unclosed
`div.lyrics` blocks, and converts visual `---` separators into stanza breaks.

## Current artists

| Folder | Artist | Songs | Scraped |
| --- | --- | --- | --- |
| `artists/elissa` | اليسا (Elissa) | 112 | 2026-10-17 |
| `artists/fadhl-shaker` | فضل شاكر (Fadhl Shaker) | 76 | 2026-10-17 |

## Notes

- Responses are cached and requests throttled to keep the scraper polite.
- Lyrics remain the property of their respective rights holders. The source
  site provides them for reading/educational purposes; verify licensing before
  redistribution or commercial use.
- Missing metadata (`year`, `lyricist`, `composer`) is left as `null` when the
  source page does not list it; nothing is guessed.
