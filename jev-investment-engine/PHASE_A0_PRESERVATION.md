# Phase A-0 private preservation

`Refresh source-mc57` scans tracked files and snapshot inputs for credential leaks, creates a
complete snapshot containing vendor raw data, uploads it to a private Google Drive folder,
records the immutable metadata in Neon, and writes
`research-hashes/YYYY/MM/DD/<github.run_id>.json`.

The 90-day public Artifact is created only after Drive, Neon, and the hash record succeed. It
excludes Massive raw files, `work/ohlcv.csv`, and `data/mktcap.json`. `chart-data` remains
public until its site dependencies and provenance are separated in the next phase.

Drive or Neon failure produces an Actions warning and suppresses the public preservation
Artifact and hash record, but it does not stop the dashboard publication. Secret leakage,
publication validation, or snapshot construction failure remains a hard stop.

## 1. Create the Drive folder with the OAuth app

Use a desktop OAuth client in production status and obtain a refresh token with `drive.file`.
The destination folder must be created by the same OAuth app; a manually created folder is not
visible through `drive.file`.

Run once outside GitHub Actions with these environment variables set:

```bash
python scripts/phase_a0/create_google_drive_folder.py
```

The helper reuses the single app-visible folder when it already exists and returns its folder
ID. It refuses a folder with an `anyone` permission. Store the returned ID as
`GOOGLE_DRIVE_FOLDER_ID`.

## 2. Apply the Neon migration once

Run `migrations/20260928_phase_a0_snapshot_manifests.sql` once with a direct administrator
connection. GitHub Actions never executes DDL. The migration creates the append-only table,
immutable trigger, and least-privilege `snapshot_writer` role.

Set a strong password separately without committing it:

```sql
ALTER ROLE snapshot_writer PASSWORD '<strong-random-password>';
```

The role receives only schema usage, table `SELECT`/`INSERT`, and sequence `USAGE`. Store only
the `snapshot_writer` connection string as `NEON_DATABASE_URL`. The runtime verifies the exact
role name, required grants, denied write operations, table ownership, role membership, and
elevated role flags before every lookup or insert.

## 3. GitHub Actions secrets

- `GOOGLE_DRIVE_CLIENT_ID`
- `GOOGLE_DRIVE_CLIENT_SECRET`
- `GOOGLE_DRIVE_REFRESH_TOKEN`
- `GOOGLE_DRIVE_FOLDER_ID`
- `NEON_DATABASE_URL` (the `snapshot_writer` connection only)

The secret gate compares all supplied secret values against every scanned file, including
URL-encoded forms. It also detects URL query keys, PostgreSQL credential URLs, and bearer
tokens without printing the detected value.

## Point-in-time evidence

The record links `github_run_id`, Actions `run_started_at`, source `code_sha`, `recorded_at`,
`drive_file_id`, and both SHA-256 values. Git commit time is not the point-in-time authority;
the later push is the durable public record containing that JSON. Snapshot `recorded_at` is
anchored to the run start and `run_attempt` is kept outside the hashed manifest, so rerunning
the same run with identical inputs produces the same immutable hashes.
