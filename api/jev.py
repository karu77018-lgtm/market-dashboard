from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from api._jev_core import (
    GATEWAY_URL,
    MAX_BODY_BYTES,
    RequestValidationError,
    normalize_payload,
    proxy_token,
    token_matches,
    upstream_token,
)


class handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        gateway_auth = bool(upstream_token())
        proxy_auth = bool(proxy_token())
        self._json(
            200,
            {
                "status": "ready" if gateway_auth and proxy_auth else "needs_configuration",
                "service": "jev-proxy",
                "model": "typesafe-ai/jev",
                "gateway_auth_configured": gateway_auth,
                "proxy_auth_configured": proxy_auth,
            },
        )

    def do_POST(self) -> None:
        expected = proxy_token()
        if not expected:
            self._json(503, {"error": "proxy_not_configured"})
            return

        received = self.headers.get("X-Jev-Proxy-Token")
        if not received:
            auth = self.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                received = auth[7:].strip()
        if not token_matches(received):
            self._json(401, {"error": "unauthorized"})
            return

        gateway_token = upstream_token()
        if not gateway_token:
            self._json(503, {"error": "gateway_auth_not_configured"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "invalid_content_length"})
            return
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._json(413, {"error": "request_too_large_or_empty"})
            return

        try:
            raw = self.rfile.read(content_length)
            incoming = json.loads(raw.decode("utf-8"))
            payload = normalize_payload(incoming)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "invalid_json"})
            return
        except RequestValidationError as exc:
            self._json(400, {"error": "invalid_request", "detail": str(exc)})
            return

        upstream_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(
            GATEWAY_URL,
            data=upstream_body,
            method="POST",
            headers={
                "Authorization": f"Bearer {gateway_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "market-dashboard-jev-proxy/1.0",
                "ai-reporting-tags": "app:market-dashboard,feature:jev-proxy",
            },
        )

        try:
            with urlopen(request, timeout=25) as response:
                body = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:4000]
            self._json(
                exc.code if 400 <= exc.code <= 599 else 502,
                {"error": "gateway_error", "status": exc.code, "detail": detail},
            )
        except (URLError, TimeoutError) as exc:
            self._json(502, {"error": "gateway_unreachable", "detail": str(exc)[:500]})
