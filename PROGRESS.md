# Lyrics DB — Progress Milestone

**Milestone:** First 120-minute batch run completed  
**Date:** 2026-11-05  
**Status:** Review package ready; 12 of 37 artists completed; human review pending

---

## 1. Snapshot

| Item | Value |
|---|---|
| Repository | `github.com/akbargherbal/lyrics` |
| Branch | `main` |
| Documentation commit | `435c3b0` |
| Job start / end | 11:26–13:26 UTC |
| Elapsed | 7,202.5 s (120 min) |
| Final DB | `data/lyrics.db` (16 MB) |
| Final review package | `review/` (regenerated 13:26 UTC) |
| Final GCS snapshot | `gs://akbar-december-2024-backup/lyrics/snapshots/20261105T135325Z/` |
| Backup verification | DB `integrity_check: ok`; counts match; review files byte-identical |

---

## 2. Completed Work

### 2.1 Pipeline

- [x] SQLite schema with artists, songs, song sources, lyrics, review state, and job state.
- [x] Ingestion of existing sources:
  - fnanen (Elissa, Fadl Shaker)
  - kalimataghani (Elissa, Fadl Shaker)
  - LyricFind/LRCLIB seed (`fadel_chaker_lyrics.json`)
- [x] Arabic normalization and text cleaning.
- [x] iTunes catalog collection (200-result cap per artist).
- [x] LRCLIB plain + synced lyrics fetching, with matching and caching.
- [x] Quality scoring, flags, source agreement, and `needs_review`.
- [x] Review package export:
  - `review/candidates.csv`
  - `review/review_queue.csv`
  - `review/songs.csv`
  - `review/artists.csv`
  - `review/summary.md`
- [x] Resumable job state (`completed_artists`, per-artist progress).
- [x] Local HTTP cache with retry/backoff and 429 handling.

### 2.2 Batch Run Results

| Metric | Value |
|---|---:|
| Total songs | 2,645 |
| Songs with any lyrics | 1,651 (62.4%) |
| Songs with synced lyrics | 1,111 (42.0% of all; 67.3% of songs with lyrics) |
| Songs without lyrics | 994 (37.6%) |
| Lyrics candidates | 2,847 |
| Candidates needing review | 168 |
| Distinct songs needing review | 154 |
| Instrumental songs | 6 |
| Artists completed | 12 |
| Artists with data | 13 (12 complete + Kadim partial) |
| Artists pending | 25 |

### 2.3 Source Distribution

| Source | Lyrics rows | Distinct songs | Preferred |
|---|---:|---:|---:|
| LRCLIB | 2,587 | 1,472 | 1,456 |
| fnanen | 188 | 188 | 133 |
| kalimataghani | 72 | 70 | 50 |
| LyricFind | 0 | 0 | 0 |

Notes:

- LyricFind contributed 255 **catalog** records (`song_sources`) but no full lyrics. Its lyrics pages are 403-blocked and were not bypassed.
- The seed file's 142 lyrics are labelled `lrclib`; 139 rows survive deduplication.
- 12 songs have lyrics but no preferred candidate because every candidate scored below 0.45 or was flagged `no_arabic`. They are all in the review queue.

### 2.4 Completed Artists

`elissa`, `fadl-shaker`, `majid-al-mohandis`, `amr-diab`, `rabeh-saqer`,
`abdul-majeed-abdullah`, `assala-nasri`, `waleed-al-shami`, `najwa-karam`,
`wael-kfoury`, `nawal-el-kuwaitia`, `tamer-hosny`.

Partial: `kadim-al-sahir` (4 songs only; the 120-minute budget expired after the
iTunes catalog was created).

### 2.5 Coverage by Artist

