# Phase A-0 private preservation

`Refresh source-mc57` scans tracked files and snapshot inputs for credential leaks, creates a
monthly-full or daily-delta snapshot containing vendor raw data, uploads it to a private Google Drive folder,
and writes the authoritative immutable metadata to
`research-hashes/YYYY/MM/DD/<github.run_id>.json`.
Neon is an optional, rebuildable query index and never gates Drive preservation.

The public Artifact excludes Massive raw files, `work/ohlcv.csv`, `data/mktcap.json`, Yahoo
history in `data/market_inputs.json`, and FRED history in `data/provider_inputs.json`.
`chart-data` remains public until its site dependencies and provenance are separated in the
next phase.

The public raw-free Artifact is independent of Drive and Neon. If private Drive
preservation is unavailable, the same private snapshot is encrypted with AES-256-CBC/PBKDF2 and
stored as a 90-day fallback Artifact. A successful encrypted fallback produces a warning but
does not fail the job. If both primary and interim preservation fail, the dashboard is
published first and the final step fails the job so normal GitHub notifications still fire.
Secret leakage, publication validation, or snapshot construction failure remains a hard stop.

## Snapshot size and reconstruction policy

The first **successfully preserved** snapshot in each calendar month is a self-contained `full`
snapshot. A full is considered successful only after either Drive/hash recording or the
encrypted fallback Artifact succeeds. The workflow then commits an immutable marker at
`research-snapshot-index/YYYY/MM/full.json`. Until that marker exists, every later run in the
month tries a full snapshot again; a failed first trading-day run therefore cannot leave the
month without a baseline.

Other runs are `delta` snapshots. A delta contains the current session only from
`work/ohlcv.csv` and `work/massive-grouped.json`, plus the current private generated inputs,
`source-mc57.html`, and `latest-manifest.json`. Only `chart-data` remains in the linked Git
commit; its paths, sizes, and SHA-256 values are recorded as `external_files` in the private
manifest instead of duplicating its bytes every day.

Before reducing the two rolling raw files, the manifest records each original file's SHA-256,
byte size, row count, and (for Massive grouped data) session count under
`source_before_delta`. This proves which complete rolling input was used, but does not make that
input reconstructable from the delta alone. Yahoo's automatically adjusted history and
Massive's `adjusted=true` history can rewrite old daily bars after splits or dividends. A chain
of deltas therefore reconstructs the values observed for each saved session, not the complete
rolling history exactly as it appeared on every individual run. This is sufficient for future
label calculations that use the retained session values; use a full snapshot when the complete
historical input as-of a particular run is required.

To reconstruct a delta, restore the latest preceding monthly full snapshot and apply every
subsequent delta in `(session_date, github_run_id)` order. Multiple runs from the same session
are valid; the later run ID replaces that session's earlier ticker/date and grouped values.
Then check each external file against the linked Git commit
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
ID. It refuses a folder with an `anyone` permission. Store the returned ID as the GitHub Actions
**Variable** `GOOGLE_DRIVE_FOLDER_ID`; it is an opaque locator, not a credential. A legacy Secret
with the same name is accepted temporarily for migration.

## 2. Optional Neon index

Neon is not required for preservation. Drive stores the private bytes and server-issued
`createdTime`; GitHub stores the hashes and Drive file ID. The Neon table can therefore be
recreated later by importing `research-hashes`.

If the query index is wanted, run `migrations/20260928_phase_a0_snapshot_manifests.sql` once with a direct administrator
connection. GitHub Actions never executes DDL. The migration creates the append-only table,
immutable trigger, and least-privilege `snapshot_writer` role.

Set a strong password separately without committing it:

```sql
ALTER ROLE snapshot_writer PASSWORD '<strong-random-password>';
```

The role receives only schema usage, table `SELECT`/`INSERT`, and sequence `USAGE`. Optionally
store the `snapshot_writer` connection string as `NEON_DATABASE_URL`. The runtime verifies the exact
role name, required grants, denied write operations, table ownership, role membership, and
elevated role flags before each insert. Missing or failed Neon indexing produces a warning only;
it does not trigger the encrypted fallback and does not change a successful Drive result.

## 3. GitHub Actions configuration

Required Secrets for live Drive preservation:

- `GOOGLE_DRIVE_CLIENT_ID`
- `GOOGLE_DRIVE_CLIENT_SECRET`
- `GOOGLE_DRIVE_REFRESH_TOKEN`

Required Variable:

- `GOOGLE_DRIVE_FOLDER_ID`

Optional Secret:

- `NEON_DATABASE_URL` (the `snapshot_writer` connection only)

Fallback/recovery Secret:

- `ARCHIVE_PASSPHRASE` (required until Drive is configured and retained while old encrypted Artifacts exist)

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
`recorded_at` is the actual snapshot construction time. For a live copy, Google Drive
`createdTime` is the availability time to use for point-in-time research. Both `recorded_at` and `run_attempt` stay
outside the hashed snapshot manifest, so rerunning the same run with identical inputs still
produces the same immutable hashes.

Use `available_at` as follows and never substitute `recorded_at` or Git commit time:

- `google_drive_live`: Drive `createdTime`
- `interim_artifact_recovery`: GitHub Artifact `created_at`, stored as `artifact_created_at`

The selected value is also copied to `available_at` in each GitHub hash record.

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
verifies the encrypted and decrypted SHA-256 values, creates a new Drive file, and writes the
original run-id hash JSON with `source = interim_artifact_recovery` and the GitHub Artifact
creation time. If `NEON_DATABASE_URL` is configured it also attempts the optional Neon insert;
that insert cannot invalidate the Drive copy or hash record. Commit the JSON before the Artifact expires.
