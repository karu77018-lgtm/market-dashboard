"""今回の下げの分解 (Market tab).  Display only: no order, rule or ledger changes.

When QQQ has fallen 10% or more from its 252-session closing high (and has not yet come back to
within 4% of it), the card breaks the decline into factors measured from the high to the day
the -10% line was first crossed, and sets them against the same moment of every Nasdaq-100
correction since 1990 (``decline_reference.EPISODES``, a local study: research/decline-anatomy-2026-11).

What the study found, and what the card therefore says:
* the breakdown DESCRIBES a decline well (which type, what is unusual about it);
* "the nearest past year" does NOT forecast what follows (worse than the plain average), so
  the nearest years are listed as reference and a split between them is shown as such;
* two overheating checks (margin debt growth, CAPE) and the money-fund growth did relate to
  what followed, with different signs at different horizons - shown as a short/mid/long table.

Inputs: daily closes from data/market_inputs.json (the refresh's own download; the display-only
workflow has the same file as work/market-inputs-cache.json) and a few slow public series
(CAPE, FINRA margin debt, retail money funds, Baa spread, 10y/3m yields).  The slow series are
fetched best-effort and fall back to seed/decline-slow.json, so a failed fetch only makes the
card show an older "as of" date.  The computed state is embedded in the card, so the display
workflow can re-render it without any market data.
"""
from __future__ import annotations

import html
import json
import math
import re
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from decline_reference import EPISODES
import fold

CARD_ID = "decline-anatomy"
STATE_ID = "decline-anatomy-state"
STYLE_ID = "decline-anatomy-style"
SLOW_SEED = "seed/decline-slow.json"
STATE_SEED = "seed/decline-anatomy-state.json"
INDEX = "QQQ"
TRIGGER, REARM = -0.10, -0.04
SECTORS = ("XLK", "XLF", "XLE", "XLP", "XLU", "XLV", "XLY", "XLI", "XLB")
SYMBOLS = (INDEX, "SPY", "IWM", "RSP", "IWF", "IWD", "SOXX", "^VIX", "^TNX", "DX-Y.NYB", "JPY=X",
           "TLT", "GC=F", "CL=F", *SECTORS)

# key -> (category, label, unit, decimals)
FACTORS: dict[str, tuple[str, str, str, int]] = {
    "days": ("速さ・値動き", "−10%までの営業日数", "日", 0),
    "maxday": ("速さ・値動き", "最大の1日下落", "%", 1),
    "bounce": ("速さ・値動き", "途中の最大の戻り", "%", 1),
    "rv20": ("速さ・値動き", "直近20日の値動きの荒さ（年率）", "%", 0),
    "vix": ("恐怖", "VIX", "", 1),
    "dvix": ("恐怖", "VIXの上昇幅", "pt", 1),
    "sox": ("何が売られたか", "半導体（指数との差）", "pt", 1),
    "spx": ("何が売られたか", "S&P500（Nasdaq100との差）", "pt", 1),
    "small": ("何が売られたか", "小型株（大型株との差）", "pt", 1),
    "gv": ("何が売られたか", "グロース（バリューとの差）", "pt", 1),
    "eqw": ("何が売られたか", "均等加重（時価総額加重との差）", "pt", 1),
    "dfn": ("何が売られたか", "ディフェンシブ（S&P500との差）", "pt", 1),
    "fin": ("何が売られたか", "金融（S&P500との差）", "pt", 1),
    "ene": ("何が売られたか", "エネルギー（S&P500との差）", "pt", 1),
    "secup": ("何が売られたか", "高値の日より上がっているセクター（9のうち）", "", 0),
    "sec50": ("何が売られたか", "50日線より上のセクター（9のうち）", "", 0),
    "d10": ("金利・信用", "10年金利の変化", "bp", 0),
    "cred": ("金利・信用", "信用スプレッドの変化", "bp", 0),
    "usd": ("他の資産", "ドル指数", "%", 1),
    "jpy": ("他の資産", "ドル円", "%", 1),
    "tlt": ("他の資産", "米長期債", "%", 1),
    "gold": ("他の資産", "金", "%", 1),
    "wti": ("他の資産", "原油", "%", 1),
    "runup": ("位置", "高値までの1年の上昇", "%", 0),
    "v200": ("位置", "200日線からの距離", "%", 1),
    "cape": ("割高度・資金", "CAPE（S&P500の割高度）", "", 1),
    "md_yoy": ("割高度・資金", "信用買い残の前年比", "%", 0),
    "mm_yoy": ("割高度・資金", "個人向けMMF残高の前年比", "%", 0),
}
SIGNED = {"dvix", "sox", "spx", "small", "gv", "eqw", "dfn", "fin", "ene", "d10", "cred", "usd", "jpy",
          "tlt", "gold", "wti", "runup", "v200", "md_yoy", "mm_yoy", "maxday", "bounce"}
CATEGORIES = ("速さ・値動き", "恐怖", "何が売られたか", "金利・信用", "他の資産", "位置", "割高度・資金")
ANALOG_KEYS = ("days", "vix", "rv20", "runup", "v200", "sox", "small", "spx", "gv", "eqw", "dfn", "fin", "ene",
               "secup", "d10", "cred", "cape", "md_yoy", "usd", "jpy")
ANALOG_MIN = 12
ANALOG_NEED = ("dfn", "fin", "secup")  # sector data (1999 on): without it the comparison misses what was sold
TYPES = {
    "信用不安・質への逃避型": "信用スプレッドが広がり、金利は下がっています。景気や信用への不安で安全資産へ逃げる下げです。",
    "金利上昇型": "金利の上昇が重しになっている下げです。",
    "ハイテク単独安（資金移動）型": "S&P500は持ちこたえ、ハイテクから他へ資金が移っている下げです。信用不安でも金利上昇でもありません。",
    "全面安型": "ハイテクもそれ以外も同じように下げています。",
}
# (label, factor, threshold, strict) -> "applies" when value >= threshold (> when strict)
HORIZON_ROWS = (
    ("CAPE（割高度）が30以上", "cape", 30.0, False, True),
    ("信用買い残が前年比+20%以上", "md_yoy", 20.0, False, False),
    ("高値までの1年で+40%以上の上昇", "runup", 40.0, False, True),
    ("指数だけの下げ（4セクター以上が50日線上）", "sec50", 4.0, False, False),
    ("小型株が大型株より強い", "small", 0.0, True, True),
    ("待機資金が多い（MMF前年比+15%以上）", "mm_yoy", 15.0, False, False),
)
HORIZONS = (("短期", "20日後", "r20"), ("中期", "120日後", "r120"), ("長期", "250日後", "r250"), ("長期", "500日後", "r500"))