| Artist | Songs | Lyrics | Synced | Coverage |
|---|---:|---:|---:|---:|
| fadl-shaker | 453 | 256 | 35 | 56.5% |
| elissa | 305 | 290 | 135 | 95.1% |
| tamer-hosny | 196 | 181 | 168 | 92.3% |
| amr-diab | 191 | 188 | 172 | 98.4% |
| wael-kfoury | 191 | 128 | 99 | 67.0% |
| majid-al-mohandis | 191 | 113 | 93 | 59.2% |
| rabeh-saqer | 192 | 90 | 77 | 46.9% |
| assala-nasri | 185 | 134 | 103 | 72.4% |
| najwa-karam | 176 | 104 | 95 | 59.1% |
| nawal-el-kuwaitia | 173 | 13 | 8 | 7.5% |
| waleed-al-shami | 191 | 27 | 18 | 14.1% |
| abdul-majeed-abdullah | 197 | 123 | 105 | 62.4% |
| kadim-al-sahir | 4 | 4 | 3 | 100% |

### 2.6 Review Queue

168 candidates (154 distinct songs), by source:

- LRCLIB: 131
- fnanen: 23
- kalimataghani: 14

By kind: plain 155, synced 13.

| Flag | Review queue | All candidates |
|---|---:|---:|
| `low_agreement` | 23 | 23 |
| `short_lyrics` | 14 | 14 |
| `snippet_mismatch` | 8 | 8 |
| `latin_chars` | 8 | 67 |
| `no_arabic` | 8 | 8 |
| `long_lines` | 2 | 2 |
| `one_line` | 2 | 2 |
| `tashkeel` | 58 | 1,338 |

`tashkeel` is informational, not a review trigger by itself.

### 2.7 Backup and Recovery

- [x] Separate backup process using SQLite Online Backup API (WAL-safe).
- [x] Periodic GCS snapshots every 15 minutes.
- [x] Timestamped snapshots plus `latest/` mirror.
- [x] Snapshot contents: DB, review package, logs, metadata (`PLAN.md`, schema,
  pipeline code/config), and HTTP cache archive.
- [x] Restore procedure documented in `batch/BACKUP.md` and `PLAN.md` §6.2.
- [x] Restore test passed: DB integrity OK, counts exact, review files identical.
- [x] Documentation and backup tooling pushed to GitHub.

---

## 3. Known Issues and Findings

### 3.1 Data Quality

1. **Wrong-song LRCLIB matches.** Clear examples:
   - Fadl Shaker — "Ma'qoul": LRCLIB returned different lyrics.
   - Fadl Shaker — "Arab": LRCLIB returned a French song.
   These are the lowest-scoring candidates (`0.105`, `0.190`).
2. **Agreement false positives.** fnanen's correct "Ma'qoul" text is penalised
   because it is compared against the wrong LRCLIB match.
3. **Truncated texts.** Example: Amr Diab — "Ana Maak" (8 lines, 141 chars).
4. **Formatting defects.** One-line collapsed lyrics (2) and very long lines (2).
5. **Transliteration instead of Arabic script.** Example: Elissa —
   "Matkhafch Minni" is Franco-Arabic.
6. **Fadl Shaker dominates the queue** (51 of 168) because the older seed data
   disagrees with newer LRCLIB results.
7. **Duplicate title variants** exist (e.g. "Ya Habibi" / "يا حبيبي",
   "Biaelmi" / "بعلمي [Original]") without a `duplicate_title` flag.
8. **Low coverage for some completed artists:** `waleed-al-shami` 14.1%,
   `nawal-el-kuwaitia` 7.5%, `rabeh-saqer` 46.9%.

### 3.2 Pipeline / Performance

1. **Alias fan-out slows fetching.** Each song may trigger LRCLIB requests for
   every artist-name variant (5–11 names). Observed uncached rate is ~5.9 s/song.
2. **iTunes 200-result cap** may truncate large discographies.
3. **LyricFind provides no lyrics** (403); only catalog metadata is available.
4. **`review/summary.md` is generated, not hand-edited.** Final quality pass must
   run before trusting `needs_review`.

### 3.3 Partial Work

- `kadim-al-sahir` is not marked complete and must restart from the beginning.
- The other 24 untouched artists have no data yet.

---

## 4. Remaining Work

### P0 — Human Review (next action)

- [ ] Review 168 candidates in `review/review_queue.csv` (or filter
  `candidates.csv` by `needs_review=1`).
