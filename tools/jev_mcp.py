#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

SERVER_NAME = "jev"
SERVER_VERSION = "1.0.0"
DEFAULT_ENDPOINT = "https://ai-gateway.vercel.sh/typesafe/v1/systemone"
ALLOWED_TYPES = {"noul", "choice", "score"}


def _write(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _error(request_id: Any, code: int, message: str, data: Any | None = None) -> None:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    _write({"jsonrpc": "2.0", "id": request_id, "error": err})


def _result(request_id: Any, result: Any) -> None:
    _write({"jsonrpc": "2.0", "id": request_id, "result": result})


def _normalize_questions(questions: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(questions, dict) or not questions:
        raise ValueError("questions must be a non-empty object")
    clean: dict[str, dict[str, Any]] = {}
    for name, question in questions.items():
        if not isinstance(name, str) or not name:
            raise ValueError("question names must be non-empty strings")
        if not isinstance(question, dict):
            raise ValueError(f"question {name!r} must be an object")
        q = dict(question)
        qtype = q.get("type")
        if qtype == "boolean":
            qtype = "noul"
            q["type"] = "noul"
        if qtype not in ALLOWED_TYPES:
            raise ValueError(f"question {name!r} type must be noul, choice, or score")
        instructions = q.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            raise ValueError(f"question {name!r} needs non-empty instructions")
        if qtype == "choice":
            criteria = q.get("criteria")
            if not isinstance(criteria, dict) or len(criteria) < 2:
                raise ValueError(f"choice question {name!r} needs at least two criteria")
        clean[name] = q
    return clean


def _call_jev(state: Any, questions: Any) -> dict[str, Any]:
    api_key = (
        os.environ.get("JEV_API_KEY")
        or os.environ.get("AI_GATEWAY_API_KEY")
        or ""
    ).strip()
    if not api_key:
        raise RuntimeError(
            "Set JEV_API_KEY or AI_GATEWAY_API_KEY in the Codex environment"
        )

    endpoint = (os.environ.get("JEV_ENDPOINT") or DEFAULT_ENDPOINT).strip()
    payload = {
        "state": state,
        "questions": _normalize_questions(questions),
    }
    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "codex-jev-mcp/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise RuntimeError("Jev returned a non-object response")
            return data
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:3000]
        raise RuntimeError(f"Jev HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Jev request failed: {exc.reason}") from exc


TOOL = {
    "name": "jev_evaluate",
    "description": (
        "Evaluate structured state with TypeSafe AI Jev. Use for bounded "
        "probabilistic decisions, classification, scoring, selection, or "
        "verification. Returns Jev typed answers and probabilities."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "state": {
                "description": (
                    "Shared state/context Jev should evaluate. "
                    "May be a string, object, or array."
                ),
            },
            "questions": {
                "type": "object",
                "description": (
                    "Named Jev questions. Each question uses type noul, choice, "
                    "or score; boolean is accepted as an alias for noul."
                ),
                "additionalProperties": {"type": "object"},
            },
        },
        "required": ["state", "questions"],
        "additionalProperties": False,
    },
    "annotations": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": True,
    },
}


def _handle(message: dict[str, Any]) -> None:
    method = message.get("method")
    request_id = message.get("id")

    if method == "initialize":
        requested_protocol = (
            (message.get("params") or {}).get("protocolVersion")
            or "2025-06-18"
        )
        _result(
            request_id,
            {
                "protocolVersion": requested_protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
                "instructions": (
                    "Use jev_evaluate only for bounded decisions over supplied "
                    "state. Do not treat Jev probabilities as deterministic facts."
                ),
            },
        )
        return

    if method == "notifications/initialized":
        return

    if method == "ping":
        _result(request_id, {})
        return

    if method == "tools/list":
        _result(request_id, {"tools": [TOOL]})
        return

    if method == "tools/call":
        params = message.get("params") or {}
        if params.get("name") != TOOL["name"]:
            _error(request_id, -32602, "Unknown tool")
            return

        args = params.get("arguments") or {}
        try:
            data = _call_jev(args.get("state"), args.get("questions"))
            _result(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(data, ensure_ascii=False),
                        }
                    ],
                    "structuredContent": data,
                    "isError": False,
                },
            )
        except Exception as exc:
            _result(
                request_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )
        return

    if request_id is not None:
        _error(request_id, -32601, f"Method not found: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        message: Any = None
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("message must be an object")
            _handle(message)
        except json.JSONDecodeError as exc:
            _error(None, -32700, "Parse error", str(exc))
        except Exception as exc:
            request_id = message.get("id") if isinstance(message, dict) else None
            _error(request_id, -32603, "Internal error", str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