# ---------------------------------------------------------------- inputs
def _closes(market: dict) -> pd.DataFrame | None:
    """Daily closes of the symbols the card reads, on the index's sessions (carried forward)."""
    series = market.get("series") or {}
    cols: dict[str, pd.Series] = {}
    for sym in SYMBOLS:
        rows = series.get(sym) or []
        if not rows:
            continue
        f = pd.DataFrame(rows)
        if "close" not in f or "date" not in f:
            continue
        s = pd.Series(pd.to_numeric(f["close"], errors="coerce").to_numpy(),
                      index=pd.to_datetime(f["date"].astype(str).str[:10], errors="coerce"))
        s = s[s.index.notna()].dropna()
        cols[sym] = s[~s.index.duplicated(keep="last")].sort_index()
    if INDEX not in cols or len(cols[INDEX]) < 260:
        return None
    idx = cols[INDEX].index
    return pd.DataFrame({k: v.reindex(idx.union(v.index)).ffill().reindex(idx) for k, v in cols.items()}, index=idx)


def load_market(root: Path) -> dict | None:
    for rel in ("data/market_inputs.json", "work/market-inputs-cache.json"):
        path = root / rel
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    return None


def _get(url: str, timeout: int = 20) -> str:
    """Browser-like fetch.  FINRA answers 403 to plain HTTP clients, so curl_cffi (installed with
    yfinance in the refresh) is tried first; urllib is the fallback."""
    try:
        from curl_cffi import requests as cr
    except ImportError:
        cr = None
    if cr is not None:
        r = cr.get(url, impersonate="chrome", timeout=timeout)
        if r.status_code != 200:
            raise OSError(f"HTTP {r.status_code}")
        return r.text
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,text/csv;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed public https URLs)
        return resp.read().decode("utf-8", "replace")


