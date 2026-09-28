# Phase A-0 private preservation

`Refresh source-mc57` scans for secrets, creates a complete snapshot with Massive raw data,
uploads it as a new private Google Drive file, appends its `drive_file_id` and SHA-256 values
to Neon, and writes `research-hashes/YYYY/MM/DD/<github.run_id>.json`. Only after those steps
succeed does it create the 90-day public Artifact, which excludes `work/massive-reference.json`
and `work/massive-grouped.json`. `chart-data` remains public until its dependencies and
provenance are separated in the next phase.

Required GitHub Actions secrets are `GOOGLE_DRIVE_CLIENT_ID`,
`GOOGLE_DRIVE_CLIENT_SECRET`, `GOOGLE_DRIVE_REFRESH_TOKEN`, `GOOGLE_DRIVE_FOLDER_ID`, and
`NEON_DATABASE_URL`. The Drive folder must not have an `anyone` permission. The uploader only
uses Drive `files.create`; it has no update path. `NEON_DATABASE_URL` should be a direct,
non-pooler connection because the workflow applies the additive migration before inserting.

The point-in-time record links `github_run_id`, Actions `run_started_at`, source `code_sha`,
`recorded_at`, `drive_file_id`, and both SHA-256 values. Git commit time is not used as the
point-in-time authority; the later push is the durable public record containing that JSON.
