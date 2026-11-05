"""Time-boxed batch job: clean, enrich, score and export lyrics for review.

Run from the project root:

    python -m batch.job --config batch/config.yaml --minutes 120

The job is resumable: it writes to SQLite and can be stopped/restarted.
At the end it writes a review package under review/.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import signal
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import db, quality, sources

LOG = logging.getLogger("lyrics-batch")
STOP_REQUESTED = False


def _handle_stop(signum, frame):  # noqa: ANN001
    global STOP_REQUESTED
    STOP_REQUESTED = True
    LOG.warning("stop requested (signal %s); finishing current step...", signum)


def parse_duration(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    match = re.match(r"^(\d+):(\d{1,2})$", text)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    return None


def load_config(path: Path) -> dict:
    defaults = {
        "artists_file": "artists.yaml",
        "db_path": "data/lyrics.db",
        "schema_path": "schema.sql",
        "review_dir": "review",
        "cache_dir": "batch/cache",
        "time_budget_minutes": 120,
        "priority_artists": [],
        "itunes": {"enabled": True, "country": "US", "limit": 200},
        "lrclib": {"enabled": True},
        "existing_sources": [],
    }
    if not path.exists():
        return defaults
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(defaults.get(key), dict):
            defaults[key].update(value)
        else:
            defaults[key] = value
    return defaults


def load_artists(path: Path) -> list[dict]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc.get("artists", [])


def find_artist(artists: list[dict], name: str | None) -> dict | None:
    if not name:
        return None
    n_ar = quality.normalize_arabic(name)
    n_lat = quality.normalize_latin(name)
    for artist in artists:
        aliases = [artist.get("name_ar"), artist.get("name_en"), *(artist.get("aliases") or [])]
        for alias in aliases:
            if not alias:
                continue
            if n_ar and quality.normalize_arabic(alias) == n_ar:
                return artist
            if n_lat and quality.normalize_latin(alias) == n_lat:
                return artist
    name_key = quality.latin_key(name)
    if name_key and quality.key_is_safe(name_key):
        key_matches = []
        for artist in artists:
            aliases = [artist.get("name_en"), *(artist.get("aliases") or [])]
            for alias in aliases:
                if not alias:
                    continue
                alias_key = quality.latin_key(alias)
                if quality.key_is_safe(alias_key) and (
                    alias_key in name_key or name_key in alias_key
                ):
                    key_matches.append(artist)
                    break
        unique = {artist["slug"]: artist for artist in key_matches}
        if len(unique) == 1:
            return next(iter(unique.values()))

    for artist in artists:
        aliases = [artist.get("name_ar"), artist.get("name_en"), *(artist.get("aliases") or [])]
        for alias in aliases:
            if not alias:
                continue
            a_ar = quality.normalize_arabic(alias)
            a_lat = quality.normalize_latin(alias)
            if (n_ar and a_ar and (n_ar in a_ar or a_ar in n_ar)) or (
                n_lat and a_lat and (n_lat in a_lat or a_lat in n_lat)
            ):
                return artist
    return None


def _title_fields(title: str) -> tuple[str | None, str | None]:
    if quality.ARABIC_RE.search(title or ""):
        return title, None
    return None, title


def ingest_fnanen(conn, path: Path, artists: list[dict]) -> int:
    doc = json.loads(path.read_text(encoding="utf-8"))
    artist = find_artist(artists, doc.get("artist"))
    if not artist:
        LOG.warning("unknown artist in %s: %s", path, doc.get("artist"))
        return 0
    artist_id = db.upsert_artist(conn, artist)
    count = 0
    for song in doc.get("songs", []):
        title = song.get("title") or ""
        raw = song.get("lyrics") or ""
        if not title or not raw.strip():
            continue
        analysis = quality.analyze_lyrics(raw)
        title_ar, title_en = _title_fields(title)
        song_id = db.get_or_create_song(
            conn,
            artist_id=artist_id,
            title=title,
            title_ar=title_ar,
            title_en=title_en,
            year=song.get("year"),
            lyricist=song.get("lyricist"),
            composer=song.get("composer"),
        )
        source_id = str(song.get("id") or song.get("url") or title)
        db.add_song_source(
            conn,
            song_id=song_id,
            source="fnanen",
            source_id=source_id,
            source_url=song.get("url"),
            raw_title=title,
            raw_artist=doc.get("artist"),
            payload={"year": song.get("year"), "lyricist": song.get("lyricist"), "composer": song.get("composer"), "views": song.get("views")},
        )
        db.add_lyric(
            conn,
            song_id=song_id,
            source="fnanen",
            source_id=source_id,
            source_url=song.get("url"),
            kind="plain",
            fmt="text",
            text_raw=raw,
            text=analysis["text"],
            line_count=analysis["line_count"],
            has_synced=False,
        )
        count += 1
    conn.commit()
    LOG.info("fnanen: ingested %s songs from %s", count, path)
    return count


def ingest_kalimataghani(conn, path: Path, artists: list[dict]) -> int:
    doc = json.loads(path.read_text(encoding="utf-8"))
    dataset = doc.get("dataset") or {}
    artist_name = dataset.get("artist_ar") or (doc.get("songs") or [{}])[0].get("artist")
    artist = find_artist(artists, artist_name)
    if not artist:
        LOG.warning("unknown artist in %s: %s", path, artist_name)
        return 0
    artist_id = db.upsert_artist(conn, artist)
    count = 0
    for song in doc.get("songs", []):
        title = song.get("title") or ""
        raw = song.get("lyrics") or ""
        if not title or not raw.strip():
            continue
        analysis = quality.analyze_lyrics(raw)
        title_ar, title_en = _title_fields(title)
        song_id = db.get_or_create_song(
            conn,
            artist_id=artist_id,
            title=title,
            title_ar=title_ar,
            title_en=title_en,
        )
        source_id = str(song.get("slug") or song.get("url") or title)
        db.add_song_source(
            conn,
            song_id=song_id,
            source="kalimataghani",
            source_id=source_id,
            source_url=song.get("url"),
            raw_title=title,
            raw_artist=song.get("artist") or artist_name,
            payload={"notes": song.get("notes"), "contributor": song.get("contributor")},
        )
        db.add_lyric(
            conn,
            song_id=song_id,
            source="kalimataghani",
            source_id=source_id,
            source_url=song.get("url"),
            kind="plain",
            fmt="text",
            text_raw=raw,
            text=analysis["text"],
            line_count=analysis["line_count"],
            has_synced=False,
        )
        count += 1
    conn.commit()
    LOG.info("kalimataghani: ingested %s songs from %s", count, path)
    return count


def ingest_fadel_lyricfind(conn, path: Path, artists: list[dict]) -> int:
    doc = json.loads(path.read_text(encoding="utf-8"))
    artist = find_artist(artists, doc.get("artist") or "Fadel Chaker")
    if not artist:
        LOG.warning("unknown artist in %s", path)
        return 0
    artist_id = db.upsert_artist(conn, artist)
    count = 0
    for song in doc.get("songs", []):
        title = song.get("title") or ""
        if not title:
            continue
        duration = parse_duration(song.get("duration"))
        title_ar, title_en = _title_fields(title)
        if not title_ar and song.get("title_romanized"):
            title_en = song.get("title_romanized")
        song_id = db.get_or_create_song(
            conn,
            artist_id=artist_id,
            title=title,
            title_ar=title_ar,
            title_en=title_en or song.get("title_romanized"),
            album=(song.get("album") or {}).get("title"),
            duration=duration,
            language=song.get("language") or "ar",
            instrumental=bool(song.get("instrumental")),
        )
        source_id = str(song.get("lfid") or song.get("slug") or title)
        db.add_song_source(
            conn,
            song_id=song_id,
            source="lyricfind",
            source_id=source_id,
            source_url=song.get("lyricfind_url"),
            raw_title=title,
            raw_artist=(song.get("artist") or {}).get("name") or doc.get("artist"),
            raw_duration=duration,
            payload={
                "snippet": song.get("lyricfind_snippet"),
                "title_romanized": song.get("title_romanized"),
                "album": song.get("album"),
                "artists": song.get("artists"),
            },
        )
        raw = song.get("lyrics")
        if raw and raw.strip():
            analysis = quality.analyze_lyrics(raw)
            lyric_source = (song.get("lyrics_source") or "lrclib").lower()
            db.add_lyric(
                conn,
                song_id=song_id,
                source=lyric_source,
                source_id=str(song.get("lrclib_id") or source_id),
                source_url=song.get("lyricfind_url"),
                kind="plain",
                fmt="text",
                text_raw=raw,
                text=analysis["text"],
                line_count=analysis["line_count"],
                has_synced=False,
            )
        count += 1
    conn.commit()
    LOG.info("lyricfind/lrclib seed: ingested %s songs from %s", count, path)
    return count


def ingest_existing(conn, cfg: dict, artists: list[dict]) -> None:
    for raw_path in cfg.get("existing_sources", []):
        path = Path(raw_path)
        if not path.exists():
            LOG.warning("existing source not found: %s", path)
            continue
        name = str(path).lower()
        if "kalimataghani" in name:
            ingest_kalimataghani(conn, path, artists)
        elif "fnanen" in name:
            ingest_fnanen(conn, path, artists)
        elif "fadel_chaker_lyrics" in name:
            ingest_fadel_lyricfind(conn, path, artists)
        else:
            LOG.warning("unknown existing source type: %s", path)


def _median(values: list[int]) -> int:
    return int(statistics.median(values)) if values else 0


def quality_pass(conn) -> dict:
    rows = conn.execute(
        """
        SELECT l.id, l.song_id, l.source, l.source_id, l.kind, l.text, l.text_raw,
               l.review_decision, l.manual_verified,
               s.artist_id, s.title_ar, s.title_en, s.lyricist, s.composer, s.year
        FROM lyrics l
        JOIN songs s ON s.id = l.song_id
        """
    ).fetchall()

    snippet_rows = conn.execute(
        "SELECT song_id, payload_json FROM song_sources WHERE source = 'lyricfind' AND payload_json IS NOT NULL"
    ).fetchall()
    snippets: dict[int, str] = {}
    for row in snippet_rows:
        try:
            payload = json.loads(row["payload_json"])
            if payload.get("snippet"):
                snippets[int(row["song_id"])] = payload["snippet"]
        except Exception:
            continue

    token_counts: dict[int, list[int]] = {}
    analyzed = {}
    for row in rows:
        analysis_text = quality.strip_lrc(row["text"]) if row["kind"] in ("synced", "word_synced") else row["text"]
        analysis = quality.analyze_lyrics(analysis_text)
        analyzed[row["id"]] = analysis
        token_counts.setdefault(int(row["artist_id"]), []).append(analysis["token_count"])
    medians = {artist_id: _median(values) for artist_id, values in token_counts.items()}

    by_song: dict[int, list] = {}
    for row in rows:
        by_song.setdefault(int(row["song_id"]), []).append(row)

    updated = 0
    review_count = 0
    for song_id, group in by_song.items():
        sets = {
            row["id"]: set(quality.tokenize(
                quality.strip_lrc(row["text"]) if row["kind"] in ("synced", "word_synced") else row["text"]
            ))
            for row in group
        }
        for row in group:
            lyric_id = row["id"]
            analysis = analyzed[lyric_id]
            flags = list(analysis["flags"])

            others = [sets[other["id"]] for other in group if other["id"] != lyric_id]
            if others:
                agreement = max(quality.jaccard(sets[lyric_id], other) for other in others)
                if agreement < 0.50:
                    flags.append("low_agreement")
            else:
                agreement = 0.50

            snippet = snippets.get(song_id)
            snip_agreement = quality.snippet_agreement(
                quality.strip_lrc(row["text"]) if row["kind"] in ("synced", "word_synced") else row["text"],
                snippet,
            ) if snippet else None
            if snip_agreement is not None and snip_agreement < 0.15:
                flags.append("snippet_mismatch")

            completeness = quality.completeness_score(
                analysis["token_count"], medians.get(int(row["artist_id"]))
            )
            format_s = quality.format_score(analysis)
            metadata_s = quality.metadata_score(row["lyricist"], row["composer"], row["year"])
            score = quality.compute_quality(
                completeness=completeness,
                agreement=agreement,
                format_s=format_s,
                metadata_s=metadata_s,
                flags=flags,
            )
            decision = row["review_decision"]
            manual_verified = int(row["manual_verified"] or 0)
            if decision == "keep":
                manual_verified = 1
                needs = False
            elif decision == "reject":
                needs = False
            elif decision in ("edit", "merge"):
                needs = True
            else:
                needs = quality.needs_review(score, flags)
            if needs:
                review_count += 1

            stored_text = row["text"]
            if row["kind"] not in ("synced", "word_synced"):
                stored_text = analysis["text"]
            conn.execute(
                """
                UPDATE lyrics
                SET text = ?, line_count = ?, quality_score = ?, quality_flags = ?,
                    source_agreement = ?, needs_review = ?, manual_verified = ?
                WHERE id = ?
                """,
                (
                    stored_text,
                    analysis["line_count"],
                    score,
                    json.dumps(sorted(set(flags)), ensure_ascii=False),
                    agreement,
                    1 if needs else 0,
                    manual_verified,
                    lyric_id,
                ),
            )
            updated += 1

        # choose preferred, excluding rejected candidates
        scored = []
        for row in group:
            qrow = conn.execute(
                "SELECT quality_score, manual_verified, kind, review_decision, quality_flags FROM lyrics WHERE id = ?",
                (row["id"],),
            ).fetchone()
            if qrow["review_decision"] == "reject":
                continue
            flags = []
            try:
                flags = json.loads(qrow["quality_flags"] or "[]")
            except Exception:
                pass
            manual = int(qrow["manual_verified"] or 0)
            score = float(qrow["quality_score"] or 0)
            if manual != 1:
                if "no_arabic" in flags or score < 0.45:
                    continue
            synced_ok = (
                1
                if qrow["kind"] in ("synced", "word_synced")
                and score >= 0.55
                else 0
            )
            scored.append((manual, synced_ok, score, row["id"]))
        scored.sort(reverse=True)
        conn.execute("UPDATE lyrics SET is_preferred = 0 WHERE song_id = ?", (song_id,))
        if scored:
            conn.execute("UPDATE lyrics SET is_preferred = 1 WHERE id = ?", (scored[0][3],))

    conn.commit()
    LOG.info("quality pass: updated %s lyric candidates, %s need review", updated, review_count)
    return {"updated": updated, "needs_review": review_count}


def _csv_write(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def export_review(conn, review_dir: Path) -> dict:
    review_dir.mkdir(parents=True, exist_ok=True)

    candidates = conn.execute(
        """
        SELECT l.id AS candidate_id, a.name_ar AS artist_ar, a.name_en AS artist_en,
               COALESCE(s.title_ar, s.title_en) AS title, s.title_en, s.title_ar,
               s.album, s.duration_sec, l.source, l.kind, l.quality_score,
               l.source_agreement, l.quality_flags, l.line_count, l.text,
               l.source_url, l.needs_review, l.review_decision, l.review_notes
        FROM lyrics l
        JOIN songs s ON s.id = l.song_id
        JOIN artists a ON a.id = s.artist_id
        ORDER BY l.needs_review DESC, l.quality_score ASC, a.name_en, s.id
        """
    ).fetchall()

    candidate_rows = []
    for row in candidates:
        text = row["text"] or ""
        preview_text = quality.strip_lrc(text) if row["kind"] in ("synced", "word_synced") else text
        preview = re.sub(r"\s+", " ", preview_text).strip()[:260]
        candidate_rows.append(
            {
                "candidate_id": row["candidate_id"],
                "artist_ar": row["artist_ar"],
                "artist_en": row["artist_en"],
                "title": row["title"],
                "title_en": row["title_en"],
                "title_ar": row["title_ar"],
                "album": row["album"],
                "duration_sec": row["duration_sec"],
                "source": row["source"],
                "kind": row["kind"],
                "quality_score": row["quality_score"],
                "source_agreement": row["source_agreement"],
                "flags": row["quality_flags"],
                "line_count": row["line_count"],
                "token_count": len(quality.tokenize(preview_text)),
                "preview": preview,
                "source_url": row["source_url"],
                "needs_review": row["needs_review"],
                "decision": row["review_decision"] or "",
                "notes": row["review_notes"] or "",
            }
        )

    fields = [
        "candidate_id", "artist_ar", "artist_en", "title", "title_en", "title_ar",
        "album", "duration_sec", "source", "kind", "quality_score", "source_agreement",
        "flags", "line_count", "token_count", "preview", "source_url", "needs_review",
        "decision", "notes",
    ]
    _csv_write(review_dir / "candidates.csv", candidate_rows, fields)
    _csv_write(
        review_dir / "review_queue.csv",
        [row for row in candidate_rows if int(row["needs_review"] or 0) == 1],
        fields,
    )

    songs = conn.execute(
        """
        SELECT s.id AS song_id, a.name_ar AS artist_ar, a.name_en AS artist_en,
               s.title_ar, s.title_en, s.album, s.duration_sec, s.instrumental,
               (SELECT COUNT(*) FROM lyrics l2 WHERE l2.song_id = s.id) AS alternatives,
               l.source AS preferred_source, l.kind AS preferred_kind,
               l.quality_score AS preferred_quality, l.has_synced
        FROM songs s
        JOIN artists a ON a.id = s.artist_id
        LEFT JOIN lyrics l ON l.song_id = s.id AND l.is_preferred = 1
        ORDER BY a.name_en, s.id
        """
    ).fetchall()
    _csv_write(
        review_dir / "songs.csv",
        [dict(row) for row in songs],
        ["song_id", "artist_ar", "artist_en", "title_ar", "title_en", "album", "duration_sec",
         "instrumental", "alternatives", "preferred_source", "preferred_kind",
         "preferred_quality", "has_synced"],
    )

    stats = conn.execute("SELECT * FROM v_artist_stats ORDER BY name_en").fetchall()
    _csv_write(review_dir / "artists.csv", [dict(row) for row in stats], list(stats[0].keys()) if stats else [])

    total_songs = conn.execute("SELECT COUNT(*) AS n FROM songs").fetchone()["n"]
    songs_with_lyrics = conn.execute("SELECT COUNT(DISTINCT song_id) AS n FROM lyrics").fetchone()["n"]
    songs_with_synced = conn.execute("SELECT COUNT(DISTINCT song_id) AS n FROM lyrics WHERE has_synced = 1").fetchone()["n"]
    review_total = conn.execute("SELECT COUNT(*) AS n FROM lyrics WHERE needs_review = 1").fetchone()["n"]
    source_counts = conn.execute("SELECT source, COUNT(*) AS n FROM lyrics GROUP BY source ORDER BY n DESC").fetchall()
    flag_counts = {}
    for row in conn.execute("SELECT quality_flags FROM lyrics WHERE quality_flags IS NOT NULL"):
        try:
            for flag in json.loads(row["quality_flags"]):
                flag_counts[flag] = flag_counts.get(flag, 0) + 1
        except Exception:
            continue

    summary = [
        "# Lyrics Batch — Review Summary",
        "",
        f"- Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Total songs: {total_songs}",
        f"- Songs with any lyrics: {songs_with_lyrics}",
        f"- Songs with synced lyrics: {songs_with_synced}",
        f"- Candidates needing review: {review_total}",
        "",
        "## Sources",
        "",
        "| Source | Candidates |",
        "|---|---:|",
    ]
    for row in source_counts:
        summary.append(f"| {row['source']} | {row['n']} |")
    summary += ["", "## Flags", "", "| Flag | Count |", "|---|---:|"]
    for flag, count in sorted(flag_counts.items(), key=lambda item: -item[1]):
        summary.append(f"| {flag} | {count} |")
    summary += [
        "",
        "## How to review",
        "",
        "1. Open `review/candidates.csv` in Excel/LibreOffice.",
        "2. Filter `needs_review = 1` first.",
        "3. Fill `decision` with one of: `keep`, `reject`, `edit`, `merge`.",
        "4. Add notes in `notes` when needed.",
        "5. Send the CSV back, or run `python -m batch.apply_review --csv review/candidates.csv`.",
        "",
        "`review_queue.csv` contains only the problematic candidates.",
    ]
    (review_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    return {
        "total_songs": total_songs,
        "songs_with_lyrics": songs_with_lyrics,
        "songs_with_synced": songs_with_synced,
        "review_total": review_total,
        "candidates": len(candidate_rows),
    }


def mark_artist_complete(conn, slug: str) -> None:
    completed = db.get_job_state(conn, "completed_artists", [])
    if not isinstance(completed, list):
        completed = []
    if slug not in completed:
        completed.append(slug)
        db.set_job_state(conn, "completed_artists", completed)


def process_artist(conn, artist: dict, client, cfg: dict, deadline: float, limit_songs: int | None) -> tuple[bool, int]:
    """Returns (finished_all, processed_songs)."""
    artist_id = db.upsert_artist(conn, artist)
    LOG.info("artist: %s (%s)", artist.get("name_en"), artist.get("slug"))
    if not cfg.get("itunes", {}).get("enabled", True):
        LOG.info("  iTunes disabled; skipping catalog fetch")
        return True, 0
    catalog = sources.itunes_catalog(
        client,
        artist,
        country=cfg["itunes"].get("country", "US"),
        limit=int(cfg["itunes"].get("limit", 200)),
    )
    LOG.info("  iTunes catalog: %s songs", len(catalog))
    if limit_songs:
        catalog = catalog[:limit_songs]

    processed = 0
    for index, track in enumerate(catalog, 1):
        if STOP_REQUESTED or time.monotonic() >= deadline:
            return False, processed
        title = track["title"]
        title_ar, title_en = _title_fields(title)
        song_id = db.get_or_create_song(
            conn,
            artist_id=artist_id,
            title=title,
            title_ar=title_ar,
            title_en=title_en,
            album=track.get("album"),
            duration=track.get("duration"),
            isrc=track.get("isrc"),
        )
        db.add_song_source(
            conn,
            song_id=song_id,
            source="itunes",
            source_id=track.get("track_id"),
            raw_title=title,
            raw_artist=track.get("artist"),
            raw_duration=track.get("duration"),
            payload=track,
        )

        if cfg.get("lrclib", {}).get("enabled", True):
            result = sources.fetch_lrclib(client, artist, track)
            if result:
                record = result["record"]
                source_id = str(record.get("id") or "")
                if record.get("instrumental"):
                    conn.execute("UPDATE songs SET instrumental = 1 WHERE id = ?", (song_id,))
                plain = record.get("plainLyrics")
                synced = record.get("syncedLyrics")
                if plain:
                    analysis = quality.analyze_lyrics(plain)
                    db.add_lyric(
                        conn,
                        song_id=song_id,
                        source="lrclib",
                        source_id=source_id,
                        source_url=f"https://lrclib.net/api/get/{source_id}",
                        kind="plain",
                        fmt="text",
                        text_raw=plain,
                        text=analysis["text"],
                        line_count=analysis["line_count"],
                        has_synced=False,
                        match_score=result["score"],
                        match_method=result["method"],
                    )
                if synced:
                    stripped = quality.strip_lrc(synced)
                    analysis = quality.analyze_lyrics(stripped)
                    db.add_lyric(
                        conn,
                        song_id=song_id,
                        source="lrclib",
                        source_id=source_id,
                        source_url=f"https://lrclib.net/api/get/{source_id}",
                        kind="synced",
                        fmt="lrc",
                        text_raw=synced,
                        text=quality.clean_text(synced),
                        line_count=analysis["line_count"],
                        has_synced=True,
                        has_word_sync=bool(record.get("hasWordSync")),
                        match_score=result["score"],
                        match_method=result["method"],
                    )
                db.add_song_source(
                    conn,
                    song_id=song_id,
                    source="lrclib",
                    source_id=source_id,
                    source_url=f"https://lrclib.net/api/get/{source_id}",
                    raw_title=record.get("trackName"),
                    raw_artist=record.get("artistName"),
                    raw_duration=record.get("duration"),
                    payload={
                        "match_score": result["score"],
                        "method": result["method"],
                        "instrumental": record.get("instrumental"),
                        "hasWordSync": record.get("hasWordSync"),
                    },
                )
            else:
                LOG.debug("  no LRCLIB match: %s", title)

        processed += 1
        if processed % 10 == 0:
            conn.commit()
            db.set_job_state(conn, "last_artist", artist.get("slug"))
            db.set_job_state(conn, "last_song", title)
            LOG.info("  [%s/%s] %s", index, len(catalog), title)

    conn.commit()
    db.set_job_state(conn, "last_artist", artist.get("slug"))
    if limit_songs is None:
        mark_artist_complete(conn, artist["slug"])
    conn.commit()
    LOG.info("  done: %s songs processed", processed)
    return True, processed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Time-boxed lyrics cleaning/enrichment job")
    parser.add_argument("--config", default="batch/config.yaml")
    parser.add_argument("--minutes", type=int, default=None, help="time budget in minutes")
    parser.add_argument("--only", default=None, help="comma-separated artist slugs")
    parser.add_argument("--skip-fetch", action="store_true", help="only clean/score existing data")
    parser.add_argument("--limit-songs", type=int, default=None, help="test limit per artist")
    parser.add_argument("--db", default=None, help="override database path")
    parser.add_argument("--force", action="store_true", help="reprocess artists already completed")
    args = parser.parse_args(argv)

    global STOP_REQUESTED
    STOP_REQUESTED = False
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    cfg = load_config(Path(args.config))
    if args.minutes is not None:
        cfg["time_budget_minutes"] = args.minutes
    if args.db:
        cfg["db_path"] = args.db

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler("batch/run.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    all_artists = load_artists(Path(cfg["artists_file"]))
    artists = all_artists
    if args.only:
        wanted = {value.strip() for value in args.only.split(",") if value.strip()}
        artists = [a for a in all_artists if a.get("slug") in wanted or a.get("name_en") in wanted or a.get("name_ar") in wanted]
    if not artists:
        LOG.error("no artists selected")
        return 2

    priority = {slug: index for index, slug in enumerate(cfg.get("priority_artists", []))}
    artists = sorted(
        artists,
        key=lambda artist: (
            priority.get(artist.get("slug"), len(priority)),
            artist.get("rank", 999),
        ),
    )

    conn = db.connect(cfg["db_path"])
    db.init_db(conn, cfg["schema_path"])
    if not args.force and not args.skip_fetch:
        completed = set(db.get_job_state(conn, "completed_artists", []) or [])
        artists = [artist for artist in artists if artist.get("slug") not in completed]
    start = time.monotonic()
    deadline = start + int(cfg["time_budget_minutes"]) * 60

    LOG.info("job start: %s artists, budget %s minutes", len(artists), cfg["time_budget_minutes"])
    ingest_existing(conn, cfg, all_artists)

    client = sources.HttpClient(
        Path(cfg["cache_dir"]),
        min_interval=float(cfg.get("lrclib", {}).get("min_interval", 0.75)),
    )

    processed_total = 0
    finished = 0
    if not args.skip_fetch:
        for artist in artists:
            if STOP_REQUESTED or time.monotonic() >= deadline:
                break
            done, processed = process_artist(
                conn, artist, client, cfg, deadline, args.limit_songs
            )
            processed_total += processed
            if done:
                finished += 1
            else:
                break
    else:
        LOG.info("skip-fetch enabled: only cleaning/scoring existing data")

    quality_result = quality_pass(conn)
    export_result = export_review(conn, Path(cfg["review_dir"]))
    elapsed = round(time.monotonic() - start, 1)

    db.set_job_state(conn, "last_run", {
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_seconds": elapsed,
        "artists_finished": finished,
        "songs_processed": processed_total,
        "quality": quality_result,
        "export": export_result,
    })
    conn.commit()
    conn.close()

    LOG.info(
        "done in %.1fs: songs=%s lyrics=%s synced=%s review=%s",
        elapsed,
        export_result["total_songs"],
        export_result["songs_with_lyrics"],
        export_result["songs_with_synced"],
        export_result["review_total"],
    )
    print(json.dumps({"elapsed_seconds": elapsed, **export_result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
