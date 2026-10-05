"""Reader-facing names for the dashboard's internal codes (display text only).

Internal identifiers stay as they are (data keys, ids, files, scripts, logic);
only visible text changes:

* MC57 (market-internals composite, 0-100)   -> マーケットパルス
* NQ運用判定 (NQ trend regime for the leverage sleeve) -> NQトレンド信号
* English / index-based chart titles and notes -> plain Japanese, % change wording

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
    # comparison charts: plain Japanese titles and % change wording
    ("時価総額別の強さ推移 / Market Leadership", "サイズ別の強さ（小型株〜MAG7）"),
    ("サイズ別相対推移 / Market Leadership", "サイズ別の強さ（小型株〜MAG7）"),
    ("Cap Weight vs Equal Weight", "時価総額加重と等ウェイトの比較"),
    ("時価総額加重 / 等ウェイト 相対強度", "大型株への集中度（加重÷等ウェイト）"),
    ("Index / Internals Divergence", "指数と広がりの乖離"),
    ("QQQ / SPY / TQQQ / SOXX / SOXL / VIX。選択期間開始=100。",
     "QQQ / SPY / SOXX（TQQQ・SOXL・VIXは凡例をタップで表示）。期間初日を0%とした騰落率。"),
    ("選択期間開始=100、上昇=時価総額加重優位、低下=等ウェイト優位。",
     "期間初日を0%とした比。上昇＝大型株（時価総額加重）が優位、低下＝等ウェイト（広がり）が優位。"),
    ("選択期間開始=100", "期間初日を0%とした騰落率"),
    ("期間開始=100", "期間初日を0%とした騰落率"),
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
