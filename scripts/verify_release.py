#!/usr/bin/env python3
"""Release gate for GitHub Pages: checks the committed files of one SHA.

validate_publication.py runs inside the refresh on the full work tree (including
ignored inputs such as data/rs.json).  This gate runs on a plain checkout of the
commit that is about to be published, so it uses only files that are in Git and
served by Pages:

  * required page markers, current rule version on every rule-dependent card;
  * one session across latest-manifest.json, data/mc57.json, chart-data/index.json
    and market-history/index.json, and that session present in the page;
  * the rendered MC57 equals data/mc57.json, which is READY at full coverage;
  * no empty sector-share data and no legacy MC57 display.

  python scripts/verify_release.py [--root .]

Exit 1 (with the reason) when the commit must not be published.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rules_tab import rule_problems  # noqa: E402
from validate_publication import REQUIRED_MARKERS  # noqa: E402


def problems(root: Path) -> list[str]:
    out: list[str] = []
    try:
        html = (root / "source-mc57.html").read_text(encoding="utf-8")
        manifest = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))
        mc57 = json.loads((root / "data" / "mc57.json").read_text(encoding="utf-8"))
        candles = json.loads((root / "chart-data" / "index.json").read_text(encoding="utf-8"))
        history = json.loads((root / "market-history" / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"published file unreadable: {exc}"]
    session = manifest.get("session_date")
    missing = [m for m in REQUIRED_MARKERS if m not in html]
    if missing:
        out.append("HTML markers missing: " + ", ".join(missing))
    out += ["rule: " + p for p in rule_problems(html)]
    sessions = {"data/mc57.json": mc57.get("session_date"), "chart-data/index.json": candles.get("session_date"),
                "market-history/index.json": history.get("session_date")}
    bad = {k: v for k, v in sessions.items() if v != session}
    if not session or bad:
        out.append(f"session mismatch against {session}: {bad}")
    elif session not in html:
        out.append(f"session {session} not present in HTML")
    if mc57.get("status") != "READY" or mc57.get("coverage") != 1.0:
        out.append("MC57 is not READY at full coverage")
    else:
        val = f'<div class="val">{float(mc57["mc57"]):.0f}<span style="font-size:15px;font-weight:600">/100</span></div>'
        if val not in html:
            out.append("rendered MC57 does not match data/mc57.json")
    if re.search(r"\bvar\s+MAJ\s*=\s*\[\s*\]\s*;", html):
        out.append("sector share data is empty (MAJ=[])")
    if "地合いスコアの内訳（4本柱）" in html or "地合いは青" in html:
        out.append("legacy MC57 display found")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    found = problems(Path(ap.parse_args().root))
    if found:
        print("release blocked:\n- " + "\n- ".join(found), flush=True)
        return 1
    print("release gate passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
