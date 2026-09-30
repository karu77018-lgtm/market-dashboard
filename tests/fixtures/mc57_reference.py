# Frozen pre-change calculation from d6b2aaf (2026-09-30). Regression oracle only.
from typing import Any
import math
import numpy as np
import pandas as pd

MC57_ETFS = [
    "SMH", "XSD", "DRAM", "SOXX", "DTCR", "IGV", "WCLD", "SKYY", "CIBR",
    "AIQ", "QTUM", "BOTZ", "ARKW", "XBI", "IHI", "PPH", "GNOM", "KBE",
    "KRE", "IAI", "KIE", "XOP", "OIH", "XES", "TAN", "ICLN", "GRID",
    "FAN", "URA", "NLR", "LIT", "HYDR", "GDX", "SIL", "COPX", "XME",
    "SLX", "REMX", "ITA", "SHLD", "XAR", "JETS", "IYT", "BOAT", "XHB",
    "PAVE", "PKB", "XRT", "IBUY", "PEJ", "BLOK", "WGMI", "DRIV", "MOO",
    "PHO", "WOOD", "QQQE",
]

METRIC_NAMES = [
    "close_gt_sma10", "close_gt_sma20", "close_gt_sma50", "close_gt_sma200",
    "ret5_gt_0", "ret21_gt_0", "ret63_gt_0", "ret252_gt_0",
    "sma20_gt_sma50", "sma50_gt_sma200", "sma50_gt_sma50_shift20",
    "dd52_continuous_score",
]

def _participation(condition: pd.DataFrame, valid: pd.DataFrame) -> pd.Series:
    return condition.astype(float).where(valid).mean(axis=1, skipna=True) * 100.0

