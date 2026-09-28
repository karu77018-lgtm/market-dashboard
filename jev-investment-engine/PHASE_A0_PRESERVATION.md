# Phase A-0 private preservation

`Refresh source-mc57` scans tracked files and snapshot inputs for credential leaks, creates a
monthly-full or daily-delta snapshot containing vendor raw data, uploads it to a private Google Drive folder,
records the immutable metadata in Neon, and writes
`research-hashes/YYYY/MM/DD/<github.run_id>.json`.

The public Artifact excludes Massive raw files, `work/ohlcv.csv`, `data/mktcap.json`, Yahoo
history in `data/market_inputs.json`, and FRED history in `data/provider_inputs.json`.
`chart-data` remains public until its site dependencies and provenance are separated in the
next phase.

The public raw-free Artifact is independent of Drive and Neon. If private Drive/Neon
preservation is unavailable, the same private snapshot is encrypted with AES-256-CBC/PBKDF2 and
stored as a 90-day fallback Artifact. A successful encrypted fallback produces a warning but
does not fail the job. If both primary and interim preservation fail, the dashboard is
published first and the final step fails the job so normal GitHub notifications still fire.
Secret leakage, publication validation, or snapshot construction failure remains a hard stop.

## Snapshot size and reconstruction policy

The first observed US market session in each calendar month is a self-contained `full`
snapshot. Other sessions are `delta` snapshots. A delta contains the current session only from
`work/ohlcv.csv` and `work/massive-grouped.json`, plus the current private generated inputs.
Large public outputs (`source-mc57.html`, `chart-data`, and `latest-manifest.json`) remain in the
linked Git commit; their paths, sizes, and SHA-256 values are recorded as `external_files` in
the private manifest instead of duplicating their bytes every day.

To reconstruct a delta, restore the latest preceding monthly full snapshot and apply every
subsequent delta in session order. Then check each external file against the linked Git commit
using the hashes in `snapshot-manifest.json`. Do not delete a monthly full while any retained
delta depends on it. The pre-policy fallback for run `36405274864` is a full snapshot and is the
September 2026 baseline.

After downloading or decrypting the required tar files, rebuild the private input chain into a
new empty directory:

```bash
python scripts/phase_a0/restore_snapshot_chain.py \
  snapshot-FIRST-MONTHLY-FULL.tar.gz \
  snapshot-NEXT-DELTA.tar.gz \
  snapshot-LATEST-DELTA.tar.gz \
  --output restored-phase-a0
```

The helper rejects unsafe or unmanifested archive members, verifies every stored file against
its manifest, merges OHLCV by ticker/date and Massive data by session, and writes a reconstruction
report listing the external Git-backed files that still need hash verification.

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
- `ARCHIVE_PASSPHRASE` (required until Drive is configured and retained for recovery)

Generate the interim passphrase locally and store it in both GitHub Actions Secrets and a
password manager. Losing it makes every interim snapshot unrecoverable:

```bash
openssl rand -base64 32
```

The secret gate compares all supplied secret values against every scanned file, including
URL-encoded forms. It also detects URL query keys, PostgreSQL credential URLs, and bearer
tokens without printing the detected value.

## Point-in-time evidence

The record links `github_run_id`, Actions `run_started_at`, source `code_sha`, `recorded_at`,
Drive `createdTime`, `drive_file_id`, `snapshot_mode`, and both SHA-256 values. Git commit time is not the
point-in-time authority; the later push is the durable public record containing that JSON.
`recorded_at` is the actual snapshot construction time and Neon `inserted_at` is the database
availability time to use for point-in-time research. Both `recorded_at` and `run_attempt` stay
outside the hashed snapshot manifest, so rerunning the same run with identical inputs still
produces the same immutable hashes.

Use `available_at` as follows and never substitute `recorded_at` or Git commit time:

- `google_drive_live`: Neon `inserted_at`
- `interim_artifact_recovery`: GitHub Artifact `created_at`, stored as `artifact_created_at`

## Recover an interim Artifact

Download the encrypted snapshot and its `.interim.json` metadata from the Actions Artifact.
Set `GH_TOKEN` for a private repository or to avoid anonymous API rate limits. For this public
repository the lookup can run without a token. Then run:

```bash
python scripts/phase_a0/recover_interim_snapshot.py \
  snapshot-YYYY-MM-DD-RUNID-HASH.tar.gz.enc \
  snapshot-YYYY-MM-DD-RUNID-HASH.tar.gz.interim.json
```

The recovery tool obtains `created_at` from the GitHub Actions API using the immutable run ID
and attempt in the metadata; it does not accept a manually entered PIT timestamp. It then
verifies the encrypted and decrypted SHA-256 values, creates a new Drive file, records
`source = interim_artifact_recovery` and the GitHub Artifact creation time in
Neon, and writes the original run-id hash JSON. Commit that JSON before the Artifact expires.
