#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


MAX_MEDIAN_VENDOR_GAP = 0.02

REQUIRED_MARKERS = (
    "マーケットステータス（MC57・市場内部）", "MC57内訳（12指標 / 4グループ）",
    "market-history-script", "NQ運用判定",
    "Daily", "Positions", "アーカイブ", 'id="archive-intro"', "Setups", "Rotation", 'id="t-themes"', "Movers",
    "Weekly", "Publish", "Rules", "Jev期待値", "mc57-candle-script",
    "jev-ranking-section", "ブレッドス推移（50日線上の割合）",
    "52週 新高値 − 新安値", 'data-source-improvement="50ma-participation"',
    'data-source-improvement="52week-high-low"',
)


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
    providers = json.loads((root / "data" / "provider_inputs.json").read_text(encoding="utf-8"))

    missing = [marker for marker in REQUIRED_MARKERS if marker not in html]
    if missing:
        raise SystemExit("HTML markers missing: " + ", ".join(missing))
    # Every output must describe the same completed session.
    sessions = {
        "latest-manifest.json": session, "data/mc57.json": mc57.get("session_date"),
        "data/rs.json": rs.get("session_date"), "data/provider_inputs.json": providers.get("session_date"),
        "chart-data/index.json": index.get("session_date"),
    }
    mismatched = {k: v for k, v in sessions.items() if v != session}
    if mismatched:
        raise SystemExit(f"session mismatch against {session}: {mismatched}")
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from rules_tab import rule_problems
    problems = rule_problems(html)
    if problems:
        raise SystemExit("rule version mismatch: " + "; ".join(problems))
    if re.search(r"\bvar\s+MAJ\s*=\s*\[\s*\]\s*;", html):
        raise SystemExit("Sector Rotation share card major-sector data is empty (MAJ=[])")
    if session not in html:
        raise SystemExit(f"target session {session} not present in HTML")
    expected = f'<div class="val">{float(mc57["mc57"]):.0f}<span style="font-size:15px;font-weight:600">/100</span></div>'
    if expected not in html:
        raise SystemExit("rendered MC57 does not match authoritative current value")
    if mc57.get("status") != "READY" or mc57.get("coverage") != 1.0:
        raise SystemExit("MC57 is not READY at 57/57 current coverage")
    history = json.loads((root / "market-history" / "index.json").read_text())
    if history["session_date"] != session:
        raise SystemExit("long history index session mismatch")
    if "地合いスコアの内訳（4本柱）" in html or "地合いは青" in html:
        raise SystemExit("legacy MC57/SAR display found")
    for key in ("mc57", "leadership", "concentration", "relative", "gics11"):
        if key not in history["files"]:
            raise SystemExit("history route missing: " + key)
    for win in ("2y", "5y", "10y"):
        obj = json.loads((root / "market-history" / history["files"]["mc57"][win]).read_text())
        if obj["dates"][-1] != session or obj["current"] != mc57["mc57"]:
            raise SystemExit("MC57 history/current mismatch")
    universe = len(rs.get("rows", []))
    candles = int(index.get("ticker_count", 0))
    if universe <= 0 or candles / universe < .95:
        raise SystemExit(f"candle coverage below 95%: {candles}/{universe}")
    if manifest.get("mcap_coverage", 0) < .95:
        raise SystemExit("market-cap coverage below 95%")
    massive = providers.get("massive", {})
    fred = providers.get("fred", {})
    structure = massive.get("market_structure", {})
    cross = massive.get("cross_vendor", {})
    if massive.get("status") not in {"READY", "FALLBACK_YAHOO"} or structure.get("status") != "READY":
        raise SystemExit("market-structure provider inputs are not READY")
    if float(structure.get("coverage", 0)) < .95:
        raise SystemExit("Massive market-structure coverage below 95%")
    if massive.get("status") == "READY" and float(cross.get("coverage", 0)) < .95:
        raise SystemExit("Yahoo/Massive cross-vendor coverage below 95%")
    # Both vendors are split-adjusted, so a typical name agrees within a fraction of
    # a percent; a large median gap means one side has wrong scale or wrong day.
    median_gap = cross.get("median_absolute_deviation")
    if massive.get("status") == "READY" and (median_gap is None or float(median_gap) > MAX_MEDIAN_VENDOR_GAP):
        raise SystemExit(f"Yahoo/Massive median close gap {median_gap} exceeds {MAX_MEDIAN_VENDOR_GAP:.0%}")
    if fred.get("status") not in {"READY", "PARTIAL"}:
        raise SystemExit("FRED provider inputs are not usable")
    if float(fred.get("required_coverage", 0)) < .70:
        raise SystemExit("FRED required-series coverage below 70%")
    print(json.dumps({"status": "READY", "session_date": session, "mc57": mc57["mc57"],
                      "universe": universe, "candle_tickers": candles,
                      "fred_status": fred["status"],
                      "massive_structure_coverage": structure["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
