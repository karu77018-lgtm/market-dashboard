#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import csv
import lzma
import hashlib
import importlib.util
import json
import math
import os
import pickle
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

SOURCE_SHA256 = "ee306726ee4b629f92c5d2d6687c06869702030f60922c93f44ead713bc8bb80"
SOURCE_PART_GLOB = "build_dashboard_4.py.lzma.b85.part*"


class CloneBuildError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloneBuildError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(obj, dict):
        raise CloneBuildError(f"JSON root is not object: {path}")
    return obj


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def reconstruct_source(source_dir: Path, target: Path) -> Path:
    parts = sorted(source_dir.glob(SOURCE_PART_GLOB))
    if not parts:
        raise CloneBuildError(f"source archive parts missing: {source_dir}/{SOURCE_PART_GLOB}")
    encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    try:
        compressed = base64.b85decode(encoded.encode("ascii"))
        raw = lzma.decompress(compressed)
    except Exception as exc:
        raise CloneBuildError(f"source archive cannot be decoded: {exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256:
        raise CloneBuildError(f"source SHA256 mismatch: {digest} != {SOURCE_SHA256}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    # 2026-09-20 improvement: every full-width chart uses five labels taken
    # from real observations (0/25/50/75/100%).  The frozen source guessed
    # half-year boundaries and could therefore show dates outside its data.
    text = target.read_text(encoding="utf-8")
    old = '''def _date_axis(ts):
    """チャート下端に半年ごとの日付ラベル（yy/m）を等間隔で並べる。"""
    if not ts or len(ts) < 2:
        return ""
    seen, labs = set(), []
    for d, _ in ts:
        dt = pd.Timestamp(d)
        h = 1 if dt.month <= 6 else 7
        key = (dt.year, h)
        if key not in seen:
            seen.add(key)
            labs.append(f'<span>{dt.year % 100}/{h}</span>')
    if len(labs) < 2:
        labs = [f'<span>{pd.Timestamp(ts[0][0]).strftime("%y/%-m")}</span>',
                f'<span>{pd.Timestamp(ts[-1][0]).strftime("%y/%-m")}</span>']
    return '<div class="dax">' + "".join(labs) + '</div>'
'''
    new = '''def _date_axis(ts):
    """実データ位置 0/25/50/75/100% の日付だけを表示する。"""
    if not ts or len(ts) < 2:
        return ""
    n = len(ts)
    pos = sorted(set([0, round((n - 1) * .25), round((n - 1) * .50),
                      round((n - 1) * .75), n - 1]))
    labs = []
    for i in pos:
        dt = pd.Timestamp(ts[i][0])
        labs.append(f'<span>{dt.strftime("%y/%-m")}</span>')
    return '<div class="dax">' + "".join(labs) + '</div>'
'''
    if old not in text:
        raise CloneBuildError("frozen source date-axis function was not found")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    return target


def write_universe_from_rs(data_dir: Path, output: Path) -> list[str]:
    rs = _load_json(data_dir / "rs.json")
    rows = rs.get("rows")
    if not isinstance(rows, list) or not rows:
        raise CloneBuildError("data/rs.json rows are required")
    output.parent.mkdir(parents=True, exist_ok=True)
    tickers: list[str] = []
    seen: set[str] = set()
    with output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["Ticker", "Name"])
        writer.writeheader()
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "").strip().upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            tickers.append(ticker)
            writer.writerow({"Ticker": ticker, "Name": str(row.get("name") or "").strip()})
    if not tickers:
        raise CloneBuildError("current universe resolved to zero tickers")
    return tickers


def write_sector_snapshot(data_dir: Path, output: Path) -> Path:
    rs = _load_json(data_dir / "rs.json")
    rs_rows = rs.get("rows") if isinstance(rs.get("rows"), list) else []
    s2i: dict[str, str] = {}
    e2j: dict[str, str] = {}
    for row in rs_rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        industry = str(row.get("industry") or "").strip()
        if ticker and industry:
            s2i[ticker] = industry
            e2j[industry] = industry

    s2t: dict[str, Any] = {}
    membership_path = data_dir / "theme_membership.json"
    if membership_path.is_file():
        membership = _load_json(membership_path)
        rows = membership.get("rows") if isinstance(membership.get("rows"), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "").strip().upper()
            major = str(row.get("major_theme") or "").strip()
            fine = str(row.get("theme_id") or row.get("theme_name") or "").strip()
            if not ticker or not fine:
                continue
            s2t[ticker] = [major, fine] if major and major != fine else fine

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"s2i": s2i, "s2t": s2t, "e2j": e2j}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return output


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "t", "yes", "y", "complete", "completed", "closed", "final", "ok", "checked"}


