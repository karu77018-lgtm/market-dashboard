"""底アラート: bottom confirmation after sharp market falls (display + ledger only).

Never changes an order, MC57, V38, Massive, FRED or publication logic.  Reads the
QQQ and ^VIX daily rows the refresh already saved (data/market_inputs.json).

Two levels, chosen by a local study of QQQ / VIX 2000-01 .. 2026-10 (bottoms = the
deepest point of each year with a fall of 8% or more, 25 of them, and the bottoms of
the ten 20%-plus falls from the 52-week high):

* 大 (VIX+2σ底確認, the Gold_Locks rule): the VIX daily high reaches +2σ of the
  log10 monthly VIX highs since 1990 (months before the current one), then the
  5-day WMA of VIX highs crosses below the 10-day WMA.  Re-armed once the VIX high
  is back under +1σ.  9 times since 2000, 67% within -10..+20 sessions of a bottom,
  QQQ +7.5% / +9.3% median 20 / 60 sessions later (all days: +1.5% / +3.8%), median
  further fall within 60 sessions -2.6% (all days -4.3%).
* 中 (急落の底候補): the same VIX crossunder on a day when either QQQ is 10% or more
  under its 52-week high and the VIX high touched +1σ within 10 sessions, or QQQ is
  8% or more under and VIX close / its 20-day mean reached 1.5 within 10 sessions.
  15-session cooldown.  40 times since 2000; caught 8 of the 10 large bottoms
  3-9 sessions late (missed 2022-11 and 2000-01), 40% within a bottom window,
  QQQ +3.3% / +8.1% median after 20 / 60 sessions, but a median further fall of
  -7.2% within 60 sessions (several in the 2022 bear market).

Small yearly dips (QQQ -8..-12%) are not detected: every tested condition there
(capitulation Z, RSI, VIX spikes) had forward returns no better than an ordinary day.
"""
from __future__ import annotations

import html
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

LEDGER = Path("track-record/bottom-alert.json")
SCHEMA = "bottom-alert.1"
CARD_ID = "bottom-alert-card"
RECENT = 10          # sessions an alert stays on the card
COOLDOWN = 15        # 中: no repeat within this many sessions
# log10 of the monthly VIX highs, 1990-01 .. 2026-09 (Yahoo ^VIX): count, sum, sum of squares
SEED_END = "2026-09"
SEED_N, SEED_SUM, SEED_SQ = 441, 601.1900209310744, 830.4693740899601


def _wma(x: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1, dtype=float)
    return x.rolling(n).apply(lambda a: float((a * w).sum() / w.sum()), raw=True)


def _rows(market: dict, symbol: str) -> pd.DataFrame:
    rows = (market.get("series") or {}).get(symbol) or []
    f = pd.DataFrame(rows)
    if f.empty:
        return f
    f["date"] = pd.to_datetime(f["date"].astype(str).str[:10])
    for c in ("open", "high", "low", "close"):
        if c in f:
            f[c] = pd.to_numeric(f[c], errors="coerce")
    return f.dropna(subset=["close"]).drop_duplicates("date", keep="last").set_index("date").sort_index()


def sigma_levels(vix_high: pd.Series) -> pd.DataFrame:
    """+1σ / +2σ VIX levels for each session: seed months plus complete months after it."""
    mh = np.log10(vix_high.dropna().resample("ME").max())
    mh = mh[mh.index.strftime("%Y-%m") > SEED_END]
    n, s, q = SEED_N, SEED_SUM, SEED_SQ
    by_month: dict[str, tuple[float, float]] = {}
    months = [(m.strftime("%Y-%m"), float(v)) for m, v in mh.items()]
    # level for a month uses every month before it
    cur = pd.Period(SEED_END, "M") + 1
    last = pd.Period(vix_high.index.max(), "M")
    vals = dict(months)
    while cur <= last:
        mu = s / n
        sd = math.sqrt(max(0.0, (q - n * mu * mu) / (n - 1)))
        by_month[str(cur)] = (10 ** (mu + sd), 10 ** (mu + 2 * sd))
        v = vals.get(str(cur))
        if v is not None and cur < last:
            n, s, q = n + 1, s + v, q + v * v
        cur += 1
    mu0 = SEED_SUM / SEED_N
    sd0 = math.sqrt((SEED_SQ - SEED_N * mu0 * mu0) / (SEED_N - 1))
    seed = (10 ** (mu0 + sd0), 10 ** (mu0 + 2 * sd0))   # months up to the seed: its own levels
    idx = vix_high.index
    keys = idx.strftime("%Y-%m")
    l1 = [by_month.get(k, seed)[0] for k in keys]
    l2 = [by_month.get(k, seed)[1] for k in keys]
    return pd.DataFrame({"l1": l1, "l2": l2}, index=idx)


