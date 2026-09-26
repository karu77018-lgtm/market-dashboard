from __future__ import annotations

import hmac
import json
import os
from typing import Any

GATEWAY_URL = "https://ai-gateway.vercel.sh/v1/evaluate"
MODEL = "typesafe-ai/jev"
MAX_BODY_BYTES = 64 * 1024
MAX_QUESTIONS = 32
ALLOWED_TYPES = {"boolean", "choice", "score"}


class RequestValidationError(ValueError):
    pass


def upstream_token() -> str:
    return (
        os.environ.get("AI_GATEWAY_API_KEY", "").strip()
        or os.environ.get("VERCEL_OIDC_TOKEN", "").strip()
    )


def proxy_token() -> str:
    return os.environ.get("JEV_PROXY_TOKEN", "").strip()


def token_matches(received: str | None) -> bool:
    expected = proxy_token()
    if not expected or not received:
        return False
    return hmac.compare_digest(received, expected)


def _validate_json_value(value: Any, *, name: str) -> None:
    if not isinstance(value, (str, list, dict)):
        raise RequestValidationError(f"{name} must be a string, object, or array")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RequestValidationError(f"{name} must be valid JSON") from exc


def normalize_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RequestValidationError("request body must be a JSON object")

    if "state" not in payload:
        raise RequestValidationError("state is required")
    state = payload["state"]
    _validate_json_value(state, name="state")

    questions = payload.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise RequestValidationError("questions must be a non-empty object")
    if len(questions) > MAX_QUESTIONS:
        raise RequestValidationError(f"questions may contain at most {MAX_QUESTIONS} entries")

    clean_questions: dict[str, dict[str, Any]] = {}
    for name, question in questions.items():
        if not isinstance(name, str) or not name or len(name) > 64:
            raise RequestValidationError("question names must be non-empty strings up to 64 characters")
        if not isinstance(question, dict):
            raise RequestValidationError(f"question {name!r} must be an object")

        qtype = question.get("type")
        if qtype not in ALLOWED_TYPES:
            raise RequestValidationError(
                f"question {name!r} type must be one of {sorted(ALLOWED_TYPES)}"
            )
        instructions = question.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            raise RequestValidationError(f"question {name!r} instructions are required")
        if len(instructions) > 4000:
            raise RequestValidationError(f"question {name!r} instructions are too long")

        if qtype == "choice":
            criteria = question.get("criteria")
            if not isinstance(criteria, dict) or len(criteria) < 2:
                raise RequestValidationError(
                    f"choice question {name!r} requires at least two criteria"
                )
            if len(criteria) > 32:
                raise RequestValidationError(
                    f"choice question {name!r} may contain at most 32 criteria"
                )
            for key, description in criteria.items():
                if not isinstance(key, str) or not key:
                    raise RequestValidationError(
                        f"choice question {name!r} criteria keys must be non-empty strings"
                    )
                if not isinstance(description, str) or not description.strip():
                    raise RequestValidationError(
                        f"choice question {name!r} criteria descriptions must be non-empty strings"
                    )

        clean_questions[name] = question

    normalized = {
        "model": MODEL,
        "state": state,
        "questions": clean_questions,
    }
    encoded = json.dumps(normalized, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_BODY_BYTES:
        raise RequestValidationError(f"normalized request exceeds {MAX_BODY_BYTES} bytes")
    return normalized
