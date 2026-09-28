# Jev Phase 1 implementation test checklist

## Build / identity
- Preview deployment reaches READY.
- /api/health returns commitSha and commitRef.
- Production health is checked again after promotion.

## Authentication
- Missing JEV_API_SECRET configuration => 503.
- Missing/wrong bearer when secret exists => 401.
- Authentication failures create no jev_attempt row.

## Persisted input validation
- persist=true + questions present => 400.
- ticker missing => 400.
- asofTimestamp missing => 400.
- timezone-naive asofTimestamp => 400.
- future asofTimestamp => 400.
- evaluationKind missing/invalid => 400.
- persisted runs != 3 => 400.
- jev-text-v1 active question count != 15 => reject.

## Dedupe
- Same identity + same kind returns existing evaluation before Jev call.
- Duplicate response reports zero new Gateway cost.
- Same identity + different kind => 409.
- Concurrent duplicate race resolves as duplicate, not 500.

## Attempts
- started row is committed before Jev is called.
- If started insert fails, API returns 503 and does not call Jev.
- 3/3 success finalizes status=success.
- Partial run failure finalizes status=partial and records successful-run cost/tokens.
- Gateway timeout finalizes timeout when the function remains alive long enough.
- A hard Vercel termination leaves status=started for later diagnosis.
- Completed attempt cannot be edited again.

## Persistence integrity
- Successful full evaluation has exactly 3 jev_runs.
- Successful jev-text-v1 evaluation has exactly 15 features / 15 distinct question IDs.
- validation_eligible=true is rejected unless sourced backfill/live success.
- ids 1-5 remain smoke,false.
- id 6 remains manual_shadow,false.

## Shortcut summary mode
With responseMode="summary", Content-Type is plain text and includes:
- status
- ticker
- as-of
- questions
- runs
- evaluation id
- attempt id
- duration
- cost

## Question-set freeze
- Insert into non-draft set rejected.
- Update/delete question in non-draft set rejected.
- question set status cannot move backward.
- activated_at can be set once only.
- completed attempts are immutable.
- protected tables reject TRUNCATE after Stage 2.

## Deployment separation
Before production switch:
- Vercel Production Branch = jev-prod.
- project-level Ignored Build Step skips all non-jev-prod branches.
- jev-prod branch protection prevents direct unreviewed pushes.
- old public previews are protected or removed later.