def compute(market: dict) -> pd.DataFrame | None:
    """Per-session readings and the two alerts, or None when QQQ / VIX are missing."""
    q, v = _rows(market, "QQQ"), _rows(market, "^VIX")
    if q.empty or v.empty or "high" not in v:
        return None
    idx = q.index
    vh = v["high"].reindex(idx).ffill()
    vc = v["close"].reindex(idx).ffill()
    lv = sigma_levels(v["high"]).reindex(idx).ffill()
    w5, w10 = _wma(vh, 5), _wma(vh, 10)
    cross = (w5 < w10) & (w5.shift(1) >= w10.shift(1))
    d52 = q["close"] / q["close"].rolling(252, min_periods=1).max() - 1
    vmax10 = vh.rolling(10).max()
    vrel = vc / vc.rolling(20).mean()
    vrel10 = vrel.rolling(10).max()
    mid_raw = cross & (((d52 <= -0.10) & (vmax10 >= lv["l1"])) | ((d52 <= -0.08) & (vrel10 >= 1.5)))
    mid = pd.Series(False, index=idx)
    big = pd.Series(False, index=idx)
    last, active, armed = -10 ** 6, False, True
    for i, d in enumerate(idx):
        if bool(mid_raw.iloc[i]) and i - last > COOLDOWN:
            mid.iloc[i], last = True, i
        h, l1, l2 = vh.iloc[i], lv["l1"].iloc[i], lv["l2"].iloc[i]
        if any(isinstance(x, float) and math.isnan(x) for x in (h, l1, l2)):
            continue
        if not active and armed and h >= l2:
            active = True
        if active and bool(cross.iloc[i]):
            big.iloc[i], active, armed = True, False, False
        if not armed and h < l1:
            armed = True
    return pd.DataFrame({"d52": d52, "vix_high": vh, "vix_rel10": vrel10, "vmax10": vmax10,
                         "l1": lv["l1"], "l2": lv["l2"], "cross": cross, "mid": mid, "big": big}, index=idx)


# ---------------------------------------------------------------- ledger

def new_ledger() -> dict[str, Any]:
    return {"schema": SCHEMA, "days": {}, "last_day": None}


def load(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict) and obj.get("schema") == SCHEMA:
            return obj
    except Exception:
        pass
    return new_ledger()