def compute_mc57(close: pd.DataFrame, target: str, generated_at: str) -> dict[str, Any]:
    sma10 = close.rolling(10, min_periods=10).mean()
    sma20 = close.rolling(20, min_periods=20).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    ret5, ret21 = close.pct_change(5, fill_method=None), close.pct_change(21, fill_method=None)
    ret63, ret252 = close.pct_change(63, fill_method=None), close.pct_change(252, fill_method=None)
    metrics: dict[str, pd.Series] = {
        "close_gt_sma10": _participation(close > sma10, close.notna() & sma10.notna()),
        "close_gt_sma20": _participation(close > sma20, close.notna() & sma20.notna()),
        "close_gt_sma50": _participation(close > sma50, close.notna() & sma50.notna()),
        "close_gt_sma200": _participation(close > sma200, close.notna() & sma200.notna()),
        "ret5_gt_0": _participation(ret5 > 0, ret5.notna()),
        "ret21_gt_0": _participation(ret21 > 0, ret21.notna()),
        "ret63_gt_0": _participation(ret63 > 0, ret63.notna()),
        "ret252_gt_0": _participation(ret252 > 0, ret252.notna()),
        "sma20_gt_sma50": _participation(sma20 > sma50, sma20.notna() & sma50.notna()),
        "sma50_gt_sma200": _participation(sma50 > sma200, sma50.notna() & sma200.notna()),
        "sma50_gt_sma50_shift20": _participation(
            sma50 > sma50.shift(20), sma50.notna() & sma50.shift(20).notna()),
    }
    rolling_high = close.rolling(252, min_periods=252).max()
    dd52 = close / rolling_high - 1.0
    dd_score = ((dd52 + 0.30) / 0.25 * 100.0).clip(0.0, 100.0)
    metrics["dd52_continuous_score"] = dd_score.mean(axis=1, skipna=True)

    mf = pd.DataFrame(metrics)[METRIC_NAMES]
    raw = mf.mean(axis=1, skipna=True).dropna()
    ema2 = raw.ewm(span=2, adjust=False).mean()
    mu = ema2.rolling(3780, min_periods=756).mean().shift(1)
    sigma = ema2.rolling(3780, min_periods=756).std(ddof=0).shift(1)
    z = (ema2 - mu) / sigma
    score = 100.0 / (1.0 + np.power(3.0, -z))
    day = pd.Timestamp(target)
    if day not in score.index or not math.isfinite(float(score.loc[day])):
        raise RuntimeError("MC57 current score could not be calculated")

    rows = []
    for d in score.dropna().iloc[-504:].index:
        vals = {name: float(mf.at[d, name]) for name in METRIC_NAMES if pd.notna(mf.at[d, name])}
        rows.append({
            "date": d.strftime("%Y-%m-%d"), "raw": float(raw.loc[d]),
            "ema2_raw": float(ema2.loc[d]), "z": float(z.loc[d]),
            "mc57": float(score.loc[d]), "metrics": vals,
            "fixed57_breadth_sma20": vals.get("close_gt_sma20"),
            "fixed57_breadth_sma50": vals.get("close_gt_sma50"),
            "fixed57_breadth_sma200": vals.get("close_gt_sma200"),
        })
    current_metrics = rows[-1]["metrics"]
    valid_counts = {name: int(57 - mf.loc[day, name:name].isna().sum()) for name in METRIC_NAMES}
    # The aggregate metric is finite if at least one ETF is valid; expose the
    # exact per-metric denominator directly from its inputs.
    valid_counts = {
        "close_gt_sma10": int((close.loc[day].notna() & sma10.loc[day].notna()).sum()),
        "close_gt_sma20": int((close.loc[day].notna() & sma20.loc[day].notna()).sum()),
        "close_gt_sma50": int((close.loc[day].notna() & sma50.loc[day].notna()).sum()),
        "close_gt_sma200": int((close.loc[day].notna() & sma200.loc[day].notna()).sum()),
        "ret5_gt_0": int(ret5.loc[day].notna().sum()), "ret21_gt_0": int(ret21.loc[day].notna().sum()),
        "ret63_gt_0": int(ret63.loc[day].notna().sum()), "ret252_gt_0": int(ret252.loc[day].notna().sum()),
        "sma20_gt_sma50": int((sma20.loc[day].notna() & sma50.loc[day].notna()).sum()),
        "sma50_gt_sma200": int((sma50.loc[day].notna() & sma200.loc[day].notna()).sum()),
        "sma50_gt_sma50_shift20": int((sma50.loc[day].notna() & sma50.shift(20).loc[day].notna()).sum()),
        "dd52_continuous_score": int(dd_score.loc[day].notna().sum()),
    }
    return {
        "schema_version": "v38.mc57.1", "calculation_version": "v38-mc57-live-1.0.0",
        "history_contract_version": "v38.mc57.history.2", "session_date": target,
        "generated_at": generated_at, "status": "READY", "coverage": 1.0,
        "source": "Yahoo Finance via yfinance 0.2.66; auto_adjust=False with explicit Adj Close; fixed recovered 56 MICRO_ETFS + QQQE",
        "etf_universe": MC57_ETFS, "raw": float(raw.loc[day]), "ema2_raw": float(ema2.loc[day]),
        "mu_prior": float(mu.loc[day]), "sigma_prior": float(sigma.loc[day]),
        "z": float(z.loc[day]), "mc57": float(score.loc[day]),
        "metric_scores": current_metrics,
        "fixed57_breadth": {"sma20": current_metrics["close_gt_sma20"],
                            "sma50": current_metrics["close_gt_sma50"],
                            "sma200": current_metrics["close_gt_sma200"]},
        "coverage_detail": {"fixed_etf_count": 57, "current_close_count": 57,
                            "current_close_coverage": 1.0, "metric_valid_counts": valid_counts,
                            "fetch": {"fixed_etf_count": 57, "downloaded_history_count": 57,
                                      "current_close_count": 57, "current_close_coverage": 1.0,
                                      "missing_current": [], "acquisition_attempts": 3,
                                      "retry_policy": "same fixed57 Yahoo contract; 30s then 60s backoff"}},
        "history_window_sessions": 504, "ui_history_limit": 504, "history": rows,
        "metric_history": {name: [{"date": r["date"], "value": r["metrics"][name]}
                                  for r in rows if name in r["metrics"]] for name in METRIC_NAMES},
        "price_contract": {"vendor": "Yahoo Finance", "client": "yfinance==0.2.66",
                           "download_auto_adjust": False, "calculation_price": "Adj Close",
                           "history_start": "2004-01-01", "symbol_substitution": "none",
                           "target_close_policy": "require all fixed 57 ETFs present for current session",
                           "missing_metric_policy": "exclude missing ETF from that metric denominator",
                           "target_session_source": "QQQ+SPY common completed session",
                           "timezone": "America/New_York", "completed_session_cutoff_et": "16:15",
                           "calendar": "observed US ETF daily sessions cut to Dashboard completed session"},
        "reference": {"verification_kind": "RECOVERED_FORMAL_SPEC_2026-09-16"},
    }
