"""Replace the ticker-candle script/style in the published page with the current ones.

The candle chart (tap a ticker) is added by enhance_source_mc57.py during the daily
refresh.  When only its drawing code changes, display workflows use this to update
the published page without re-acquiring data.  Idempotent.

  python scripts/candle_refresh.py [--html source-mc57.html]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def apply(text: str) -> str:
    from enhance_source_mc57 import SCRIPT, STYLE
    for tag, block in (("script", SCRIPT), ("style", STYLE)):
        ident = f"mc57-candle-{tag}"
        pat = re.compile(rf'<{tag} id="{ident}">.*?</{tag}>', re.S)
        new = block.strip()
        if pat.search(text):
            text = pat.sub(lambda m: new, text, count=1)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default="source-mc57.html")
    page = Path(ap.parse_args().html)
    text = page.read_text(encoding="utf-8")
    out = apply(text)
    if out != text:
        page.write_text(out, encoding="utf-8")
    print("candle chart code refreshed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