def save(ledger: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as h:
        json.dump(ledger, h, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        h.write("\n")
    os.replace(tmp, path)


def _r(x: Any, nd: int = 4) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if math.isfinite(v) else None


def update(ledger: dict, f: pd.DataFrame, session: str, keep_from: str | None = None) -> dict:
    """Record sessions after ledger['last_day'] up to ``session`` (frozen once written)."""
    dates = [d.strftime("%Y-%m-%d") for d in f.index]
    if session not in dates:
        return ledger
    last = ledger.get("last_day")
    if last and last >= session:
        return ledger
    first = keep_from or (dates[max(0, len(dates) - 30)] if not last else None)
    for d, row in f.loc[: pd.Timestamp(session)].iterrows():
        k = d.strftime("%Y-%m-%d")
        if (last and k <= last) or (first and k < first):
            continue
        ledger["days"][k] = {"d52": _r(row["d52"]), "vix_high": _r(row["vix_high"], 2),
                             "vix_rel10": _r(row["vix_rel10"], 3), "vmax10": _r(row["vmax10"], 2),
                             "l1": _r(row["l1"], 2), "l2": _r(row["l2"], 2),
                             "mid": bool(row["mid"]), "big": bool(row["big"])}
    ledger["last_day"] = session
    return ledger


def update_ledger(root: Path, session: str) -> dict:
    path = root / LEDGER
    ledger = load(path)
    try:
        market = json.loads((root / "data" / "market_inputs.json").read_text(encoding="utf-8"))
        f = compute(market)
        if f is not None:
            ledger = update(ledger, f, session)
            save(ledger, path)
        else:
            print("bottom alert: QQQ / VIX missing; keeping the last recorded day", flush=True)
    except Exception as exc:  # display + ledger only
        print(f"bottom alert update skipped: {exc!r}", flush=True)
    return ledger


# ---------------------------------------------------------------- display

def _md(d: str) -> str:
    return d[5:].replace("-", "/")


def card_html(ledger: dict | None) -> str:
    e = html.escape
    days = sorted((ledger or {}).get("days", {}))
    if not days:
        return ""
    recent = days[-RECENT:]
    rec = ledger["days"][days[-1]]
    big = [d for d in recent if ledger["days"][d].get("big")]
    mid = [d for d in recent if ledger["days"][d].get("mid")]
    d52, vh, l1, l2, vr = rec.get("d52"), rec.get("vix_high"), rec.get("l1"), rec.get("l2"), rec.get("vix_rel10")
    if big:
        cls, word = "on", f"大型急落の底確認（{_md(big[-1])}）"
        msg = ('VIXが+2σまで跳ねたあと反落。2000年以降9回、底の近く（−10〜+20営業日）67%、'
               'QQQの60営業日後は中央値+9.3%（普段+3.8%）、その後の追加下落は中央値−2.6%。')
    elif mid:
        cls, word = "warn", f"急落の底候補（{_md(mid[-1])}）"
        msg = ('急落のあとVIXが反落。2000年以降40回、20%超の大型急落10回のうち8回を底の3〜9営業日後に検出。'
               'ただし底の近くは40%で、2022年のような下げ相場では空振りが続いた。60営業日後のQQQは中央値+8.1%（普段+3.8%）、'
               'その前にさらに中央値−7.2%下げることがある。')
    else:
        watching = (d52 is not None and d52 <= -0.08) or (vh is not None and l1 is not None and vh >= l1)
        cls, word = ("watch", "監視中") if watching else ("", "なし")
        msg = ""
    reading = (f'QQQ 52週高値から <b>{d52 * 100:+.1f}%</b>（中は−8〜−10%以下）・VIX高値 <b>{vh:.1f}</b>'
               f'（+1σ {l1:.1f}／+2σ {l2:.1f}）・VIX急騰度 <b>{vr:.2f}倍</b>（中は1.5倍）'
               if None not in (d52, vh, l1, l2, vr) else "入力がそろっていません")
    return (f'<div class="bta-card bta-{cls or "none"}" id="{CARD_ID}" data-day="{e(days[-1])}">'
            f'<div class="bta-top"><span class="bta-h">底アラート</span><span class="bta-m">{e(word)}</span>'
            f'<span class="bta-d">{_md(days[-1])} 終値</span></div>'
            + (f'<div class="bta-msg">{msg}</div>' if msg else "")
            + f'<div class="bta-sub">{reading.replace("+-", "−").replace("-", "−")}</div>'
            '<details class="bta-more"><summary>判定のしかた</summary><div class="bta-sub">'
            '<b>大</b>：VIXの日中高値が+2σ（1990年以降の月間高値のlog、前月まで）に届いたあと、VIX高値の5日WMAが10日WMAを下抜けた日。+1σ割れで再待機。<br/>'
            '<b>中</b>：VIX高値の5日WMAが10日WMAを下抜けた日に、①QQQが52週高値から−10%以下かつ10日内にVIX高値が+1σ、'
            'または②QQQが−8%以下かつ10日内にVIXが20日平均の1.5倍。15営業日は再表示しない。<br/>'
            '年ごとの小さな押し（QQQ−8〜−12%）は、投げ売りZ値・RSI・VIX急騰のどれでも普段と差が出ず判定できない。'
            '表示だけで売買ルールは変えない（底ではTQQQルールの緊急解除・①早期再エントリーが本来の戻り方）。</div></details></div>')


STYLE = ('<style id="bottom-alert-style">.bta-card{border-radius:12px;padding:8px 14px;margin:8px 0;border:1px solid #d7d3c7;'
         'background:#f7f6f1}.bta-card.bta-on{background:rgba(34,197,94,.08);border-color:rgba(34,197,94,.45)}'
         '.bta-card.bta-warn,.bta-card.bta-watch{background:#f3ecd6;border-color:#e0cf98}'
         '.bta-top{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px}.bta-h{font-weight:800;font-size:14px;color:#1b1a18}'
         '.bta-m{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;background:#fff;border:1px solid #d7d3c7;color:#565243}'
         '.bta-d{font-size:11px;color:#8a877c;margin-left:auto}.bta-msg{font-size:12px;color:#3f3d35;line-height:1.6;margin-top:6px}'
         '.bta-sub{font-size:11.5px;color:#565243;line-height:1.6;margin-top:4px}.bta-more summary{font-size:11.5px;color:#467ed6;cursor:pointer}'
         '.bta-more{margin-top:4px}</style>')


def apply(text: str, ledger: dict | None, after_id: str = "tqqq-rule-card") -> str:
    """Place the card right after the TQQQ card (replacing an existing one)."""
    card = card_html(ledger)
    text = _remove(text, CARD_ID)
    text = re.sub(r'<style id="bottom-alert-style">.*?</style>', "", text, count=1, flags=re.S)
    if not card:
        return text
    m = re.search(rf'<div[^>]*\bid="{after_id}"', text)
    if not m:
        return text
    end = _div_end(text, m.start())
    if end is None:
        return text
    text = text[:end] + card + text[end:]
    return text.replace("</head>", STYLE + "</head>", 1)


def _div_end(text: str, pos: int) -> int | None:
    depth = 0
    for tag in re.finditer(r"<(/?)div\b[^>]*>", text[pos:]):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return pos + tag.end()
    return None


def _remove(text: str, cid: str) -> str:
    m = re.search(rf'<div[^>]*\bid="{cid}"', text)
    if not m:
        return text
    end = _div_end(text, m.start())
    return text if end is None else text[:m.start()] + text[end:]