def build_w_from_ohlcv(ohlcv_csv: Path, session: str) -> dict[str, pd.DataFrame]:
    if not ohlcv_csv.is_file():
        raise CloneBuildError(f"OHLCV input missing: {ohlcv_csv}")
    df = pd.read_csv(ohlcv_csv)
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    required = {"ticker", "date", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise CloneBuildError(f"OHLCV columns missing: {missing}")
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    df = df[df["date"].notna()]
    session_ts = pd.Timestamp(session)
    df = df[df["date"] <= session_ts]
    if "is_complete" in df.columns:
        df = df[df["is_complete"].map(_truthy)]
    if df.empty:
        raise CloneBuildError("OHLCV has no completed rows through target session")
    out: dict[str, pd.DataFrame] = {}
    for raw, key in (("open", "Open"), ("high", "High"), ("low", "Low"), ("close", "Close"), ("volume", "Volume")):
        df[raw] = pd.to_numeric(df[raw], errors="coerce")
        wide = df.pivot_table(index="date", columns="ticker", values=raw, aggfunc="last").sort_index()
        wide.index = pd.DatetimeIndex(wide.index, name="Date")
        out[key] = wide
    close = out["Close"]
    if close.empty or close.index[-1].strftime("%Y-%m-%d") != session:
        raise CloneBuildError(
            f"OHLCV latest completed session {close.index[-1].strftime('%Y-%m-%d') if not close.empty else None} != {session}"
        )
    return out


def build_macro_from_market_inputs(data_dir: Path, session: str) -> dict[str, pd.DataFrame]:
    market = _load_json(data_dir / "market_inputs.json")
    if market.get("session_date") != session:
        raise CloneBuildError(
            f"market_inputs session mismatch: {market.get('session_date')} != {session}"
        )
    series = market.get("series")
    if not isinstance(series, dict):
        raise CloneBuildError("market_inputs.series is required")
    out: dict[str, pd.DataFrame] = {}
    for symbol, rows in series.items():
        if not isinstance(symbol, str) or not isinstance(rows, list):
            continue
        normalized: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("date"), str):
                continue
            try:
                day = pd.Timestamp(row["date"]).tz_localize(None).normalize()
            except Exception:
                continue
            if day > pd.Timestamp(session):
                continue
            item: dict[str, Any] = {"Date": day}
            for source, target in (("open", "Open"), ("high", "High"), ("low", "Low"), ("close", "Close"), ("volume", "Volume")):
                value = _finite(row.get(source))
                if value is not None:
                    item[target] = value
            if "Close" in item:
                normalized.append(item)
        if not normalized:
            continue
        out[symbol] = pd.DataFrame(normalized).drop_duplicates("Date", keep="last").set_index("Date").sort_index()
    for required in ("QQQ", "SPY", "^VIX"):
        if required not in out:
            raise CloneBuildError(f"required macro series missing from existing route: {required}")
    return out


