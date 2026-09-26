# Jev Vercel proxy

This branch adds an isolated Vercel Python Function at `/api/jev`.
It does not modify source-mc57 generation, MC57 logic, chart data, or the GitHub Pages output.

## Upstream

The proxy calls Vercel AI Gateway:

- endpoint: `https://ai-gateway.vercel.sh/v1/evaluate`
- model: `typesafe-ai/jev`
- accepted question types: `boolean`, `choice`, `score`

The model is fixed server-side so callers cannot turn this endpoint into a proxy for other AI Gateway models.

## Authentication

Two layers are used.

1. Upstream Jev authentication
   - `AI_GATEWAY_API_KEY` if configured
   - otherwise `VERCEL_OIDC_TOKEN` supplied by Vercel deployments

2. Proxy authentication
   - set `JEV_PROXY_TOKEN` in Vercel
   - callers must send the same value as `X-Jev-Proxy-Token`
   - `Authorization: Bearer <token>` is also accepted

If `JEV_PROXY_TOKEN` is not configured, POST fails closed with HTTP 503.
The unauthenticated GET endpoint only reports configuration booleans and never returns secrets.

## Example

```bash
curl https://YOUR-DEPLOYMENT.vercel.app/api/jev \
  -H 'Content-Type: application/json' \
  -H 'X-Jev-Proxy-Token: YOUR_PROXY_TOKEN' \
  -d '{
    "state": {
      "ticker": "NVDA",
      "rs63": 94,
      "rs189": 97
    },
    "questions": {
      "regime": {
        "type": "choice",
        "instructions": "Classify the next 5 trading days.",
        "criteria": {
          "weak": "Likely weak or below-normal outcome",
          "normal": "Likely ordinary outcome",
          "strong": "Likely strong positive outcome"
        }
      }
    }
  }'
```

## Safety limits

- request body: 64 KiB maximum
- questions: 32 maximum
- choice criteria: 32 maximum
- upstream timeout: 25 seconds
- no caching
- no secret values returned by the health endpoint
