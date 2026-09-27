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