def parse_fred_csv(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in text.splitlines()[1:]:
        day, _, val = line.partition(",")
        try:
            out[str(pd.Timestamp(day).date())] = float(val)
        except (ValueError, TypeError):
            continue
    return out


def parse_multpl(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for day, val in re.findall(r"<td[^>]*>\s*([A-Z][a-z]{2} \d{1,2}, \d{4})\s*</td>\s*<td[^>]*>(.*?)</td>", text, flags=re.S):
        num = re.search(r"-?\d+(?:\.\d+)?", re.sub(r"<[^>]+>|&#?\w+;|,", "", val))
        if num:
            out[str(pd.Timestamp(day).date())] = float(num.group(0))
    return out


def parse_finra(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for mon, val in re.findall(r"<td[^>]*>\s*([A-Z][a-z]{2}-\d{2})\s*</td>\s*<td[^>]*>\s*([\d,]+)\s*</td>", text):
        day = pd.Timestamp(pd.to_datetime(mon, format="%b-%y")) + pd.offsets.MonthEnd(0)
        out[str(day.date())] = float(val.replace(",", ""))
    return out


SLOW_SOURCES = {
    "cape": ("https://www.multpl.com/shiller-pe/table/by-month", parse_multpl),
    "margin": ("https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics", parse_finra),
    "mmf": ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=WRMFNS", parse_fred_csv),
    "baa": ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA10Y", parse_fred_csv),
    "dgs10": ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10", parse_fred_csv),
    "dtb3": ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3", parse_fred_csv),
}


def load_slow(root: Path) -> dict[str, dict[str, float]]:
    try:
        seed = json.loads((root / SLOW_SEED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: dict(v) for k, v in (seed.get("series") or {}).items()}


def refresh_slow(slow: dict[str, dict[str, float]], getter=_get) -> dict[str, dict[str, float]]:
    """Seed series with whatever newer public observations can be fetched (best effort)."""
    out = {k: dict(v) for k, v in slow.items()}
    down: set[str] = set()
    for key, (url, parse) in SLOW_SOURCES.items():
        host = url.split("/")[2]
        if host in down:  # one failure per site is enough waiting for a display-only card
            continue
        try:
            fresh = parse(getter(url))
        except Exception as exc:  # display only: keep the seed
            down.add(host)
            print(f"decline anatomy: {key} not refreshed ({type(exc).__name__}); using the saved series", flush=True)
            continue
        if len(fresh) >= 6:
            out.setdefault(key, {}).update(fresh)
    return out


# how much of each series the saved file keeps, and when it counts as stale (days since the last
# observation, against the session): FINRA publishes about three weeks after month end, multpl
# updates CAPE daily from the latest month, FRED's weekly money-fund series often runs a month or
# more behind (so 60 days), the Baa spread is daily.
SLOW_KEEP = {"cape": 40, "margin": 40, "mmf": 130, "baa": 520, "dgs10": 760, "dtb3": 760}
STALE = {"margin": ("信用買い残（FINRA）", 80), "cape": ("CAPE（multpl）", 45),
         "mmf": ("個人向けMMF残高（FRED）", 60), "baa": ("信用スプレッド（FRED）", 14)}


def trim_slow(slow: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    return {k: dict(sorted(v.items())[-SLOW_KEEP.get(k, len(v)):]) for k, v in sorted(slow.items()) if v}


def save_slow(root: Path, slow: dict[str, dict[str, float]], saved: str) -> bool:
    """Write the merged series back to the seed file (committed by the refresh) when they grew."""
    path = root / SLOW_SEED
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    new = trim_slow(slow)
    if new == old.get("series"):
        return False
    doc = {**{k: v for k, v in old.items() if k != "series"}, "schema": "decline-slow.1", "saved": saved, "series": new}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    return True


def stale_inputs(slow: dict, session: str) -> list[dict]:
    day = pd.Timestamp(session)
    out = []
    for key, (label, limit) in STALE.items():
        last = max(slow[key]) if slow.get(key) else None
        age = None if last is None else int((day - pd.Timestamp(last)).days)
        if age is None or age > limit:
            out.append({"key": key, "label": label, "last": last, "days": age})
    return out


def _series(slow: dict, key: str) -> pd.Series:
    d = slow.get(key) or {}
    if not d:
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(k): float(v) for k, v in d.items()}, dtype=float)
    return s.sort_index()


def _asof(s: pd.Series, day: pd.Timestamp, lag_days: int = 0) -> float | None:
    if s.empty:
        return None
    v = s[:day - pd.Timedelta(days=lag_days)]
    return float(v.iloc[-1]) if len(v) else None


# ---------------------------------------------------------------- episode + factors
def find_episode(q: pd.Series) -> dict | None:
    """The latest -10% trigger of the index and whether it is still open (not back within 4%)."""
    hi = q.rolling(252, min_periods=200).max()
    dd = q / hi - 1.0
    armed, last, seen = True, None, set()
    for t in range(len(q)):
        d = dd.iloc[t]
        if math.isnan(d):
            continue
        if armed and d <= TRIGGER:
            peak = q.iloc[max(0, t - 252):t + 1].idxmax()
            armed = False
            if peak not in seen:  # a second trigger off the same high keeps the first one
                seen.add(peak)
                last = {"peak": peak, "trigger": q.index[t]}
        elif not armed and d >= REARM:
            armed = True
    if last is None:
        return {"active": False, "dd_now": float(dd.iloc[-1]) * 100}
    return {**last, "active": not armed, "dd_now": float(dd.iloc[-1]) * 100}


def factors_at(px: pd.DataFrame, peak: pd.Timestamp, day: pd.Timestamp, slow: dict) -> dict[str, float | None]:
    """Every factor measured from the high (``peak``) to ``day``."""
    q = px[INDEX]
    p, t = px.index.get_loc(peak), px.index.get_loc(day)

    def ret(sym: str) -> float | None:
        if sym not in px:
            return None
        a, b = px[sym].iloc[p], px[sym].iloc[t]
        return None if (pd.isna(a) or pd.isna(b) or a == 0) else float(b / a - 1) * 100

    def diff(a: str, b: str) -> float | None:
        x, y = ret(a), ret(b)
        return None if x is None or y is None else x - y

    def level(sym: str, i: int) -> float | None:
        return None if sym not in px or pd.isna(px[sym].iloc[i]) else float(px[sym].iloc[i])

    day_ret = q.pct_change()
    seg = q.iloc[p:t + 1]
    sec = [ret(s) for s in SECTORS]
    ma50 = px[[s for s in SECTORS if s in px]].rolling(50, min_periods=50).mean()
    ma200 = q.rolling(200, min_periods=200).mean().iloc[t]
    xlp, xlu, spy = ret("XLP"), ret("XLU"), ret("SPY")
    vix_t, vix_p = level("^VIX", t), level("^VIX", p)
    tnx_t, tnx_p = level("^TNX", t), level("^TNX", p)
    rv = day_ret.iloc[max(0, t - 19):t + 1].std()
    out: dict[str, float | None] = {
        "days": float(t - p),
        "maxday": float(day_ret.iloc[p + 1:t + 1].min()) * 100 if t > p else None,
        "bounce": float((seg / seg.cummin() - 1).max()) * 100,
        "rv20": None if pd.isna(rv) else float(rv) * math.sqrt(252) * 100,
        "vix": vix_t,
        "dvix": None if vix_t is None or vix_p is None else vix_t - vix_p,
        "sox": diff("SOXX", INDEX), "spx": diff("SPY", INDEX), "small": diff("IWM", "SPY"),
        "gv": diff("IWF", "IWD"), "eqw": diff("RSP", "SPY"),
        "dfn": None if None in (xlp, xlu, spy) else (xlp + xlu) / 2 - spy,
        "fin": diff("XLF", "SPY"), "ene": diff("XLE", "SPY"),
        "secup": None if any(v is None for v in sec) else float(sum(v > 0 for v in sec)),
        "sec50": (None if len(ma50.columns) < len(SECTORS) or ma50.iloc[t].isna().any()
                  else float(sum(px[s].iloc[t] > ma50[s].iloc[t] for s in SECTORS))),
        "d10": None if tnx_t is None or tnx_p is None else (tnx_t - tnx_p) * 100,
        "usd": ret("DX-Y.NYB"), "jpy": ret("JPY=X"), "tlt": ret("TLT"), "gold": ret("GC=F"), "wti": ret("CL=F"),
        "runup": float(q.iloc[p] / q.iloc[p - 252] - 1) * 100 if p >= 252 else None,
        "v200": None if pd.isna(ma200) else float(q.iloc[t] / ma200 - 1) * 100,
    }
    baa, cape, margin, mmf = (_series(slow, k) for k in ("baa", "cape", "margin", "mmf"))
    b1, b0 = _asof(baa, day), _asof(baa, peak)
    out["cred"] = None if b1 is None or b0 is None else (b1 - b0) * 100
    out["cape"] = _asof(cape, peak)
    m1, m0 = _asof(margin, peak, 30), _asof(margin, peak, 30 + 365)
    out["md_yoy"] = None if not m1 or not m0 else (m1 / m0 - 1) * 100
    f1, f0 = _asof(mmf, peak, 7), _asof(mmf, peak, 7 + 365)
    out["mm_yoy"] = None if not f1 or not f0 else (f1 / f0 - 1) * 100
    return out


def inverted_before(slow: dict, peak: pd.Timestamp, days: int = 548) -> bool | None:
    """Was the 10y yield below the 3m yield at any time in the 18 months before the high?"""
    d10, d3 = _series(slow, "dgs10"), _series(slow, "dtb3")
    if d10.empty or d3.empty:
        return None
    gap = (d10 - d3).dropna()[peak - pd.Timedelta(days=days):peak]
    return None if gap.empty else bool((gap < 0).any())


def classify(f: dict) -> str:
    cred, d10, spx = f.get("cred"), f.get("d10"), f.get("spx")
    if cred is not None and d10 is not None and cred >= 15 and d10 <= -20:
        return "信用不安・質への逃避型"
    if d10 is not None and d10 >= 20:
        return "金利上昇型"
    if spx is not None and spx >= 5:
        return "ハイテク単独安（資金移動）型"
    return "全面安型"


def _past(key: str) -> list[float]:
    return [e[key] for e in EPISODES if e.get(key) is not None]


def rank(key: str, value: float | None) -> dict | None:
    """Where ``value`` sits among the past episodes (1 = most extreme on that side)."""
    past = _past(key)
    if value is None or len(past) < 15:
        return None
    lo, hi = sum(v < value for v in past) + 1, sum(v > value for v in past) + 1
    edge = max(2, math.ceil(len(past) * 0.075))
    side = "low" if lo <= edge else "high" if hi <= edge else None
    return {"n": len(past), "lo": lo, "hi": hi, "side": side}


def analogs(f: dict, k: int = 3) -> list[dict]:
    stats = {}
    for key in ANALOG_KEYS:
        past = _past(key)
        if len(past) >= 15 and np.std(past) > 0:
            stats[key] = (float(np.mean(past)), float(np.std(past, ddof=1)))
    out = []
    for e in EPISODES:
        if e.get("r120") is None or any(e.get(k) is None for k in ANALOG_NEED):
            continue
        d = [((f[key] - mu) / sd - (e[key] - mu) / sd) ** 2 for key, (mu, sd) in stats.items()
             if f.get(key) is not None and e.get(key) is not None]
        if len(d) >= ANALOG_MIN:
            out.append({"peak": e["peak"], "dist": round(math.sqrt(sum(d) / len(d)), 2), "type": classify(e),
                        "more": e.get("more"), "r60": e.get("r60"), "r120": e.get("r120")})
    return sorted(out, key=lambda r: r["dist"])[:k]


STATE_REF = Path(__file__).with_name("state_reference.json")
NOW_WEEKS = 4        # match the last 4 weekly states (steadier than one week)
NOW_EXCLUDE = 365    # never match the last year (it would match itself)
NOW_GAP = 26 * 7     # one pick per half year


def _load_state_ref() -> tuple[pd.DataFrame, list[str]] | None:
    try:
        doc = json.loads(STATE_REF.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cols = doc["columns"]
    f = pd.DataFrame({k: v for k, v in cols.items() if k != "date"}, index=pd.to_datetime(cols["date"]), dtype=float)
    return f, list(doc["features"])


def state_frame(px: pd.DataFrame, slow: dict) -> pd.DataFrame:
    """Daily market state with the reference's definitions (QQQ / SPY / IWM / SOXX stand in for the
    Nasdaq-100 / S&P 500 / Russell 2000 / SOX indices)."""
    q = px[INDEX]

    def ch(sym: str, n: int = 63) -> pd.Series:
        return (px[sym] / px[sym].shift(n) - 1) * 100 if sym in px else pd.Series(np.nan, index=px.index)

    f = pd.DataFrame(index=px.index)
    f["dd"] = (q / q.rolling(252, min_periods=200).max() - 1) * 100
    f["r63"], f["r252"] = ch(INDEX), ch(INDEX, 252)
    f["v200"] = (q / q.rolling(200, min_periods=200).mean() - 1) * 100
    f["rv20"] = q.pct_change().rolling(20).std() * math.sqrt(252) * 100
    f["vix"] = px["^VIX"] if "^VIX" in px else np.nan
    f["sox"], f["spx"], f["small"] = ch("SOXX") - f["r63"], ch("SPY") - f["r63"], ch("IWM") - ch("SPY")
    f["eqw"], f["gv"] = ch("RSP") - ch("SPY"), ch("IWF") - ch("IWD")
    f["dfn"] = (ch("XLP") + ch("XLU")) / 2 - ch("SPY")
    f["fin"], f["ene"] = ch("XLF") - ch("SPY"), ch("XLE") - ch("SPY")
    if all(s in px for s in SECTORS):
        ma = {s: px[s].rolling(50, min_periods=50).mean() for s in SECTORS}
        f["sec50"] = sum((px[s] > ma[s]).astype(float).where(ma[s].notna()) for s in SECTORS)
    else:
        f["sec50"] = np.nan
    f["d10"] = (px["^TNX"] - px["^TNX"].shift(63)) * 100 if "^TNX" in px else np.nan
    baa = _series(slow, "baa")
    if len(baa):
        b = pd.Series(baa.reindex(px.index.union(baa.index)).ffill().reindex(px.index).to_numpy(), index=px.index)
        f["cred"] = (b - b.shift(63)) * 100
    else:
        f["cred"] = np.nan
    f["usd"] = ch("DX-Y.NYB")
    return f


def now_like(px: pd.DataFrame, slow: dict, k: int = 3) -> list[dict]:
    """Past weeks whose last 4 weekly market states are closest to today's (z-scored distance)."""
    ref = _load_state_ref()
    if ref is None:
        return []
    R, feats = ref
    today = px.index[-1]
    weekly = state_frame(px, slow)[feats].groupby(px.index.to_period("W-FRI")).tail(1).iloc[-NOW_WEEKS:]
    if len(weekly) < NOW_WEEKS:
        return []
    pool = R[R.index <= today - pd.Timedelta(days=NOW_EXCLUDE)]
    mu, sd = pool[feats].mean(), pool[feats].std()
    Z, z = ((R[feats] - mu) / sd).to_numpy(), ((weekly - mu) / sd).to_numpy()
    n_pool = len(pool)
    cand = np.arange(NOW_WEEKS - 1, n_pool)
    D, C = np.zeros(len(cand)), np.zeros(len(cand))
    for lag in range(NOW_WEEKS):
        a, b = Z[cand - lag], z[NOW_WEEKS - 1 - lag]
        m = ~np.isnan(a) & ~np.isnan(b)
        D += np.where(m, (a - b) ** 2, 0).sum(1)
        C += m.sum(1)
    ok = C >= 12 * NOW_WEEKS
    if not ok.any():
        return []
    d = np.sqrt(D[ok] / C[ok])
    out: list[dict] = []
    for j, v in sorted(zip(cand[ok], d), key=lambda x: x[1]):
        day = R.index[j]
        if all(abs((day - pd.Timestamp(o["week"])).days) > NOW_GAP for o in out):
            row = R.iloc[j]
            out.append({"week": str(day.date()), "dist": round(float(v), 2),
                        **{h: (None if pd.isna(row[h]) else float(row[h])) for h in ("f20", "f60", "f120", "f250")}})
        if len(out) == k:
            break
    return out


def build_state(market: dict, slow: dict, session: str | None = None) -> dict | None:
    """Everything the card shows, JSON-serialisable.  None when the index history is missing."""
    px = _closes(market)
    if px is None:
        return None
    if session:
        px = px[px.index <= pd.Timestamp(session)]
    ep = find_episode(px[INDEX])
    state: dict[str, Any] = {"session": str(px.index[-1].date()), "index": INDEX, "active": bool(ep.get("active")),
                             "dd_now": round(ep["dd_now"], 1), "now_like": now_like(px, slow),
                             "stale": stale_inputs(slow, str(px.index[-1].date()))}
    if "peak" not in ep:
        return state
    peak, trig = ep["peak"], ep["trigger"]
    at, now = factors_at(px, peak, trig, slow), factors_at(px, peak, px.index[-1], slow)
    state.update({
        "peak": str(peak.date()), "trigger": str(trig.date()),
        "days_now": int(px.index.get_loc(px.index[-1]) - px.index.get_loc(peak)),
        "type": classify(at), "inv18": inverted_before(slow, peak),
        "factors": {k: {"v": None if at[k] is None else round(at[k], 2),
                        "now": None if now.get(k) is None else round(now[k], 2)} for k in FACTORS},
        "analogs": analogs(at),
        "asof": {k: (max(slow[k]) if slow.get(k) else None) for k in ("cape", "margin", "mmf", "baa")},
    })
    return state


# ---------------------------------------------------------------- rendering
def _num(v: float | None, key: str | None = None, unit: str | None = None, nd: int | None = None) -> str:
    if v is None:
        return "未取得"
    _, _, u, d = FACTORS[key] if key else ("", "", unit or "", nd or 0)
    u, d = (unit if unit is not None else u), (nd if nd is not None else d)
    s = f"{v:+.{d}f}" if (key in SIGNED if key else True) else f"{v:.{d}f}"
    return s.replace("-", "−") + u


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:+.0f}%".replace("-", "−")


def _md(day: str) -> str:
    t = pd.Timestamp(day)
    return f"{t.month}/{t.day}"


def _ym(day: str) -> str:
    t = pd.Timestamp(day)
    return f"{t.year}年{t.month}月"


def _median(vals: list[float]) -> float | None:
    return float(np.median(vals)) if vals else None


def type_stats(name: str) -> dict:
    same = [e for e in EPISODES if classify(e) == name and e.get("more") is not None]
    r120 = [e["r120"] for e in same if e.get("r120") is not None]
    return {"n": len(same), "more": _median([e["more"] for e in same]),
            "deep": sum(e["more"] <= -10 for e in same),
            "up120": None if not r120 else round(sum(v > 0 for v in r120) / len(r120) * 100),
            "r120": _median(r120)}


def recession_stats(inv: bool | None, cred_wide: bool | None) -> dict:
    known = [e for e in EPISODES if e.get("rec12") is not None and e.get("more") is not None]
    rec, non = [e for e in known if e["rec12"] == 1], [e for e in known if e["rec12"] == 0]
    out = {"rec_n": len(rec), "rec_more": _median([e["more"] for e in rec]),
           "non_n": len(non), "non_more": _median([e["more"] for e in non]), "same_n": None, "same_rec": None}
    if inv is not None and cred_wide is not None:
        same = [e for e in known if e.get("inv18") is not None and e.get("cred") is not None
                and bool(e["inv18"]) == inv and (e["cred"] >= 15) == cred_wide]
        out.update(same_n=len(same), same_rec=sum(e["rec12"] == 1 for e in same))
    return out


def heat_stats() -> dict:
    ok = [e for e in EPISODES if e.get("md_yoy") is not None and e.get("cape") is not None and e.get("more") is not None]
    both = [e for e in ok if e["md_yoy"] >= 20 and e["cape"] >= 30]
    md = [e for e in EPISODES if e.get("md_yoy") is not None and e.get("more") is not None]
    hi, lo = [e for e in md if e["md_yoy"] >= 20], [e for e in md if e["md_yoy"] < 20]
    cp = [e for e in EPISODES if e.get("cape") is not None and e.get("more") is not None]
    chi, clo = [e for e in cp if e["cape"] >= 30], [e for e in cp if e["cape"] < 30]
    share = lambda xs: None if not xs else round(sum(e["more"] <= -10 for e in xs) / len(xs) * 100)  # noqa: E731
    return {"both_n": len(both), "both_deep": sum(e["more"] <= -10 for e in both),
            "md_hi": share(hi), "md_lo": share(lo), "md_hi_n": len(hi), "md_lo_n": len(lo),
            "cape_hi": share(chi), "cape_lo": share(clo)}


def horizon_table(f: dict) -> list[dict]:
    rows = []
    for label, key, thr, strict, fragile in HORIZON_ROWS:
        hit = (lambda v: v > thr) if strict else (lambda v: v >= thr)
        cells = []
        for _, _, out in HORIZONS:
            xs = [e for e in EPISODES if e.get(key) is not None and e.get(out) is not None]
            cells.append((_median([e[out] for e in xs if hit(e[key])]), _median([e[out] for e in xs if not hit(e[key])])))
        v = (f.get(key) or {}).get("v")
        rows.append({"label": label, "now": None if v is None else bool(hit(v)), "cells": cells, "fragile": fragile})
    return rows


STYLE = (
    f'<style id="{STYLE_ID}">'
    '.da-card .da-type{font-size:17px;font-weight:800;line-height:1.4;margin:2px 0 4px;color:var(--ds-ink,#1c1b19)}'
    '.da-card .da-lead{font-size:13px;line-height:1.65;margin:0 0 8px;color:var(--ds-ink-2,#46443d)}'
    '.da-card .da-h{font-size:12.5px;font-weight:800;margin:12px 0 5px;color:var(--ds-ink,#1c1b19)}'
    '.da-card ul{margin:0 0 4px;padding-left:1.15em}'
    '.da-card li{font-size:12.5px;line-height:1.6;margin:2px 0;color:var(--ds-ink-2,#46443d)}'
    '.da-card li b{color:var(--ds-ink,#1c1b19)}'
    '.da-card .da-now{color:var(--ds-muted,#6b685e);font-size:11.5px;white-space:nowrap}'
    '.da-card .da-chk{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:4px 0 6px}'
    '.da-card .da-box{background:var(--ds-inset,#efede7);border:1px solid var(--ds-line,#dedbd2);border-radius:10px;padding:8px 9px;min-width:0}'
    '.da-card .da-box i{display:block;font-style:normal;font-size:11.5px;font-weight:700;color:var(--ds-muted,#6b685e);margin-bottom:3px}'
    '.da-card .da-box div{font-size:12px;line-height:1.55;color:var(--ds-ink-2,#46443d)}'
    '.da-card .da-on{color:var(--ds-down,#b3362c);font-weight:800}'
    '.da-card .da-off{color:var(--ds-up,#17703f);font-weight:800}'
    '.da-card .da-wrap{max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}'
    '.da-card table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}'
    '.da-card th,.da-card td{padding:4px 3px;border-bottom:1px solid var(--ds-line,#dedbd2);text-align:center;vertical-align:top;line-height:1.45}'
    '.da-card th{font-weight:700;color:var(--ds-muted,#6b685e)}'
    '.da-card .da-l td{text-align:left;border-bottom:0;padding-top:8px;font-weight:700;color:var(--ds-ink,#1c1b19)}'
    '.da-card td b{color:var(--ds-ink,#1c1b19)}'
    '.da-card th small,.da-card td small{display:block;color:var(--ds-muted,#6b685e);font-size:10.5px;font-weight:400}'
    '.da-card details{margin:8px 0 0}'
    '.da-card summary{font-size:12.5px;font-weight:800;cursor:pointer;color:var(--ds-accent,#2659ab);padding:3px 0}'
    '.da-card .da-end{display:none}'
    '.da-card .da-warn{font-size:12.5px;line-height:1.6;font-weight:700;color:var(--ds-warn,#8a5a12);background:#f7efd9;'
    'border:1px solid #e3d3a0;border-radius:10px;padding:7px 10px;margin:4px 0 8px}'
    '.da-card .da-like{background:var(--ds-inset,#efede7);border:1px solid var(--ds-line,#dedbd2);border-radius:10px;padding:8px 10px;margin:6px 0 2px}'
    '.da-card .da-like i{display:block;font-style:normal;font-size:11.5px;font-weight:700;color:var(--ds-muted,#6b685e)}'
    '.da-card .da-like b{font-size:18px;font-weight:800;color:var(--ds-ink,#1c1b19);margin-right:10px}'
    '.da-card .da-like span{font-size:12.5px;color:var(--ds-ink-2,#46443d)}'
    '@media(max-width:420px){.da-card .da-chk{grid-template-columns:minmax(0,1fr)}}'
    '</style>'
)


def _state_tag(state: dict) -> str:
    raw = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    return f'<script id="{STATE_ID}" type="application/json">{raw}</script>'


def _open(inner: str, title: str = "今回の下げの分解", en: str = "Decline Anatomy", key: str = "") -> str:
    return (f'<div class="card da-card" id="{CARD_ID}">'
            + fold.card("decline-anatomy", f'<h2>{title}<span class="h2en">{en}</span></h2>', key, inner)
            + '<span class="da-end"></span></div>')


def key_of(state: dict) -> str:
    """One line for the folded card."""
    like = "・".join(_ym(x["week"]) for x in (state.get("now_like") or [])[:3])
    like = f"今に近い時期：{like}" if like else ""
    if state.get("active") and "factors" in state:
        return "｜".join(x for x in (f'{state["type"]}', f'高値から{_num(state.get("dd_now"), unit="%", nd=1)}', like) if x)
    return like or f'調整局面ではない（高値から{_num(state.get("dd_now"), unit="%", nd=1)}）'


def stale_html(state: dict) -> str:
    rows = state.get("stale") or []
    if not rows:
        return ""
    parts = []
    for r in rows:
        age = "" if r["days"] is None else f'・{r["days"]}日前'
        parts.append(f'{html.escape(r["label"])}（最終 {r["last"] or "なし"}{age}）')
    items = "、".join(parts)
    return (f'<div class="da-warn">⚠ 更新が止まっているデータがあります：{items}。'
            'この項目を使う判定は古い値のままです。</div>')


def like_html(state: dict) -> str:
    like = state.get("now_like") or []
    if not like:
        return ""
    first, rest = like[0], like[1:]
    sub = "・".join(_ym(x["week"]) for x in rest)
    rows = "".join(f'<li><b>{_ym(x["week"])}</b>：その後 20日 {_pct(x["f20"])}・60日 {_pct(x["f60"])}・'
                   f'120日 {_pct(x["f120"])}・250日 {_pct(x["f250"])}</li>' for x in like)
    signs = {x["f120"] > 0 for x in like if x.get("f120") is not None}
    split = "近い時期どうしで、その後が割れています。" if len(signs) > 1 else ""
    return (f'<div class="da-like"><i>今の相場にいちばん近い時期</i><b>{_ym(first["week"])}</b>'
            + (f'<span>次点 {sub}</span>' if sub else "") + '</div>'
            '<details><summary>近い時期のその後</summary>'
            f'<ul>{rows}</ul><div class="sub">{split}直近4週の相場の状態（下落率・勢い・荒さ・VIX・何が買われ何が売られたか・金利・信用・ドル）を、'
            '1999年以降の毎週と比べて毎日自動で判定しています（直近1年は除外）。検証では、近い時期からその後を当てる方法は'
            '過去平均より当たりませんでした。今の相場の説明として見てください。</div></details>')


def card_html(state: dict) -> str:
    e = html.escape
    tag = _state_tag(state)
    warn, like = stale_html(state), like_html(state)
    if not state.get("active") or "factors" not in state:
        last = ""
        if state.get("peak"):
            last = f'直近の調整は{_ym(state["peak"])}の高値からの下げ（{e(state.get("type", ""))}）でした。'
        return _open(
            warn + like
            + f'<div class="da-lead">いまはNasdaq100（QQQ）の調整局面ではありません（高値から{_num(state.get("dd_now"), unit="%", nd=1)}）。'
            f'高値から−10%に達すると、その下げを要因に分解してここに表示します。{last}</div>'
            f'<div class="sub">{e(state.get("session", ""))} 終値時点。表示のみで、売買ルールは変えません。</div>{tag}',
            "今の相場に近い時期", "Market Look-alike", key_of(state))
    f, kind = state["factors"], state["type"]
    n_all = len(EPISODES)
    al = state.get("analogs") or []
    near_top = (f'<div class="da-lead">下げの中身がいちばん近い過去の下げ：<b>{_ym(al[0]["peak"])}</b>'
                + (f'（次点 {"・".join(_ym(a["peak"]) for a in al[1:])}）' if len(al) > 1 else "") + '</div>') if al else ""
    head = (f'<div class="da-type">{e(kind)}</div>'
            f'<div class="da-lead">{e(TYPES[kind])}Nasdaq100（QQQ）は{_md(state["peak"])}の高値から{_num(state["dd_now"], unit="%", nd=1)}'
            f'（{state["days_now"]}営業日目）。−10%に達した{_md(state["trigger"])}時点の中身を、1990年以降の同じ場面{n_all}回と比べています。</div>')
    # unusual items by category
    items, quiet = [], []
    for cat in CATEGORIES:
        rows = []
        for key, (c, label, _, _) in FACTORS.items():
            if c != cat:
                continue
            r = rank(key, f[key]["v"])
            if r and r["side"]:
                pos = (("最小" if r["lo"] == 1 else f'下から{r["lo"]}番目') if r["side"] == "low"
                       else ("最大" if r["hi"] == 1 else f'上から{r["hi"]}番目'))
                now = f[key]["now"]
                today = "" if now is None else f' <span class="da-now">今日 {_num(now, key)}</span>'
                rows.append(f'<li>{e(label)} <b>{_num(f[key]["v"], key)}</b>（過去{r["n"]}回で{pos}）{today}</li>')
        if rows:
            items.append(f'<li><b>{e(cat)}</b><ul>{"".join(rows)}</ul></li>')
        else:
            quiet.append(cat)
    unusual = ('<div class="da-h">いつもと違う点</div>'
               + (f'<ul>{"".join(items)}</ul>' if items else '<div class="da-lead">目立って平常から外れた項目はありません。</div>')
               + (f'<div class="sub">平常の範囲：{e("、".join(quiet))}</div>' if quiet else ""))
    # checks
    cred, md, cape = f["cred"]["v"], f["md_yoy"]["v"], f["cape"]["v"]
    inv = state.get("inv18")
    cred_wide = None if cred is None else cred >= 15
    yn = lambda flag, on, off: ('<span class="da-on">' + on + '</span>') if flag else ('<span class="da-off">' + off + '</span>')  # noqa: E731
    rs = recession_stats(inv, cred_wide)
    same = (f'今回と同じ組み合わせの過去{rs["same_n"]}回のうち、1年以内に景気後退が来たのは{rs["same_rec"]}回。'
            if rs["same_n"] else "")
    rec_box = (
        '<div class="da-box"><i>景気後退チェック</i><div>'
        f'逆イールドの経験（直前18か月）：{"未取得" if inv is None else yn(inv, "あり", "なし")}／'
        f'信用スプレッドの拡大：{"未取得" if cred_wide is None else yn(cred_wide, "あり", "なし")}（{_num(cred, "cred")}）。'
        f'1年以内に景気後退が来た{rs["rec_n"]}回は、その後の最大下落が中央値{_num(rs["rec_more"], unit="%", nd=1)}、'
        f'来なかった{rs["non_n"]}回は{_num(rs["non_more"], unit="%", nd=1)}。{same}</div></div>')
    hs = heat_stats()
    md_on, cape_on = (None if md is None else md >= 20), (None if cape is None else cape >= 30)
    both = (f'両方当てはまった過去{hs["both_n"]}回のうち{hs["both_deep"]}回が、さらに−10%以上下落。'
            if md_on and cape_on else
            f'信用買い残が+20%以上だった{hs["md_hi_n"]}回は{hs["md_hi"]}%がさらに−10%以上下落、+20%未満の{hs["md_lo_n"]}回は{hs["md_lo"]}%。')
    heat_box = (
        '<div class="da-box"><i>過熱チェック</i><div>'
        f'信用買い残の前年比 {_num(md, "md_yoy")}：{"未取得" if md_on is None else yn(md_on, "該当", "非該当")}／'
        f'CAPE {_num(cape, "cape")}：{"未取得" if cape_on is None else yn(cape_on, "該当", "非該当")}。{both}</div></div>')
    ts = type_stats(kind)
    same_type = (f'<div class="da-h">同じ型の過去{ts["n"]}回</div><ul>'
                 f'<li>その後の最大下落は中央値 <b>{_num(ts["more"], unit="%", nd=1)}</b>、さらに−10%以上下げたのは <b>{ts["deep"]}回</b></li>'
                 f'<li>120営業日後にプラスだったのは <b>{ts["up120"]}%</b>（中央値 {_pct(ts["r120"])}）</li></ul>') if ts["n"] else ""
    # horizons
    hrows = ""
    for row in horizon_table(f):
        mark = "未取得" if row["now"] is None else ("該当" if row["now"] else "非該当")
        cells = "".join(
            (f'<td><b>{_pct(a)}</b><small>他 {_pct(b)}</small></td>' if row["now"] else
             f'<td>{_pct(a)}<small>他 <b>{_pct(b)}</b></small></td>' if row["now"] is False else
             f'<td>{_pct(a)}<small>他 {_pct(b)}</small></td>')
            for a, b in row["cells"])
        star = "※" if row["fragile"] else ""
        hrows += (f'<tr class="da-l"><td colspan="{len(HORIZONS)}">{e(row["label"])}{star}　今回：{mark}</td></tr>'
                  f'<tr>{cells}</tr>')
    horizon = (
        '<details><summary>期間で変わる傾向（短期・中期・長期）</summary>'
        '<div class="da-wrap"><table><thead><tr>'
        + "".join(f'<th>{name}<small>{span}</small></th>' for name, span, _ in HORIZONS)
        + f'</tr></thead><tbody>{hrows}</tbody></table></div>'
        '<div class="sub">その後のNasdaq100の騰落率の中央値（営業日）。上段＝当てはまった回、「他」＝当てはまらなかった回。太字が今回の側。'
        '※は2000年前後の6回を除くと長期の差がほぼ消える項目です。</div></details>')
    # analogs
    if al:
        rows = "".join(f'<li><b>{_ym(a["peak"])}</b>（{e(a["type"])}）：その後の最大下落 {_num(a["more"], unit="%", nd=1)}、'
                       f'60営業日後 {_pct(a["r60"])}、120営業日後 {_pct(a["r120"])}</li>' for a in al)
        signs = {a["r120"] > 0 for a in al if a.get("r120") is not None}
        split = "近い年どうしで結果が割れています。" if len(signs) > 1 else ""
        near = (f'<details><summary>下げの中身が近い過去の下げ</summary><ul>{rows}</ul>'
                f'<div class="sub">{split}検証では、近い年からその後を当てる方法は、全{n_all}回の平均を使うより外れました。'
                '「どんな下げか」の説明として見てください。</div></details>')
    else:
        near = ""
    asof = state.get("asof") or {}
    stamp = "、".join(f'{name}は{_ym(asof[k])}' for k, name in (("margin", "信用買い残"), ("cape", "CAPE")) if asof.get(k))
    note = (f'<div class="sub">{e(state["session"])} 終値時点（{stamp}までの公表値）。予測ではなく、下げの中身の説明です。'
            '過去の集計は40回前後と少なく、偶然を含みます。過去比較はNasdaq100指数、今回の計算はQQQと各ETFです。'
            '表示のみで、売買ルールは変えません。</div>')
    return _open(warn + head + near_top + like + unusual + f'<div class="da-chk">{rec_box}{heat_box}</div>'
                 + same_type + horizon + near + note + tag, key=key_of(state))


CARD_RE = re.compile(rf'<div class="card da-card" id="{CARD_ID}">.*?<span class="da-end"></span></div>', re.S)
STATE_RE = re.compile(rf'<script id="{STATE_ID}" type="application/json">(.*?)</script>', re.S)
STYLE_RE = re.compile(rf'<style id="{STYLE_ID}">.*?</style>', re.S)
ANCHOR = '<div class="card ch-card"'


def apply(text: str, state: dict | None) -> str:
    """Insert or replace the card (before 前回からの変化 on the Market tab).  Idempotent."""
    if state is None:
        return text
    card = card_html(state)
    if CARD_RE.search(text):
        out = CARD_RE.sub(lambda _: card, text, count=1)
    else:
        at = text.find(ANCHOR)
        if at < 0:
            print("decline anatomy: anchor not found; card not inserted", flush=True)
            return text
        out = text[:at] + card + text[at:]
    out = STYLE_RE.sub("", out)
    out = out.replace("</head>", STYLE + "</head>", 1) if "</head>" in out else out
    return fold.ensure(out)


def embedded_state(text: str) -> dict | None:
    m = STATE_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1).replace("<\\/", "</"))
    except ValueError:
        return None


def _page_session(text: str) -> str | None:
    m = re.search(r'<meta\b[^>]*name="session-date"[^>]*content="([^"]+)"', text) or re.search(r'"session_date":\s*"(\d{4}-\d{2}-\d{2})"', text)
    return m.group(1) if m else None


def rerender(text: str, root: Path) -> str:
    """Display-only path: re-render the card from the state stored in the page; when the page has
    no card yet, start from the committed seed state if it belongs to the page's session."""
    state = embedded_state(text)
    if state is None:
        try:
            seed = json.loads((root / STATE_SEED).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return text
        try:
            manifest = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}
        if seed.get("session") != (manifest.get("session_date") or _page_session(text)):
            return text
        state = seed
    return apply(text, state)


def run(text: str, root: Path, session: str, getter=_get) -> str:
    """Refresh path: compute today's state from the refresh's market inputs and insert the card."""
    market = load_market(root)
    if market is None:
        print("decline anatomy: market inputs not found; keeping the page as is", flush=True)
        return rerender(text, root)
    slow = refresh_slow(load_slow(root), getter)
    try:
        if save_slow(root, slow, session):
            print("decline anatomy: saved newer public series to " + SLOW_SEED, flush=True)
    except OSError as exc:
        print(f"decline anatomy: could not save the public series ({exc!r})", flush=True)
    state = build_state(market, slow, session)
    if state is None:
        print("decline anatomy: index history incomplete; keeping the page as is", flush=True)
        return rerender(text, root)
    print(f"decline anatomy: active={state['active']} type={state.get('type')} dd={state['dd_now']} "
          f"like={[x['week'] for x in state.get('now_like') or []]}", flush=True)
    for r in state.get("stale") or []:  # GitHub Actions annotation; the morning check reports it too
        print(f"::warning title=decline anatomy::{r['label']} has not updated since {r['last']} ({r['days']} days)", flush=True)
    return apply(text, state)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--html", default="source-mc57.html")
    a = ap.parse_args()
    page = Path(a.root) / a.html
    page.write_text(rerender(page.read_text(encoding="utf-8"), Path(a.root)), encoding="utf-8")
