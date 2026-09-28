# Research Snapshot Phase A-0

Purpose: preserve each market session before later research, AI evaluation, or
rule changes can rewrite history.

## Storage model

- GitHub Free: code, public-safe outputs, append-only SHA-256 records
- Google Drive: private long-term snapshot archive
- Neon: manifest/provenance only

No B2 or GitHub Pro is required for Phase A-0.

## Rollout behavior

Until Google Drive OAuth is configured, the workflow keeps a 30-day raw
fallback Artifact so there is no storage gap. Once a Drive upload succeeds,
that raw fallback is skipped automatically. Public-safe artifacts are retained
for 90 days.

The raw fallback contains provider-derived data and is temporary. It should not
be treated as the long-term design.

## GitHub Secrets

Do not put secret values in source files.

Required for Google Drive:
- GOOGLE_OAUTH_CLIENT_ID
- GOOGLE_OAUTH_CLIENT_SECRET
- GOOGLE_OAUTH_REFRESH_TOKEN

Optional:
- GOOGLE_DRIVE_FOLDER_ID

The OAuth grant should use only the Google Drive `drive.file` scope. Keep the
OAuth app in Production rather than Test so the refresh token is not subject to
the short testing lifetime.

Required for Neon manifest recording:
- SNAPSHOT_DATABASE_URL

Use a dedicated `snapshot_writer` Postgres role. Do not reuse the database
owner connection string.

## Snapshot contents

The daily content-addressed archive currently includes:
- source-mc57.html
- latest-manifest.json
- data/*.json
- work/ohlcv.csv
- work/massive-reference.json
- work/massive-grouped.json
- chart-data files changed by the current run

The archive embeds `snapshot-manifest.json` with the SHA-256 and byte size of
every included file. Gzip/tar metadata is normalized so identical source bytes
from the same code revision reproduce the same archive hash.

## Secret gate

Before creating an archive, the workflow scans the selected payload for:
- exact configured provider/database/OAuth secret values
- API-key query parameters
- Bearer credentials
- PostgreSQL URLs

If any match is found, archive creation fails. Values are not auto-redacted.

## Public hash record

Every run writes a new file:

`research-hashes/YYYY/MM/DD/<github_run_id>-a<github_run_attempt>.json`

No daily hash file is overwritten. The GitHub run id and run attempt can be matched against
GitHub's own Actions metadata for third-party timing evidence and safe workflow reruns.

## Neon

Migration order:
1. Apply `research-archive/migrations/20260928_snapshot_manifests.sql` (schema + append-only guards).
2. Create the login role `snapshot_writer`.
3. Apply `research-archive/migrations/20260928_snapshot_writer_grants.sql`.

`20260928_snapshot_manifests_protection.sql` is compatibility-only and is not required after step 1.
The manifest and storage-copy tables are append-only by trigger. Drive file IDs and copy statuses
are recorded as separate copy events so later retries never rewrite the original manifest.
Payload data itself is not stored in Neon.

## Next items after Phase A-0 is live

- raw unadjusted daily prices
- splits
- dividends
- point-in-time security/ticker reference mapping
- Quality Gate + canonical_decisions
- weekly Drive/Neon/GitHub restore and hash verification
- monthly full chart-data archive