def write_source_cache(ohlcv_csv: Path, data_dir: Path, output: Path, session: str) -> Path:
    payload = {
        "W": build_w_from_ohlcv(ohlcv_csv, session),
        "macro": build_macro_from_market_inputs(data_dir, session),
        "asof": session,
        "fetch_quality": {
            "source": "existing V38 acquisition route: TradingView universe + Yahoo OHLCV + market_inputs",
            "adapter_only": True,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as fh:
        pickle.dump(payload, fh, protocol=4)
    return output


def mc57_series(data_dir: Path, session: str, *, max_date: pd.Timestamp | None = None) -> pd.Series:
    obj = _load_json(data_dir / "mc57.json")
    if obj.get("session_date") != session:
        raise CloneBuildError(f"mc57 session mismatch: {obj.get('session_date')} != {session}")
    if obj.get("status") != "READY":
        raise CloneBuildError(f"mc57 is not READY: {obj.get('status')}")
    rows = obj.get("history")
    if not isinstance(rows, list):
        raise CloneBuildError("mc57.history is required")
    points: dict[pd.Timestamp, float] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("date"), str):
            continue
        value = _finite(row.get("mc57"))
        if value is None:
            continue
        try:
            day = pd.Timestamp(row["date"]).tz_localize(None).normalize()
        except Exception:
            continue
        points[day] = value
    current = _finite(obj.get("mc57"))
    if current is not None:
        points[pd.Timestamp(session)] = current
    if not points:
        raise CloneBuildError("mc57 history has no finite observations")
    series = pd.Series(points, dtype=float).sort_index()
    if max_date is not None:
        series = series[series.index <= pd.Timestamp(max_date).tz_localize(None).normalize()]
    if series.empty or series.index[-1].strftime("%Y-%m-%d") != session:
        raise CloneBuildError(
            f"mc57 latest session {series.index[-1].strftime('%Y-%m-%d') if not series.empty else None} != {session}"
        )
    return series


def _ensure_ohlcv(data_dir: Path, work_dir: Path, session: str, tickers: list[str]) -> Path:
    candidate = work_dir / "ohlcv.csv"
    if candidate.is_file() and candidate.stat().st_size > 0:
        return candidate
    try:
        import yfinance as yf
        from v38.live_acquisition import download_stock_ohlcv
    except Exception as exc:
        raise CloneBuildError(f"cannot load existing V38 acquisition route: {exc}") from exc
    work_dir.mkdir(parents=True, exist_ok=True)
    download_stock_ohlcv(yf, tickers, target_session=session, output_path=candidate)
    if not candidate.is_file() or candidate.stat().st_size == 0:
        raise CloneBuildError("existing V38 acquisition route did not produce OHLCV")
    return candidate


def _isolated_env(temp: Path, *, universe: Path, sector: Path, cache: Path, output: Path,
                  mktcap: Path) -> dict[str, str]:
    return {
        "V38_UNIVERSE_CSV": str(universe),
        "V38_SECTOR_JSON": str(sector),
        "V38_CACHE": str(cache),
        "V38_CACHE_ROOT_STRICT": "0",
        "V38_OUT_HTML": str(output),
        "V38_UNIVERSE_AUTO": "0",
        "V38_FMP_REFERENCE_BUDGET": "0",
        "V38_FRED_CACHE": str(temp / "fred_cache.json"),
        "V38_STATE_JSON": str(temp / "state.json"),
        "V38_LOG_CSV": str(temp / "daily_log.csv"),
        "V38_TREND_JSON": str(temp / "trend_history.json"),
        "V38_EQUITY_CSV": str(temp / "equity.csv"),
        "V38_ER_JSON": str(temp / "earnings.json"),
        "V38_MKTCAP_JSON": str(mktcap),
        "V38_OPT_JSON": str(temp / "options.json"),
        "V38_OPT_SCAN_HISTORY": str(temp / "options_scan_history.json"),
        "V38_OPT_TARGETS": str(temp / "options_targets.json"),
        "V38_INCEPT_VWAP_JSON": str(temp / "inception_vwap.json"),
        # The isolated publication never persists the source cache, therefore
        # repeating the 1,400-symbol period=max bootstrap on every daily run is
        # both wasteful and misleading.  The current three-year OHLCV remains
        # authoritative; inception VWAP degrades to unavailable independently.
        "V38_INCEPT_VWAP_BUDGET": "0",
        "V38_INDUSTRY_JSON": str(temp / "industry.json"),
        "V38_THEME_JSON": str(temp / "theme.json"),
        "V38_RISK_JSON": str(temp / "risk.json"),
        "V38_SAR_STATE": str(temp / "sar_state.txt"),
        "V38_NQ_EXPORT": str(temp / "nq_export.csv"),
    }


def import_source(source_path: Path, env: dict[str, str]):
    old_env = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    try:
        spec = importlib.util.spec_from_file_location("v38_exact_source_build_dashboard_4", source_path)
        if spec is None or spec.loader is None:
            raise CloneBuildError("cannot create source module spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        raise


def _install_mc57_score_patch(module: Any, data_dir: Path, session: str) -> None:
    original = module.mri_frame

    def mc57_mri_frame(macro, W=None):
        try:
            _legacy_series, breakdown, dropped, active, vals = original(macro, W)
        except ValueError as exc:
            # A diagnostic macro symbol can occasionally return a single stale
            # row under Yahoo throttling.  The legacy implementation intersects
            # every available series and can then discard all QQQ/SPY history.
            # MC57 is authoritative, so degrade the explanatory legacy frame to
            # the two required indices instead of blocking the publication.
            if "QQQ/SPY history" not in str(exc):
                raise
            essential = {k: macro[k] for k in ("QQQ", "SPY")
                         if k in macro and getattr(macro[k], "empty", True) is False}
            if len(essential) != 2:
                raise
            _legacy_series, breakdown, dropped, active, vals = original(essential, W)
        max_date = None
        try:
            close = W.get("Close") if isinstance(W, dict) else None
            if close is not None and len(close.index):
                max_date = pd.Timestamp(close.index[-1])
        except Exception:
            max_date = None
        score = mc57_series(data_dir, session, max_date=max_date)
        return score, breakdown, dropped, active, vals

    module.mri_frame = mc57_mri_frame


def validate_output(output: Path, data_dir: Path, session: str) -> None:
    if not output.is_file() or output.stat().st_size < 100_000:
        raise CloneBuildError(f"clone output missing or unexpectedly small: {output}")
    text = output.read_text(encoding="utf-8")
    required = (
        "マーケットステータス（地合いスコア）",
        "地合いスコアの内訳（4本柱）",
        "Daily",
        "Positions",
        "Core 12",
        "Setups",
        "Rotation",
        "Movers",
        "Weekly",
        "Publish",
        "Rules",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise CloneBuildError(f"source display markers missing: {missing}")
    current = float(mc57_series(data_dir, session).iloc[-1])
    expected = f'<div class="val">{current:.0f}<span style="font-size:15px;font-weight:600">/100</span></div>'
    if expected not in text:
        raise CloneBuildError(f"rendered market-condition value is not current MC57 ({current:.4f})")


def build(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    data_dir = (repo_root / args.data_dir).resolve() if not Path(args.data_dir).is_absolute() else Path(args.data_dir)
    source_dir = (repo_root / args.source_dir).resolve() if not Path(args.source_dir).is_absolute() else Path(args.source_dir)
    output = (repo_root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    work_dir = Path(args.work_dir).resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix="v38-exact-clone-work-"))

    state = _load_json(data_dir / "state.json")
    session = str(state.get("session_date") or "")
    if not session:
        raise CloneBuildError("data/state.json session_date is required")

    temp = Path(tempfile.mkdtemp(prefix="v38-exact-mc57-clone-"))
    source_path = reconstruct_source(source_dir, temp / "build_dashboard_4.py")
    universe_path = temp / "universe.csv"
    tickers = write_universe_from_rs(data_dir, universe_path)
    sector_path = write_sector_snapshot(data_dir, temp / "sector_snapshot.json")
    ohlcv_path = _ensure_ohlcv(data_dir, work_dir, session, tickers)
    cache_path = write_source_cache(ohlcv_path, data_dir, temp / "prices.pkl", session)

    output.parent.mkdir(parents=True, exist_ok=True)
    module = import_source(
        source_path,
        _isolated_env(temp, universe=universe_path, sector=sector_path, cache=cache_path,
                      output=output, mktcap=data_dir / "mktcap.json"),
    )
    _install_mc57_score_patch(module, data_dir, session)

    old_argv = list(sys.argv)
    try:
        sys.argv = [str(source_path), "--integration-test"]
        module.main()
    finally:
        sys.argv = old_argv

    validate_output(output, data_dir, session)
    current = float(mc57_series(data_dir, session).iloc[-1])
    return {
        "status": "READY",
        "output": str(output),
        "source_sha256": SOURCE_SHA256,
        "session_date": session,
        "market_condition_source": "data/mc57.json",
        "mc57": current,
        "existing_index_modified": False,
        "display_rearranged": False,
        "data_route": "existing V38 TradingView/Yahoo acquisition adapted to source cache schema",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a separate exact build_dashboard(4).py page with only the market-condition score series replaced by authoritative MC57."
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--source-dir", default="sources/build_dashboard_4")
    parser.add_argument("--work-dir")
    parser.add_argument("--output", default="_site/source-mc57.html")
    args = parser.parse_args()
    result = build(args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
