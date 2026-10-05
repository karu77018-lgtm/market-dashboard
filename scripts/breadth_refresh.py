"""Re-render the 50MA-participation and 52-week high-low cards from saved inputs.

Display workflows (no market re-acquisition): when the chart format of these two
cards changes, the published page is updated from the OHLCV the last refresh
saved for the same session (Actions cache work/ohlcv.csv), instead of waiting for
the next daily refresh.  Nothing happens when the saved data is missing or from a
different session.  Idempotent.

  python scripts/breadth_refresh.py [--root .] [--html source-mc57.html]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from enhance_source_mc57 import breadth_cards  # noqa: E402
from rule_refresh import load_frame  # noqa: E402

FIRST = 'data-source-improvement="50ma-participation"'
SECOND = 'data-source-improvement="52week-high-low"'


def _card_span(text: str, marker: str) -> tuple[int, int] | None:
    i = text.find(marker)
    if i < 0:
        return None
    start = text.rfind("<div", 0, i)
    depth = 0
    for tag in re.finditer(r"<(/?)div\b[^>]*>", text[start:]):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return start, start + tag.end()
    return None


def replace_cards(text: str, html: str) -> str:
    a, b = _card_span(text, FIRST), _card_span(text, SECOND)
    if not a or not b or a[1] > b[0]:
        return text
    return text[:a[0]] + html + text[b[1]:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--html", default="source-mc57.html")
    a = ap.parse_args()
    root = Path(a.root)
    page = root / a.html
    session = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))["session_date"]
    frame = load_frame(root / "work" / "ohlcv.csv", session)
    if frame is None:
        print(f"saved OHLCV for {session} unavailable; breadth cards left as published", flush=True)
        return 0
    text = page.read_text(encoding="utf-8")
    out = replace_cards(text, breadth_cards(frame))
    if out != text:
        page.write_text(out, encoding="utf-8")
    print("breadth cards re-rendered from saved inputs", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
