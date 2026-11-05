"""Apply review decisions from review/candidates.csv back into SQLite."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from .db import connect

VALID = {"keep", "reject", "edit", "merge"}


def choose_preferred(conn, song_id: int) -> None:
    conn.execute("UPDATE lyrics SET is_preferred = 0 WHERE song_id = ?", (song_id,))
    conn.execute(
        """
        UPDATE lyrics
        SET is_preferred = 1
        WHERE id = (
            SELECT id FROM lyrics
            WHERE song_id = ?
              AND (review_decision IS NULL OR review_decision != 'reject')
              AND (
                    manual_verified = 1
                    OR (
                        quality_score >= 0.45
                        AND COALESCE(quality_flags, '') NOT LIKE '%"no_arabic"%'
                    )
                  )
            ORDER BY
              manual_verified DESC,
              CASE WHEN kind IN ('synced', 'word_synced') AND quality_score >= 0.55 THEN 1 ELSE 0 END DESC,
              quality_score DESC
            LIMIT 1
        )
        """,
        (song_id,),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply review decisions from CSV")
    parser.add_argument("--csv", default="review/candidates.csv")
    parser.add_argument("--db", default="data/lyrics.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"CSV not found: {path}")

    conn = connect(args.db)
    counts = Counter()
    songs = set()

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            decision = (row.get("decision") or "").strip().lower()
            if not decision:
                continue
            if decision not in VALID:
                print(f"skip candidate {row.get('candidate_id')}: invalid decision {decision!r}")
                continue
            candidate_id = row.get("candidate_id")
            if not candidate_id:
                continue
            notes = (row.get("notes") or "").strip()
            song_id = conn.execute(
                "SELECT song_id FROM lyrics WHERE id = ?", (candidate_id,)
            ).fetchone()
            if not song_id:
                print(f"skip candidate {candidate_id}: not found")
                continue
            song_id = int(song_id["song_id"])
            songs.add(song_id)
            counts[decision] += 1

            if args.dry_run:
                continue

            if decision == "keep":
                conn.execute(
                    """
                    UPDATE lyrics
                    SET review_decision = 'keep', review_notes = ?, reviewed_at = datetime('now'),
                        manual_verified = 1, needs_review = 0
                    WHERE id = ?
                    """,
                    (notes, candidate_id),
                )
            elif decision == "reject":
                conn.execute(
                    """
                    UPDATE lyrics
                    SET review_decision = 'reject', review_notes = ?, reviewed_at = datetime('now'),
                        manual_verified = 0, needs_review = 0, is_preferred = 0
                    WHERE id = ?
                    """,
                    (notes, candidate_id),
                )
            else:  # edit / merge
                conn.execute(
                    """
                    UPDATE lyrics
                    SET review_decision = ?, review_notes = ?, reviewed_at = datetime('now'),
                        needs_review = 1
                    WHERE id = ?
                    """,
                    (decision, notes, candidate_id),
                )

    if not args.dry_run:
        for song_id in songs:
            choose_preferred(conn, song_id)
        conn.commit()
    conn.close()

    print("decisions:", dict(counts))
    print("songs updated:", len(songs))
    if args.dry_run:
        print("dry run: database not modified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
