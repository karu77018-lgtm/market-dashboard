from __future__ import annotations

import pytest

from api._jev_core import MODEL, RequestValidationError, normalize_payload


def test_normalize_boolean_and_force_model():
    result = normalize_payload(
        {
            "model": "something-else",
            "state": {"ticker": "NVDA", "rs63": 94},
            "questions": {
                "continue": {
                    "type": "boolean",
                    "instructions": "Is momentum still constructive?",
                }
            },
        }
    )
    assert result["model"] == MODEL
    assert result["state"]["ticker"] == "NVDA"


def test_choice_requires_two_criteria():
    with pytest.raises(RequestValidationError):
        normalize_payload(
            {
                "state": "x",
                "questions": {
                    "bucket": {
                        "type": "choice",
                        "instructions": "Pick one",
                        "criteria": {"a": "only one"},
                    }
                },
            }
        )


def test_rejects_unknown_question_type():
    with pytest.raises(RequestValidationError):
        normalize_payload(
            {
                "state": "x",
                "questions": {
                    "bad": {"type": "freeform", "instructions": "No"}
                },
            }
        )
