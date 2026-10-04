# Jev Investment Engine

Independent Jev decision layer for `market-dashboard`.

## Phase 1

- Vercel project: `jev-investment-engine`
- Runtime: Vercel Functions
- Jev path: Vercel AI Gateway -> `typesafe-ai/jev`
- Endpoint: `POST /api/jev`
- Default important-evaluation policy: 3 runs
- Shadow only. No BUY/SELL authority.

## Required Vercel environment variable

`AI_GATEWAY_API_KEY`

Optional:

`JEV_API_SECRET`

If `JEV_API_SECRET` is configured, callers must send:

`Authorization: Bearer <JEV_API_SECRET>`

## Example request

```json
{
  "state": "Management raised full-year revenue guidance and announced a new enterprise contract.",
  "runs": 3,
  "questions": {
    "guidanceRaise": {
      "type": "boolean",
      "instructions": "Did management raise forward guidance?"
    }
  }
}
```

## Rules

- Numeric calculations stay in Python/Quant.
- Jev outputs are research features, not trade orders.
- Model/question versions must be persisted before production backfill.
- Point-in-time and tradable-at timestamps are mandatory for historical research.

## Automatic live shadow run

The weekday/manual `Refresh source-mc57` workflow invokes
`scripts/run_jev_live_shadow.py` after the dashboard publication gates pass.
It evaluates up to 70 dashboard names (default `--max-candidates 70`): the swing
candidates (本命・まだ入れる・次の候補) first, then names just below an option
call wall (壁近接, up to 20), then ピックアップ・新高値圏 and RS21/63/189 leaders,
using at most eight Massive news items published during the preceding 30 days
and no later than `latest-manifest.json.generated_at`.

- Each eligible ticker runs the frozen `jev-text-v1` question set three times.
- Results and the supplied state are stored in Neon by the Jev API.
- Runs are `evaluationKind=live`, `validationEligible=false`, and shadow-only.
- Tickers without point-in-time news are skipped instead of asking Jev to guess.
- Push-triggered rebuilds do not invoke Jev; scheduled and manual runs do.
- A Jev failure cannot block the dashboard or Phase A-0 preservation.
- A duplicate (already saved) evaluation counts as success only when its scores
  can be restored (from the API's stored aggregate or the last public ranking);
  a partial run never replaces a ranking of the same session.
- The 90-day GitHub audit Artifact contains only ticker, counts, evaluation IDs,
  cost, and the state SHA-256. Vendor news text is never written to GitHub.

GitHub Actions needs a `JEV_API_SECRET` repository Secret whose value exactly
matches the `JEV_API_SECRET` configured for the Vercel project. The secret is
required: without it the API refuses every request (503), it is never optional. The optional
`JEV_API_URL` repository Variable may override the production endpoint.
