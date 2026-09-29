# Historical Massive news acquisition

This additive research tool does not change the daily dashboard, production Jev API,
trading rules, or portfolio data. Code is based on `jev-prod`; any production adoption
requires a reviewed PR into that branch. No Jev inference or paid news add-on is used.

## Problem / cause / change / impact

Daily news ingestion reads a short lookback and bounded per-ticker article count.
Historical forecast development needs the full provider archive for its period.
This tool pages all-market news (no ticker filter) in UTC monthly half-open windows,
including 30 warmup days, stores article versions, and checkpoints pagination in SQLite.
It has no dependency on current winners or private holdings. All-market retrieval does
not guarantee the provider covered every issuer or event.

The current data manifest defines a 2026-09-28 price-session end. Acquisition starts
2026-02-26 and ends strictly before 2026-09-29T04:05:21Z, the manifest generation cutoff.
The retrospective evaluation period is 2026-03-28 through 2026-09-28.

## Privacy and storage

Only aggregate counts, dates, status, and encrypted archive hashes are public.
Raw JSON, article titles, URLs, tickers, and credentials are not logged or uploaded in
plaintext. Private raw data exists only in the runner's ephemeral working directory.
The `.aesgcm` artifact is an authenticated AES-256-GCM encrypted gzip SQLite file.
PBKDF2-HMAC-SHA256, 600,000 iterations, random 16-byte salt and 12-byte nonce; the header
is authenticated. The existing `ARCHIVE_PASSPHRASE` never leaves the execution environment.
Keep the password in its existing secure location; the artifact cannot be recovered
without it. New format is independent of the existing Phase A-0 CBC archive format.
An encrypted artifact is retained for 90 days. If existing private Drive credentials
are configured, an additional encrypted copy is uploaded there without creating folders.
No user holdings or private holdings evaluation is processed by this workflow.

## Execute / resume

- `python -m pytest research/news_backfill/test_archive.py -q`
- `python research/news_backfill/archive.py acquire`
- Restore with `python research/news_backfill/archive.py restore --archive INPUT.aesgcm`.
- For Actions continuation, set `resume_artifact_id` in config to the preceding encrypted
  artifact ID and push this dedicated research branch. The dataset time range must match.
- `max_requests` and `max_seconds` are ceilings, not completeness promises. Pagination
  exhaustion defines completion. Limits/errors retain already committed pages encrypted.
- No raw Actions cache or git commit is made. The workflow has read-only repo permission.

## Evidence restrictions

A provider's published timestamp is not proof that today's article version or vendor
sentiment existed at that timestamp. Each version retains `published`, `retrieved`, its
content hash, and the vendor payload. Historical version availability is UNKNOWN.
Retrospective slices are explicitly marked; strict slices exclude material retrieved
later than the forecast cutoff. Vendor-generated sentiment/insights are never included
in forecast document slices. No historical accuracy claim is made by this acquisition.
News without descriptions remains recorded as such, not inferred to be negative/no event.
Primary IR/SEC corroboration remains a separate evidence task, not silently simulated.

Rollback: do not run this workflow. No production files need reverting and no dataset
or previous archive is deleted.
