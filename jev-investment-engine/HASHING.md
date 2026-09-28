# Jev hashing specification

Updated: 2026-09-28

## Canonical JSON

All hash inputs use the same canonicalization rules as `jev.js`:

1. Unicode strings are normalized to NFC.
2. Object keys are recursively sorted lexicographically.
3. Array order is preserved.
4. The normalized value is serialized as compact JSON.
5. SHA-256 is calculated over the UTF-8 bytes of that JSON.

Canonicalization version: `canon-v1`.

## state_text_hash

```text
SHA256(canonicalJson(state_payload))
```

A string state is first wrapped as:

```json
{"text":"..."}
```

## dedupe_key

Do not change this formula. Existing evaluations depend on it.

```json
{
  "asof_timestamp": "<ISO timestamp>",
  "question_set_version": "<version>",
  "requested_model": "typesafe-ai/jev",
  "source_document_id": null,
  "state_text_hash": "<64 hex>",
  "ticker": "<UPPERCASE>"
}
```

Then:

```text
SHA256(canonicalJson(object_above))
```

`evaluation_kind` is intentionally NOT part of the dedupe key.
If the same dedupe identity arrives under another kind, the API must return HTTP 409.

## question_text_hash

Recovered from existing `jev-text-v1` rows and verified against BOTH:

- `RF01_dilution` (boolean)
- `THEME01_primary_theme` (choice)

Input object:

```json
{
  "question_id": "...",
  "question_type": "...",
  "instructions": "...",
  "options": null,
  "binary_threshold": 0.5,
  "score_scale_min": null,
  "score_scale_max": null,
  "ordinal": 1
}
```

For choice questions, `options` contains the options object. The key is `options`,
even though the database column is named `options_json`.

Formula:

```text
question_text_hash = SHA256(canonicalJson(input_object))
```

Verified existing hashes:

- RF01: `d7bf3abba3946130777febb0d8094cac9f3f849b4099720ebc92b278a39124b8`
- THEME01: `33f6310216ce3a4bd7558fd2aa3c1bd2fe67640f4f2fc77ee8769715fb62384f`

The original v1 question text is also present in Git commit:
`043880903a97c2c17d8125e4312640066bfbd6f2`.

## question_set_hash

Do not invent or silently change its formula. The current v1 stored hash is preserved.
Before creating `jev-text-v2`, recover/document the exact question-set hash formula separately.
