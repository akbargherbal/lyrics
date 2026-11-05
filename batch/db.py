"""SQLite helpers for the lyrics database."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from .quality import normalize_arabic


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection, schema_path: Path | str) -> None:
    schema = Path(schema_path).read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()


def canonical_key(artist_id: int, title: str, duration: int | None) -> str:
    bucket = int(round(duration / 5.0) * 5) if duration else "na"
    raw = f"{artist_id}|{normalize_arabic(title)}|{bucket}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def upsert_artist(conn: sqlite3.Connection, artist: dict) -> int:
    slug = artist["slug"]
    row = conn.execute("SELECT id FROM artists WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        cur = conn.execute(
            """
            INSERT INTO artists
                (slug, name_ar, name_en, country, country_code, lyricfind_slug, itunes_id, musicbrainz_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                artist.get("name_ar"),
                artist.get("name_en"),
                artist.get("country"),
                artist.get("country_code"),
                artist.get("lyricfind_slug"),
                artist.get("itunes_artist_id"),
                artist.get("musicbrainz_id"),
            ),
        )
        artist_id = int(cur.lastrowid)
    else:
        artist_id = int(row["id"])

    aliases = [artist.get("name_ar"), artist.get("name_en"), *(artist.get("aliases") or [])]
    for alias in dict.fromkeys(value for value in aliases if value):
        conn.execute(
            "INSERT OR IGNORE INTO artist_aliases (artist_id, alias, normalized) VALUES (?, ?, ?)",
            (artist_id, alias, normalize_arabic(alias)),
        )
    conn.commit()
    return artist_id


def get_or_create_song(
    conn: sqlite3.Connection,
    *,
    artist_id: int,
    title: str,
    title_ar: str | None = None,
    title_en: str | None = None,
    album: str | None = None,
    duration: int | None = None,
    year: str | None = None,
    lyricist: str | None = None,
    composer: str | None = None,
    isrc: str | None = None,
    language: str = "ar",
    instrumental: bool = False,
    version: str = "studio",
) -> int:
    normalized = normalize_arabic(title)
    rows = conn.execute(
        "SELECT * FROM songs WHERE artist_id = ? AND normalized_title = ?",
        (artist_id, normalized),
    ).fetchall()

    chosen = None
    for row in rows:
        row_duration = row["duration_sec"]
        if duration is None:
            chosen = row
            break
        if row_duration is None:
            chosen = row
            break
        if abs(int(row_duration) - int(duration)) <= 5:
            chosen = row
            break
    if chosen is None and rows and duration is None:
        chosen = rows[0]

    if chosen is not None:
        updates = {}
        for key, value in {
            "album": album,
            "duration_sec": duration,
            "year": year,
            "lyricist": lyricist,
            "composer": composer,
            "isrc": isrc,
            "instrumental": 1 if instrumental else None,
        }.items():
            if value is not None and chosen[key] in (None, 0, ""):
                updates[key] = value
        if updates:
            assignments = ", ".join(f"{key} = ?" for key in updates)
            conn.execute(
                f"UPDATE songs SET {assignments} WHERE id = ?",
                (*updates.values(), chosen["id"]),
            )
        if duration and not chosen["duration_sec"]:
            conn.execute(
                "UPDATE songs SET canonical_key = ? WHERE id = ?",
                (canonical_key(artist_id, title, duration), chosen["id"]),
            )
        return int(chosen["id"])

    key = canonical_key(artist_id, title, duration)
    try:
        cur = conn.execute(
            """
            INSERT INTO songs
                (artist_id, canonical_key, title_ar, title_en, normalized_title, normalized_artist,
                 album, duration_sec, year, lyricist, composer, isrc, language, instrumental, version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artist_id,
                key,
                title_ar or (title if not title_en else None),
                title_en or (title if not title_ar else None),
                normalized,
                "",
                album,
                duration,
                year,
                lyricist,
                composer,
                isrc,
                language,
                1 if instrumental else 0,
                version,
            ),
        )
        return int(cur.lastrowid)
    except sqlite3.IntegrityError:
        row = conn.execute("SELECT id FROM songs WHERE canonical_key = ?", (key,)).fetchone()
        if row:
            return int(row["id"])
        raise


def add_song_source(
    conn: sqlite3.Connection,
    *,
    song_id: int,
    source: str,
    source_id: str | None,
    source_url: str | None = None,
    raw_title: str | None = None,
    raw_artist: str | None = None,
    raw_duration: int | None = None,
    payload: dict | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO song_sources
            (song_id, source, source_id, source_url, raw_title, raw_artist, raw_duration, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            song_id,
            source,
            source_id or "",
            source_url,
            raw_title,
            raw_artist,
            raw_duration,
            json.dumps(payload, ensure_ascii=False) if payload else None,
        ),
    )


def add_lyric(
    conn: sqlite3.Connection,
    *,
    song_id: int,
    source: str,
    source_id: str | None,
    source_url: str | None,
    kind: str,
    fmt: str,
    text_raw: str,
    text: str,
    line_count: int,
    has_synced: bool,
    has_word_sync: bool = False,
    match_score: float | None = None,
    match_method: str | None = None,
) -> int:
    conn.execute(
        """
        INSERT INTO lyrics
            (song_id, source, source_id, source_url, kind, format, text_raw, text,
             line_count, has_synced, has_word_sync, match_score, match_method)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(song_id, source, source_id, kind) DO UPDATE SET
            source_url = excluded.source_url,
            text_raw = excluded.text_raw,
            text = excluded.text,
            line_count = excluded.line_count,
            has_synced = excluded.has_synced,
            has_word_sync = excluded.has_word_sync,
            match_score = excluded.match_score,
            match_method = excluded.match_method,
            fetched_at = datetime('now')
        """,
        (
            song_id,
            source,
            source_id or "",
            source_url,
            kind,
            fmt,
            text_raw,
            text,
            line_count,
            1 if has_synced else 0,
            1 if has_word_sync else 0,
            match_score,
            match_method,
        ),
    )
    row = conn.execute(
        "SELECT id FROM lyrics WHERE song_id = ? AND source = ? AND source_id = ? AND kind = ?",
        (song_id, source, source_id or "", kind),
    ).fetchone()
    return int(row["id"]) if row else 0


def set_job_state(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        """
        INSERT INTO job_state (key, value, updated_at) VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
        """,
        (key, json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value),
    )


def get_job_state(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM job_state WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]