- [ ] Fill the `decision` column: `keep`, `reject`, `edit`, or `merge`.
- [ ] Add `notes` where the reason is ambiguous.
- [ ] Run `python -m batch.apply_review --csv review/candidates.csv`.
- [ ] Re-export, then verify preferred versions and the 12 songs with no
  preferred candidate.

### P1 — Finish All 37 Artists (25 pending)

Pending artists:

`kadim-al-sahir`, `hussain-al-jassmi`, `oumaima-taleb`, `assi-el-hallani`,
`asma-lmnawar`, `sherine-abdel-wahab`, `saber-rebai`, `melhim-zain`,
`marwan-khoury`, `nabeel-shuail`, `haifa-wahbe`, `balqees`, `nawal-al-zoghbi`,
`jaber-al-kaser`, `rashed-al-majed`, `nancy-ajram`, `abdullah-al-rowaished`,
`mohammed-al-bloushi`, `abadi-al-johar`, `mohammed-abdo`, `talal-maddah`,
`latifa`, `maya-nasri`, `majida-el-roumi`, `mohamed-hamaki`.

Suggested run:

```bash
source .venv/bin/activate
nohup python -m batch.job --config batch/config.yaml --minutes 480 > batch/nohup.out 2>&1 &
nohup bash batch/backup_gcs.sh >/dev/null 2>&1 &
```

Estimated remaining processing: **6–10 hours**, depending on catalog sizes.
Completed artists are skipped automatically.

### P2 — Quality Fixes (after review decisions)

- [ ] Re-fetch or reject wrong LRCLIB matches; prioritise `snippet_mismatch`.
- [ ] Reduce or deduplicate alias lookups to improve throughput.
- [ ] Decide how to treat `tashkeel`: keep for display, strip for search, or both.
- [ ] Detect duplicate title variants before creating new song rows.
- [ ] Resolve the 12 songs with lyrics but no preferred version.
- [ ] Improve coverage for weak artists, potentially with Tarab or manual imports.

### P3 — Export and Application

- [ ] Generate `export/artists/<slug>.json`.
- [ ] Generate `export/combined.json`, `export/catalog.json`, `export/missing.json`.
- [ ] Build FTS5 search over titles, artists, and lyrics.
- [ ] Validate JSON against the karaoke/learning-app interface.
- [ ] Add synced-lyrics playback and line-level karaoke.
- [ ] Decide whether to add word-level sync.

### P4 — Optional

- [ ] Decide whether to use the LRCLIB dump (~46 GiB compressed).
- [ ] Add Tarab as an Arabic fallback source.
- [ ] Add WhisperX/stable-ts alignment for important songs without LRC.
- [ ] Add translations for language learning.

---

## 5. Next Milestone Acceptance Criteria

- [ ] All 37 artists processed and marked complete.
- [ ] Review decisions applied; no unresolved `needs_review=1` in preferred rows.
- [ ] Tier 1 lyrics coverage >= 80%; synced coverage >= 35–50%.
- [ ] No wrong-song matches in a 100-song sample.
- [ ] Export package generated and schema-validated.
- [ ] Fresh restore from GCS tested after the final run.

---

## 6. Operating Rules

- Do not delete `data/` or `review/`.
- Do not change quality rules until review feedback is incorporated.
- Do not bypass LyricFind 403.
- Personal, non-commercial use only; do not redistribute lyrics.
- Do not push generated data to GitHub.
- Back up to GCS before disconnecting the VM.

## 7. Recovery Quick Reference

- Backup guide: `batch/BACKUP.md`
- Full procedure: `PLAN.md` §6.2
- Latest backup: `gs://akbar-december-2024-backup/lyrics/latest/`
- Final snapshot: `gs://akbar-december-2024-backup/lyrics/snapshots/20261105T135325Z/`
- Resume job: rerun the same command; completed artists are skipped.
- Restore DB: stop the job, remove `data/lyrics.db-wal`/`-shm`, download
  `latest/lyrics.db.gz`, gunzip to `data/lyrics.db`.
