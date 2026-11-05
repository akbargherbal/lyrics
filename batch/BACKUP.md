# GCS Backup

Progress is backed up to:

```text
gs://akbar-december-2024-backup/lyrics/
```

Layout:

```text
lyrics/
  latest/
    lyrics.db.gz          # consistent SQLite snapshot (includes WAL)
    manifest.json         # stats, current artist/progress, git commit
    review/               # candidates.csv, review_queue.csv, songs.csv, artists.csv, summary.md
    logs/                 # run.log.gz, nohup.out.gz, backup.log.gz
    meta/                 # PLAN.md, PROGRESS.md, artists.yaml, schema.sql, batch code/config
  snapshots/
    YYYYMMDDTHHMMSSZ/
      lyrics.db.gz
      manifest.json
      review/
      logs/
      meta/
```

The loop (`batch/backup_gcs.sh`) runs every 15 minutes and uses SQLite's
online backup API, so it is safe while `batch.job` is writing. It stops
automatically after the batch job has been absent for two cycles.

## Restore

Stop the batch job first, then:

```bash
rm -f data/lyrics.db data/lyrics.db-wal data/lyrics.db-shm
gcloud storage cp gs://akbar-december-2024-backup/lyrics/latest/lyrics.db.gz /tmp/lyrics.db.gz
gunzip -c /tmp/lyrics.db.gz > data/lyrics.db

rm -rf review
gcloud storage cp -r gs://akbar-december-2024-backup/lyrics/latest/review ./review
```

To restore a specific timestamp, replace `latest` with
`snapshots/YYYYMMDDTHHMMSSZ`.

The `meta/` folder contains a copy of `PLAN.md`, `artists.yaml`, `schema.sql`,
and the batch pipeline code/config, so recovery does not depend on the VM
surviving. Restore it with:

```bash
gcloud storage cp -r gs://akbar-december-2024-backup/lyrics/latest/meta ./meta-restored
```

## Notes

- The HTTP cache (`batch/cache/`) is not backed up; it is regenerable.
- The SQLite snapshot is the authoritative progress record and preserves
  job state, so completed artists are skipped after a restart.
