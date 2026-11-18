"""先行アラート for the share card (display only): signs that came before the entry gate closing.

Local study research/lead-alerts-2026-11/lead.py (2014-2019 and 2020-2026, gate = QQQ above its 200-day average):
- risk:  high beta vs low volatility (SPHB/SPLV) down 5%+ over 20 sessions   -> caught 83% / 83% of the gate closings
- f3:    leader lamp F3 at 警戒 (60%+)                                       -> 83% of the closings in 2020-2026
- nfci:  financial conditions (NFCI) up more than 0.05 over 4 weeks          -> hit 60% / 75% (any day: 17% / 14%)
- score: market score under 30                                               -> hit 50% / 57%
- both:  two or more of them lit within 10 sessions                          -> hit 50% / 33%, caught 83% / 67%
Histories live in seed/lead-alerts.json (backfilled locally); the refresh adds F3 from the page, NFCI from the
decline card's saved series and SPHB/SPLV closes from Yahoo.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

SEED = "seed/lead-alerts.json"
KEEP_FROM = "2016-01-01"
ALERTS = (("risk", "リスク選好"), ("f3", "先導株"), ("nfci", "金融環境"), ("score", "スコア30"))
RISK_DROP, F3_BAD, NFCI_RISE, SCORE_CUT, BOTH_WINDOW = -0.05, 0.60, 0.05, 30.0, 10


def load(root: Path) -> dict:
    try:
        return json.loads((root / SEED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _series(d: dict | None) -> pd.Series:
    if not d:
        return pd.Series(dtype=float)
    s = pd.Series(d, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index().dropna()


def with_page(seed: dict, page: str) -> dict:
    """The seed plus the latest daily F3 from the page (the lamps card keeps a year of it)."""
    import regime_history as rh
    out = {k: dict(v) for k, v in seed.items() if isinstance(v, dict)}
    reg = rh.embedded_state(page)
    if reg and reg.get("f3"):
        out.setdefault("f3", {}).update({d: round(float(v), 4) for d, v in zip(reg["dates"], reg["f3"]) if v is not None})
    return out


def current(root: Path, page: str) -> dict:
    """Seed + the page's F3 + the decline card's saved NFCI (no network; both paths)."""
    data = with_page(load(root), page)
    try:
        import decline_anatomy as da
        nf = da.load_slow(root).get("nfci")
        if nf:
            data.setdefault("nfci", {}).update(nf)
    except Exception:  # display only
        pass
    return data


def _yahoo(symbols: tuple[str, ...], session: str) -> dict[str, dict[str, float]]:
    import sys
    import yfinance as yf
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from v38 import live_acquisition as la
    out = {}
    start = (pd.Timestamp(session) - pd.Timedelta(days=70)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(session) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    for tk in symbols:
        raw = yf.download(tk, start=start, end=end, auto_adjust=False, actions=False, progress=False, threads=False, timeout=20)
        f = la.select_yfinance_symbol_frame(raw, tk)
        if f.empty or "adj_close" not in f:
            continue
        s = pd.to_numeric(f["adj_close"], errors="coerce")
        s.index = pd.to_datetime(s.index, utc=True).tz_localize(None).normalize()
        out[tk] = {str(d.date()): round(float(v), 4) for d, v in s.dropna().items() if str(d.date()) <= session}
    return out


def update(root: Path, page: str, session: str) -> dict:
    """Refresh side: add today's F3, NFCI and SPHB/SPLV to the seed and save it.  Failures keep the saved series."""
    data = current(root, page)
    try:
        fresh = _yahoo(("SPHB", "SPLV"), session)
        for tk in ("SPHB", "SPLV"):
            if fresh.get(tk):
                data.setdefault(tk.lower(), {}).update(fresh[tk])
    except Exception as exc:  # display only
        print(f"lead alerts: SPHB/SPLV not updated ({type(exc).__name__})", flush=True)
    for k, v in list(data.items()):
        data[k] = {d: x for d, x in sorted(v.items()) if d >= KEEP_FROM}
    data["note"] = __doc__.strip().splitlines()[0]
    try:
        (root / SEED).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except OSError as exc:
        print(f"lead alerts: seed not written: {exc!r}", flush=True)
    return data


def states(data: dict, dates: list[str], pulse: list[float | None]) -> dict[str, list[bool]]:
    """Each alert lit or not on the given sessions, and 'both' (two or more lit within 10 sessions)."""
    idx = pd.to_datetime(dates)

    def on(cond: pd.Series) -> list[bool]:
        if cond.empty:
            return [False] * len(idx)
        c = cond.astype(float).reindex(cond.index.union(idx)).ffill().reindex(idx)
        return [bool(v) if v == v else False for v in c]
    hb, lv = _series(data.get("sphb")), _series(data.get("splv"))
    ratio = (hb / lv.reindex(hb.index).ffill()).dropna()
    out = {"risk": on(ratio / ratio.shift(20) - 1 <= RISK_DROP)}
    out["f3"] = on(_series(data.get("f3")) >= F3_BAD)
    nf = _series(data.get("nfci"))
    out["nfci"] = on(nf - nf.shift(4) > NFCI_RISE)           # weekly: four weeks
    out["score"] = [v is not None and v < SCORE_CUT for v in pulse]
    lit = pd.DataFrame({k: out[k] for k, _ in ALERTS}, index=idx)
    recent = lit.astype(int).rolling(BOTH_WINDOW, min_periods=1).max()
    out["both"] = [bool(v) for v in (recent.sum(axis=1) >= 2).values]
    return out
