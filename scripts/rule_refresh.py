"""Re-render the rule-dependent cards from saved inputs (display workflows).

The lightweight display publication never re-acquires market data, so a rule
change merged between daily refreshes used to leave the published Rules tab,
swing card, pickup card and breakout-health card on the old rule.  This step
rebuilds exactly those cards from the inputs the last refresh saved (Actions
cache: work/ohlcv.csv and work/market-inputs-cache.json, same session as the
manifest), reusing the option walls already in the page (no network), and then
checks that every rule-dependent card carries the current RULE_ID.

  python scripts/rule_refresh.py [--root .] [--html source-mc57.html]

Exit 1 when the page still mixes rule versions (the workflow must not publish).
Reruns are idempotent.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import breakout_health  # noqa: E402
import pickup_watch  # noqa: E402
import rules_tab  # noqa: E402
import swing_screener  # noqa: E402

CARD_IDS = (swing_screener.CARD_ID, pickup_watch.CARD_ID, breakout_health.CARD_ID)
STYLE_IDS = ("mc57-swing-screener-style", "mc57-pickup-watch-style")


def remove_div(text: str, element_id: str) -> str:
    """Remove the <div ... id="element_id"> element (balanced), if present."""
    m = re.search(rf'<div\b[^>]*\bid="{re.escape(element_id)}"', text)
    if not m:
        return text
    depth, pos = 0, m.start()
    for tag in re.finditer(r"<(/?)div\b[^>]*>", text[m.start():]):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            end = m.start() + tag.end()
            return text[:m.start()] + text[end:]
    raise ValueError(f"unbalanced <div> for {element_id}")


def remove_style(text: str, style_id: str) -> str:
    return re.sub(rf'\s*<style id="{re.escape(style_id)}">.*?</style>', "", text, count=1, flags=re.S)


def page_det(text: str) -> dict:
    i = text.find("window.DET=")
    if i < 0:
        return {}
    try:
        return json.JSONDecoder().raw_decode(text, i + len("window.DET="))[0]
    except ValueError:
        return {}


def load_frame(path: Path, session: str) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    frame = pd.read_csv(path, usecols=["ticker", "date", "open", "high", "low", "close", "volume"])
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for c in ("open", "high", "low", "close", "volume"):
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    frame = frame[frame["date"].notna() & (frame["date"] <= pd.Timestamp(session))]
    if frame.empty or frame["date"].max() != pd.Timestamp(session):
        return None
    return frame


def regenerate(text: str, frame: pd.DataFrame, regime: dict | None, root: Path | None = None) -> str:
    det = page_det(text)
    try:
        health = breakout_health.compute(frame)
    except Exception as exc:  # display-only, same as the refresh path
        print(f"breakout health skipped: {exc!r}", flush=True)
        health = None
    for cid in CARD_IDS:
        if cid == breakout_health.CARD_ID and health is None:
            continue  # keep the published card rather than silently dropping it
        text = remove_div(text, cid)
    for sid in STYLE_IDS:
        text = remove_style(text, sid)

    def saved_walls(targets: dict, session: str) -> dict:
        return {t: dict(det[t]["opt"]) for t in targets
                if isinstance(det.get(t), dict) and isinstance(det[t].get("opt"), dict)}

    text = breakout_health.apply_daily(text, health, regime)
    text = pickup_watch.apply(text, frame, regime=regime)
    text = swing_screener.apply(text, frame, walls_fn=saved_walls, regime=regime, health=health)
    text = rules_tab.apply(text, regime=regime, health=health)
    if root is not None:
        import track_record
        text = track_record.render_only(text, root)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--html", default="source-mc57.html")
    a = ap.parse_args()
    root = Path(a.root)
    page = root / a.html
    text = page.read_text(encoding="utf-8")
    session = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))["session_date"]
    if rules_tab.rule_problems(text):
        if all(p.startswith("track-record-card") for p in rules_tab.rule_problems(text)):
            import track_record
            text = track_record.render_only(text, root)
            page.write_text(text, encoding="utf-8")
    if rules_tab.rule_problems(text):
        frame = load_frame(root / "work" / "ohlcv.csv", session)
        if frame is None:
            print(f"saved OHLCV for {session} unavailable; cannot re-render rule cards", flush=True)
        else:
            market = next((p for p in (root / "data" / "market_inputs.json", root / "work" / "market-inputs-cache.json")
                           if p.is_file()), None)
            regime = swing_screener.regime_from_market(market, session) if market else None
            text = regenerate(text, frame, regime, root)
            page.write_text(text, encoding="utf-8")
            print(f"re-rendered rule cards for {session} with {rules_tab.RULE_ID}", flush=True)
    problems = rules_tab.rule_problems(text)
    if problems:
        print("rule version mismatch: " + "; ".join(problems), flush=True)
        return 1
    print(f"rule cards consistent: {rules_tab.RULE_ID}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
