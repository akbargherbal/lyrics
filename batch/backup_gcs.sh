#!/usr/bin/env bash
# Periodic, crash-safe backup of the lyrics batch progress to Google Cloud Storage.
# Uses SQLite's online backup API so it is safe while batch.job is writing.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.." || exit 1

BUCKET="${BACKUP_BUCKET:-gs://akbar-december-2024-backup/lyrics}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-900}"
LOG="batch/backup.log"
LOCK="batch/.backup.lock"

export CLOUDSDK_CORE_DISABLE_PROMPTS=1
mkdir -p batch

log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" >> "$LOG"; }

# Prevent overlapping snapshots. The lock is held only while a snapshot is
# running, not during sleep, so killing the loop cannot leave an orphan sleep
# process holding the lock.
acquire_lock() {
  exec 9>"$LOCK"
  if ! flock -n 9; then
    exec 9>&-
    return 1
  fi
  return 0
}
release_lock() { exec 9>&-; }

job_pid() { pgrep -f '^python[0-9.]* -m batch\.job' | head -1 || true; }

snapshot_once() {
  local ts tmp job running artist progress commit rc
  ts="$(date -u '+%Y%m%dT%H%M%SZ')"
  tmp="$(mktemp -d /tmp/opencode/lyrics-backup.XXXXXX)" || { log "ERROR: mktemp failed"; return 1; }

  mkdir -p "$tmp/latest/logs"

  # Consistent SQLite snapshot (includes WAL contents).
  if ! python3 - "$tmp/latest/lyrics.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect("file:data/lyrics.db?mode=ro", uri=True, timeout=60)
dst = sqlite3.connect(sys.argv[1])
try:
    src.backup(dst)
finally:
    dst.close()
    src.close()
PY
  then
    log "ERROR: sqlite online backup failed"
    rm -rf "$tmp"
    return 1
  fi

  if [ ! -s "$tmp/latest/lyrics.db" ]; then
    log "ERROR: sqlite backup is empty"
    rm -rf "$tmp"
    return 1
  fi
  gzip -f "$tmp/latest/lyrics.db"

  # Review package (CSV/Markdown only; generated files are small).
  if [ -d review ]; then
    cp -a review "$tmp/latest/review"
  fi

  # Logs.
  local f
  for f in batch/run.log batch/nohup.out batch/backup.log; do
    if [ -f "$f" ]; then
      gzip -c "$f" > "$tmp/latest/logs/$(basename "$f").gz"
    fi
  done

  # Recovery metadata: plan, registry, schema, config and pipeline code.
  mkdir -p "$tmp/latest/meta"
  for f in PLAN.md PROGRESS.md artists.yaml schema.sql batch/BACKUP.md batch/backup_gcs.sh \
           batch/config.yaml batch/requirements.txt batch/job.py batch/quality.py \
           batch/sources.py batch/db.py batch/apply_review.py batch/README.md; do
    if [ -f "$f" ]; then
      cp "$f" "$tmp/latest/meta/$(basename "$f")"
    fi
  done

  # Job / repo metadata.
  job="$(job_pid)"
  if [ -n "$job" ]; then running="true"; else running="false"; fi
  artist="$(grep -a 'artist:' batch/nohup.out 2>/dev/null | tail -1 | grep -o '([a-z-]*)' | tr -d '()' || true)"
  progress="$(grep -o '\[[0-9]*/[0-9]*\]' batch/nohup.out 2>/dev/null | tail -1 || true)"
  commit="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

  if ! python3 - "$tmp/latest/lyrics.db.gz" "$tmp/latest/manifest.json" \
      "$ts" "$running" "${job:-}" "$artist" "$progress" "$commit" <<'PY'
import gzip, json, sqlite3, sys, tempfile, os

db_gz, out, ts, running, job, artist, progress, commit = sys.argv[1:9]

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
    path = tmp.name
with gzip.open(db_gz, "rb") as src, open(path, "wb") as dst:
    dst.write(src.read())

con = sqlite3.connect(path)
try:
    def one(sql):
        row = con.execute(sql).fetchone()
        return row[0] if row else 0
    stats = {
        "total_songs": one("SELECT COUNT(*) FROM songs"),
        "songs_with_lyrics": one("SELECT COUNT(DISTINCT song_id) FROM lyrics"),
        "songs_with_synced": one("SELECT COUNT(DISTINCT song_id) FROM lyrics WHERE has_synced = 1"),
        "lyrics_candidates": one("SELECT COUNT(*) FROM lyrics"),
        "needs_review": one("SELECT COUNT(*) FROM lyrics WHERE needs_review = 1"),
    }
    sources = {
        row[0]: row[1]
        for row in con.execute("SELECT source, COUNT(*) FROM lyrics GROUP BY source ORDER BY 2 DESC")
    }
finally:
    con.close()
    os.unlink(path)

manifest = {
    "snapshot_utc": ts,
    "git_commit": commit,
    "job": {
        "running": running == "true",
        "pid": job or None,
        "current_artist": artist or None,
        "current_progress": progress or None,
    },
    "stats": stats,
    "sources": sources,
    "files": {
        "lyrics_db": "lyrics.db.gz",
        "review": "review/" if os.path.isdir(os.path.join(os.path.dirname(out), "review")) else None,
        "logs": "logs/",
        "meta": "meta/" if os.path.isdir(os.path.join(os.path.dirname(out), "meta")) else None,
    },
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2, ensure_ascii=True)
    fh.write("\n")
PY
  then
    log "ERROR: manifest generation failed"
    rm -rf "$tmp"
    return 1
  fi

  # Upload snapshot (immutable, timestamped).
  rc=0
  gcloud --quiet storage cp "$tmp/latest/lyrics.db.gz" "$BUCKET/snapshots/$ts/lyrics.db.gz" >>"$LOG" 2>&1 || rc=1
  if [ -d "$tmp/latest/review" ]; then
    gcloud --quiet storage cp -r "$tmp/latest/review" "$BUCKET/snapshots/$ts/" >>"$LOG" 2>&1 || rc=1
  fi
  if [ -d "$tmp/latest/meta" ]; then
    gcloud --quiet storage cp -r "$tmp/latest/meta" "$BUCKET/snapshots/$ts/" >>"$LOG" 2>&1 || rc=1
  fi
  for f in "$tmp/latest/logs/"*.gz; do
    [ -e "$f" ] || continue
    gcloud --quiet storage cp "$f" "$BUCKET/snapshots/$ts/logs/$(basename "$f")" >>"$LOG" 2>&1 || rc=1
  done
  gcloud --quiet storage cp "$tmp/latest/manifest.json" "$BUCKET/snapshots/$ts/manifest.json" >>"$LOG" 2>&1 || rc=1

  # Upload latest/ pointers for easy restore.
  gcloud --quiet storage cp "$tmp/latest/lyrics.db.gz" "$BUCKET/latest/lyrics.db.gz" >>"$LOG" 2>&1 || rc=1
  if [ -d "$tmp/latest/review" ]; then
    gcloud --quiet storage cp -r "$tmp/latest/review" "$BUCKET/latest/" >>"$LOG" 2>&1 || rc=1
  fi
  if [ -d "$tmp/latest/meta" ]; then
    gcloud --quiet storage cp -r "$tmp/latest/meta" "$BUCKET/latest/" >>"$LOG" 2>&1 || rc=1
  fi
  for f in "$tmp/latest/logs/"*.gz; do
    [ -e "$f" ] || continue
    gcloud --quiet storage cp "$f" "$BUCKET/latest/logs/$(basename "$f")" >>"$LOG" 2>&1 || rc=1
  done
  gcloud --quiet storage cp "$tmp/latest/manifest.json" "$BUCKET/latest/manifest.json" >>"$LOG" 2>&1 || rc=1

  rm -rf "$tmp"

  if [ "$rc" -ne 0 ]; then
    log "ERROR: one or more uploads failed for snapshot $ts"
    return 1
  fi
  log "OK snapshot=$ts job_running=$running artist=${artist:-none} progress=${progress:-none}"
  return 0
}

log "backup loop start pid=$$ interval=${INTERVAL}s bucket=$BUCKET"

if [ "${1:-}" = "--once" ]; then
  if ! acquire_lock; then
    log "another backup is already running; skipping"
    exit 0
  fi
  snapshot_once
  rc=$?
  release_lock
  exit $rc
fi

idle=0
while true; do
  if [ -n "$(job_pid)" ]; then
    idle=0
  else
    idle=$((idle + 1))
  fi

  if acquire_lock; then
    snapshot_once || true
    release_lock
  else
    log "another backup is already running; skipping this cycle"
  fi

  # After the job has been absent for two cycles, do one final snapshot and stop.
  if [ "$idle" -ge 2 ]; then
    log "job not running for $idle cycles; backup loop exiting"
    break
  fi

  sleep "$INTERVAL"
done
