"""Reader-facing names for the dashboard's internal codes (display text only).

Internal identifiers stay as they are (data keys, ids, files, scripts, logic);
only visible text changes:

* MC57 (market-internals composite, 0-100)   -> マーケットパルス
* NQ運用判定 (NQ trend regime for the leverage sleeve) -> NQトレンド信号

Only text between tags is rewritten; <script>, <style> and attribute values are
left alone, so nothing that code reads can change.  Idempotent.

  python scripts/naming.py [--html source-mc57.html]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

PULSE = "マーケットパルス"
NQ_SIGNAL = "NQトレンド信号"

# longest / most specific first; plain "MC57" last
NAMES: tuple[tuple[str, str], ...] = (
    ("マーケットステータス（MC57・市場内部）", f"{PULSE}（市場内部スコア）"),
    ("MC57内訳（12指標 / 4グループ）", f"{PULSE}の内訳（12指標 / 4グループ）"),
    ("MC57 12指標の推移", f"{PULSE} 12指標の推移"),
    ("MC57構成指標", "パルス構成指標"),
    ("補助リスク（MC57外）", "補助リスク（パルス外）"),
    ("最終MC57", "最終スコア"),
    ("MC57", PULSE),
    ("NQ運用判定", NQ_SIGNAL),
)

_SKIP = re.compile(r"(<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>|<[^>]+>)", re.S | re.I)


def rename_text(segment: str) -> str:
    for old, new in NAMES:
        segment = segment.replace(old, new)
    return segment


def apply(text: str) -> str:
    out, pos = [], 0
    for m in _SKIP.finditer(text):
        out.append(rename_text(text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(rename_text(text[pos:]))
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default="source-mc57.html")
    page = Path(ap.parse_args().html)
    page.write_text(apply(page.read_text(encoding="utf-8")), encoding="utf-8")
    print("reader-facing names applied", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
