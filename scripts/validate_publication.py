#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    root = Path(args.root)
    manifest = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))
    session = manifest["session_date"]
    html = (root / "source-mc57.html").read_text(encoding="utf-8")
    mc57 = json.loads((root / "data" / "mc57.json").read_text(encoding="utf-8"))
    index = json.loads((root / "chart-data" / "index.json").read_text(encoding="utf-8"))
    rs = json.loads((root / "data" / "rs.json").read_text(encoding="utf-8"))

    required = [
        "マーケットステータス（地合いスコア）", "地合いスコアの内訳（4本柱）",
        "Daily", "Positions", "Core 12", "Setups", "Rotation", "Movers",
        "Weekly", "Publish", "Rules", "ブレッドス推移（50日線上の割合）",
        "52週 新高値 − 新安値", "mc57-candle-script",
    ]
    missing = [marker for marker in required if marker not in html]
    if missing:
        raise SystemExit("HTML markers missing: " + ", ".join(missing))
    if session not in html:
        raise SystemExit(f"target session {session} not present in HTML")
    expected = f'<div class="val">{float(mc57["mc57"]):.0f}<span style="font-size:15px;font-weight:600">/100</span></div>'
    if expected not in html:
        raise SystemExit("rendered MC57 does not match authoritative current value")
    if mc57.get("status") != "READY" or mc57.get("coverage") != 1.0:
        raise SystemExit("MC57 is not READY at 57/57 current coverage")
    universe = len(rs.get("rows", []))
    candles = int(index.get("ticker_count", 0))
    if universe <= 0 or candles / universe < .95:
        raise SystemExit(f"candle coverage below 95%: {candles}/{universe}")
    if manifest.get("mcap_coverage", 0) < .95:
        raise SystemExit("market-cap coverage below 95%")
    print(json.dumps({"status": "READY", "session_date": session, "mc57": mc57["mc57"],
                      "universe": universe, "candle_tickers": candles}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
