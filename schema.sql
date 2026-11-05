-- ============================================================
-- Arabic Lyrics Database — Schema
-- SQLite 3
-- ============================================================
-- الهدف: قاعدة بيانات قانونية (canonical) لكل الفنانين،
-- مع الاحتفاظ بكل نسخة من الكلمات واختيار نسخة مفضّلة لكل أغنية.
-- ============================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;

-- ------------------------------------------------------------
-- الفنانين
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS artists (
    id              INTEGER PRIMARY KEY,
    slug            TEXT NOT NULL UNIQUE,
    name_ar         TEXT NOT NULL,
    name_en         TEXT,
    country         TEXT,
    country_code    TEXT,
    lyricfind_slug  TEXT,
    itunes_id       TEXT,
    musicbrainz_id  TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS artist_aliases (
    id          INTEGER PRIMARY KEY,
    artist_id   INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    alias       TEXT NOT NULL,
    normalized  TEXT NOT NULL,
    UNIQUE(artist_id, normalized)
);

CREATE INDEX IF NOT EXISTS idx_artist_aliases_artist ON artist_aliases(artist_id);
CREATE INDEX IF NOT EXISTS idx_artist_aliases_norm   ON artist_aliases(normalized);

-- ------------------------------------------------------------
-- الأغاني
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS songs (
    id                INTEGER PRIMARY KEY,
    artist_id         INTEGER NOT NULL REFERENCES artists(id),
    canonical_key     TEXT NOT NULL UNIQUE,
    title_ar          TEXT,
    title_en          TEXT,
    normalized_title  TEXT NOT NULL,
    normalized_artist TEXT,
    album             TEXT,
    duration_sec      INTEGER,
    year              TEXT,
    lyricist          TEXT,
    composer          TEXT,
    isrc              TEXT,
    language          TEXT DEFAULT 'ar',
    instrumental      INTEGER NOT NULL DEFAULT 0,
    version           TEXT DEFAULT 'studio',  -- studio | live | remix | acoustic | unknown
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_songs_artist      ON songs(artist_id);
CREATE INDEX IF NOT EXISTS idx_songs_norm_title  ON songs(normalized_title);
CREATE INDEX IF NOT EXISTS idx_songs_album       ON songs(album);
CREATE INDEX IF NOT EXISTS idx_songs_duration    ON songs(duration_sec);

-- ------------------------------------------------------------
-- مصادر الأغنية (Metadata / Catalog)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS song_sources (
    id            INTEGER PRIMARY KEY,
    song_id       INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    source        TEXT NOT NULL,  -- lyricfind | itunes | musicbrainz | fnanen | kalimataghani | lrclib
    source_id     TEXT,
    source_url    TEXT,
    raw_title     TEXT,
    raw_artist    TEXT,
    raw_duration  INTEGER,
    payload_json  TEXT,
    fetched_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(song_id, source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_song_sources_song   ON song_sources(song_id);
CREATE INDEX IF NOT EXISTS idx_song_sources_source ON song_sources(source, source_id);

-- ------------------------------------------------------------
-- نصوص الكلمات (كل النسخ)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lyrics (
    id              INTEGER PRIMARY KEY,
    song_id         INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    source          TEXT NOT NULL,        -- lrclib | fnanen | kalimataghani | tarab | manual
    source_id       TEXT,
    source_url      TEXT,
    kind            TEXT NOT NULL,        -- plain | synced | word_synced
    format          TEXT NOT NULL,        -- text | lrc | yaml
    text_raw        TEXT,
    text            TEXT NOT NULL,
    line_count      INTEGER,
    has_synced      INTEGER NOT NULL DEFAULT 0,
    has_word_sync   INTEGER NOT NULL DEFAULT 0,
    match_score     REAL,
    match_method    TEXT,
    quality_score   REAL,
    quality_flags   TEXT,
    source_agreement REAL,
    needs_review    INTEGER NOT NULL DEFAULT 0,
    manual_verified INTEGER NOT NULL DEFAULT 0,
    review_decision TEXT,                 -- keep | reject | edit | merge
    review_notes    TEXT,
    reviewed_at     TEXT,
    is_preferred    INTEGER NOT NULL DEFAULT 0,
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(song_id, source, source_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_lyrics_song      ON lyrics(song_id);
CREATE INDEX IF NOT EXISTS idx_lyrics_preferred ON lyrics(song_id, is_preferred);
CREATE INDEX IF NOT EXISTS idx_lyrics_kind      ON lyrics(kind);
CREATE INDEX IF NOT EXISTS idx_lyrics_review    ON lyrics(needs_review, quality_score);

-- ------------------------------------------------------------
-- النواقص / المراجعة اليدوية
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS missing (
    id            INTEGER PRIMARY KEY,
    song_id       INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    reason        TEXT NOT NULL,  -- no_match | low_confidence | blocked | bad_metadata
    last_attempt  TEXT NOT NULL DEFAULT (datetime('now')),
    notes         TEXT
);

CREATE INDEX IF NOT EXISTS idx_missing_song   ON missing(song_id);
CREATE INDEX IF NOT EXISTS idx_missing_reason ON missing(reason);

-- ------------------------------------------------------------
-- حالة المهمة (Checkpoint / Resume)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_state (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------
-- البحث النصي (FTS5)
-- ------------------------------------------------------------
-- جدول مستقل ليُملأ من سكربت التصدير/المزامنة.
CREATE VIRTUAL TABLE IF NOT EXISTS lyrics_fts USING fts5(
    song_id UNINDEXED,
    title_ar,
    title_en,
    artist_ar,
    artist_en,
    lyrics_text,
    tokenize = 'unicode61 remove_diacritics 2'
);

-- ------------------------------------------------------------
-- Views مساعدة
-- ------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_preferred_lyrics AS
SELECT
    s.id                AS song_id,
    a.name_ar           AS artist_ar,
    a.name_en           AS artist_en,
    s.title_ar,
    s.title_en,
    s.album,
    s.duration_sec,
    s.instrumental,
    l.source,
    l.source_id,
    l.kind,
    l.format,
    l.text,
    l.has_synced,
    l.has_word_sync,
    l.match_score,
    l.match_method
FROM songs s
JOIN artists a ON a.id = s.artist_id
LEFT JOIN lyrics l ON l.song_id = s.id AND l.is_preferred = 1;

CREATE VIEW IF NOT EXISTS v_artist_stats AS
SELECT
    a.id                AS artist_id,
    a.slug,
    a.name_ar,
    a.name_en,
    COUNT(DISTINCT s.id) AS songs,
    COUNT(DISTINCT CASE WHEN l.id IS NOT NULL THEN s.id END) AS songs_with_lyrics,
    COUNT(DISTINCT CASE WHEN l.has_synced = 1 THEN s.id END) AS songs_with_synced,
    COUNT(DISTINCT CASE WHEN s.instrumental = 1 THEN s.id END) AS instrumental_songs
FROM artists a
LEFT JOIN songs s  ON s.artist_id = a.id
LEFT JOIN lyrics l ON l.song_id = s.id AND l.is_preferred = 1
GROUP BY a.id;

CREATE VIEW IF NOT EXISTS v_review_queue AS
SELECT
    s.id            AS song_id,
    a.name_ar       AS artist_ar,
    a.name_en       AS artist_en,
    s.title_ar,
    s.title_en,
    l.id            AS lyrics_id,
    l.source,
    l.source_id,
    l.kind,
    l.quality_score,
    l.source_agreement,
    l.quality_flags,
    l.needs_review
FROM lyrics l
JOIN songs s   ON s.id = l.song_id
JOIN artists a ON a.id = s.artist_id
WHERE l.needs_review = 1
   OR (l.quality_score IS NOT NULL AND l.quality_score < 0.60)
ORDER BY l.quality_score ASC, s.id;
