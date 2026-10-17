# Kalimataghani Lyrics Archive

Structured lyric datasets scraped from [kalimataghani.com](https://kalimataghani.com),
plus a reusable scraper for adding more artists.

## Layout

```
kalimataghani/
├── README.md
├── scripts/
│   ├── scrape_artist.py      # reusable scraper (any artist page)
│   └── requirements.txt
└── artists/
    └── elissa/               # إليسا
        ├── README.md         # dataset schema + stats
        ├── elissa_lyrics.json
        ├── elissa_lyrics.jsonl
        ├── elissa_lyrics.csv
        └── elissa_lyrics.txt
```

## Quick start

```bash
pip install -r scripts/requirements.txt

# Scrape an artist (pagination is followed automatically)
python scripts/scrape_artist.py "https://kalimataghani.com/المطربين/51/إليسا/" \
    --slug elissa --name-en Elissa
```

Output goes to `artists/<slug>/` as JSON, JSONL, CSV, and TXT, plus a generated
`README.md` documenting that dataset.

## Adding another artist

1. Open the artist's page on kalimataghani.com (e.g. via **المطربين → letter → artist**).
2. Copy its URL and run:

```bash
python scripts/scrape_artist.py "<artist-page-url>" --slug <folder-name> --name-en "<Latin name>"
```

`--slug` is optional; without it the folder name is transliterated from the Arabic
artist name. `--name-en` is optional metadata.

### Useful options

| Option | Description |
|---|---|
| `--out DIR` | Output root (default: `artists`) |
| `--slug NAME` | Folder/file name for the artist |
| `--name-en NAME` | Latin artist name stored in metadata |
| `--delay SECONDS` | Delay between requests (default: 0.4) |
| `--timeout SECONDS` | Per-request timeout (default: 30) |
| `--retries N` | Retry attempts per request (default: 3) |
| `--limit N` | Scrape only the first N songs (testing) |
| `--overwrite` | Replace an existing artist folder |

The scraper:

- follows all `?debut_articles=` pagination pages;
- keeps only links under the artist's own path;
- extracts title, artist, version/remix notes, lyrics and submitter credit;
- retries failed requests with backoff and skips song pages with no lyrics;
- writes UTF-8 files (CSV includes a BOM for Excel compatibility).

## Dataset schema

Each artist folder has a `README.md` with its own schema and stats. Common fields
per song: `id`, `title`, `slug`, `url`, `artist`, `notes`, `lyrics`,
`lyrics_lines`, `line_count`, `word_count`, `contributor`.

## Current artists

| Folder | Artist | Songs | Scraped |
|---|---|---|---|
| `artists/elissa` | إليسا (Elissa) | 46 | 2026-10-17 |
| `artists/fadhl-shaker` | فضل شاكر (Fadhl Shaker) | 26 | 2026-10-17 |

## Copyright

Lyrics are the property of their respective rights holders. Datasets here are for
personal/research use; verify licensing before redistributing.
