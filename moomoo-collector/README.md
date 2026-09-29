# moomoo intraday collector

Isolated observation layer for market data. It does not modify V38/MC57/Jev trading rules and contains no live-order path.

## Security
- OAuth 2.1 + PKCE only.
- Initial requested scope: quote:read only.
- Tokens live outside Git in /var/lib/moomoo-collector with owner-only permissions.
- No trade:write scope is requested.
- Never commit tokens, client registration access tokens, or authorization codes.

## Runtime
The collector connects to wss://webapi-quote.moomoo.com/ws, authenticates with a Bearer access token, subscribes to configured symbols, writes newline-delimited JSON, refreshes OAuth tokens, and reconnects/resubscribes after disconnects.

Start small. Default symbols are QQQ, TQQQ, SOXX, SOXL, NVDA and PLTR with basic quote + 1m K-line only. Order book and ticker are intentionally disabled until quote permissions and storage/network use are measured.

Official protocol references:
- https://open.moomoo.com/api/overview/getting-started
- https://open.moomoo.com/api/quote/push/auth
- https://open.moomoo.com/api/quote/push/subscribe
