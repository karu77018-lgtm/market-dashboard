"""Private session snapshots. Never use a new scanner result on a rerun."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def digest_rows(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def load_frozen(work: Path, session: str):
    path = work / "universes" / f"{session}.json"
    if not path.exists():
        if (work.parent / "universe-snapshots" / f"{session}.json").exists():
            raise RuntimeError("frozen universe cache missing; restore private snapshot before rerunning this session")
        return None
    value = json.loads(path.read_text())
    rows = value.get("rows", [])
    tickers = [r["ticker"] for r in rows]
    if (value.get("session_date") != session or not rows or len(set(tickers)) != len(tickers)
            or value.get("rows_sha256") != digest_rows(rows)):
        raise RuntimeError("invalid or modified frozen session universe")
    write_ledger(work, value)
    return value


def save_frozen(work, session, rows, stats, tv_stats, generated_at):
    existing = load_frozen(work, session)
    if existing:
        return existing
    observed = datetime.fromisoformat(generated_at.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York"))
    # The scanner cannot reconstruct historical fundamentals. Expose late first
    # captures instead of silently claiming point-in-time historical data.
    late = observed.date().isoformat() > session
    value = {"schema": "source-mc57.session-universe.1", "session_date": session,
             "captured_at": generated_at, "scanner_observed_at": generated_at,
             "point_in_time_verified": False,
             "late_capture": late,
             "historical_use": "unverified scanner fundamentals; exclude from point-in-time backtests",
             "rows_sha256": digest_rows(rows), "ticker_count": len(rows),
             "broad_count": tv_stats.get("active_universe", len(rows)),
             "rows": rows, "expansion_stats": stats, "tradingview_stats": tv_stats}
    path = work / "universes" / f"{session}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")
    write_ledger(work, value)
    return value


def write_ledger(work, value):
    ledger = work.parent / "universe-snapshots" / f"{value['session_date']}.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    public = {k: v for k, v in value.items() if k not in {"rows", "expansion_stats", "tradingview_stats"}}
    public["tickers"] = [r["ticker"] for r in value["rows"]]
    if ledger.exists():
        if json.loads(ledger.read_text()) != public:
            raise RuntimeError("frozen universe does not match published ledger")
        return
    with ledger.open("x", encoding="utf-8") as handle:
        json.dump(public, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")


def coverage_stats(rows, current):
    covered = sum(r["ticker"] in current for r in rows)
    return {"massive_current_covered": covered, "massive_current_missing": len(rows) - covered,
            "massive_current_coverage": covered / len(rows), "active_universe": len(rows)}
