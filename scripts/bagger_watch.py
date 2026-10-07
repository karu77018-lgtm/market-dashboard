"""大化け候補 (Setups tab): former leaders that pulled back deeply and are taking back their high.

Watch only, never added to the 6 slots.  Built from the 2016-2025 bagger study
(research/bagger-study.html): every US listing that tripled inside a calendar
year (338 cases, close >= $10 and 50-day dollar volume >= $20M at the low).

What the study found, in the order this card uses it:

* 84% had risen 50%+ in the year before, then fell a median 61% over ~4 months
  ("前の相場の主役が深く押した").  The rise restarted at a market low (72%;
  33% in normal years), on earnings, or on news.
* The first 52-week closing high after the low still had most of the move left
  (normal years: median +132% to the year's high).
* Among all fresh 52-week-high breakouts of liquid stocks (17,468), the ones
  after a deep base (>= 30% below the prior high) with RS >= 90 doubled within a
  year 28% of the time vs 5.6% for all breakouts.  Base tightness (VCP) and the
  trend template did not help.
* Fundamentals did not raise that hit rate, but the latest quarter's EPS being
  better than a year earlier (profit or smaller loss) cut the downside: median
  1-year return +10.5% vs -3.0% when EPS was worse (3 of 4 sub-periods).
* As a pre-breakout watch list (deep base, within 15% of the high, RS >= 80):
  ~10 names a week, 65% broke out within 60 sessions; those breakouts doubled
  21% of the time.  With a -25% trailing stop from the highest close the
  average trade was +16% (median -2%, 48% winners): a few large winners pay.
  Weak in 2019/2021/2022, strong after market lows (2020, 2023, 2025).

Shown (all on the session close):

* ブレイク済み: a fresh 52-week closing high (none in the prior 20 sessions) in
  the last 15 sessions, base depth >= 30%, RS >= 90, price >= $10, 50-day
  dollar volume >= $20M, and not yet 25% below its highest close since.
* 監視中: base depth >= 30%, close within 15% below the 252-session closing
  high (not above it), close >= 1.25x the base low, RS >= 80, same liquidity.

RS = 0.4*r63 + 0.2*r126 + 0.2*r189 + 0.2*r252, percentile among names with 50-day
dollar volume >= $5M.  EPS is the latest quarter filed with the SEC (10-Q/10-K
XBRL, Q4 = fiscal year minus nine months) against the same quarter a year
earlier; foreign filers and missing tags show データなし.

Today's breakouts are frozen in track-record/bagger-signals.json and followed
with the study's exit (signal close, -25% trailing stop on closes).
"""
from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

CARD_ID = "bagger-watch"
MSEC_ID = "bagger-watch-msec"
TITLE = "大化け候補"
LEDGER = Path("track-record/bagger-signals.json")
SCHEMA = "bagger-watch-signals.1"
CIK_MAP = Path(__file__).with_name("sec_cik.json")
SEC_CACHE = Path("work/sec-facts")
RESEARCH = "research/bagger-study.html"

MIN_PX, MIN_DV, RS_DV = 10.0, 20e6, 5e6
DEPTH = 0.30
BO_RS, WATCH_RS = 90, 80
NEAR = 0.15
LOW_UP = 1.25
LOOKBACK = 15
FRESH = 20
TRAIL = 0.25
MAX_HOLD = 504
MAX_FETCH = 60

STUDY = ("2016〜2025年に年内3倍になった338件の研究と、流動株の52週高値ブレイク17,468回の比較から。"
         "深い押し（30%以上）＋RS90以上のブレイクは1年以内に2倍になった割合が28%（全ブレイクは5.6%）。"
         "業績は確率を上げないが、直近四半期のEPSが前年同期より改善していると1年後の中央値が+10.5%（悪化は−3.0%）と下振れが小さい。"
         "監視リスト（深い押し・高値まで−15%以内・RS80以上）として使うと常時10銘柄前後、65%が60営業日以内にブレイクし、"
         "そのブレイクの21%が1年以内に2倍。高値から−25%のトレイルで売ると1回平均+16%（中央値−2%・勝率48%）で、少数の大勝ちが全体を支える形。"
         "2019・2021・2022年は弱く、相場の底明け（2020・2023・2025年）に強い。現存銘柄のみの検証")


# ---------------------------------------------------------------- price scan
def _rs(c: pd.DataFrame, dv: pd.DataFrame) -> pd.DataFrame:
    r = lambda n: c / c.shift(n) - 1
    raw = 0.4 * r(63) + 0.2 * r(126) + 0.2 * r(189) + 0.2 * r(252)
    return raw.where(dv >= RS_DV).rank(axis=1, pct=True) * 99


def _base(col: np.ndarray, k: int) -> tuple[float, float, int]:
    """(prior 252-session closing high, depth of the base since it, sessions since it) at bar k."""
    lo = max(0, k - 252)
    win = col[lo:k]
    if len(win) < 200 or not np.isfinite(win).any():
        return np.nan, np.nan, 0
    j = lo + int(np.nanargmax(win))
    hi = col[j]
    low = np.nanmin(col[j:k + 1])
    return float(hi), float(1 - low / hi), k - j


def scan(frame: pd.DataFrame, session: str) -> dict:
    from swing_screener import _pivot
    out = {"session": session, "rows": [], "today": [], "reason": None}
    p = _pivot(frame)
    c, v = p["close"], p["volume"]
    if len(c) < 260:
        out["reason"] = "history_short"
        return out
    dv = (c * v).rolling(50, min_periods=40).mean()
    rs = _rs(c, dv)
    hi = c.shift(1).rolling(252, min_periods=200).max()
    newhi = c > hi
    fresh = newhi & ~newhi.shift(1, fill_value=False).astype(float).rolling(FRESH, min_periods=1).max().astype(bool)
    n = len(c)
    last = c.iloc[-1]
    seen: set[str] = set()
    # breakouts of the last LOOKBACK sessions (newest first)
    for back in range(LOOKBACK):
        k = n - 1 - back
        ok = fresh.iloc[k] & (c.iloc[k] >= MIN_PX) & (dv.iloc[k] >= MIN_DV) & (rs.iloc[k] >= BO_RS)
        for t in ok[ok.fillna(False)].index:
            if t in seen:
                continue
            col = c[t].to_numpy(float)
            h, depth, base_days = _base(col, k)
            if not (depth >= DEPTH):
                continue
            after = pd.Series(col[k:]).dropna()
            peak = float(after.max())
            if back and float((after / after.cummax()).min()) < 1 - TRAIL:
                continue  # the trailing stop has already been hit
            seen.add(t)
            r = {"t": t, "kind": "breakout", "back": back, "signal_date": str(c.index[k].date()),
                 "signal_close": float(col[k]), "close": float(last[t]), "from_signal": float(last[t]) / col[k] - 1,
                 "prior_high": h, "depth": depth, "base_days": base_days, "rs": int(round(float(rs[t].iloc[k]))),
                 "day_chg": float(col[k] / col[k - 1] - 1), "peak": peak, "stop": peak * (1 - TRAIL),
                 "dv50": float(dv[t].iloc[-1])}
            out["rows"].append(r)
            if back == 0:
                out["today"].append(r)
    # watch: deep base, close within NEAR below the high
    k = n - 1
    pre = ((last >= MIN_PX) & (dv.iloc[k] >= MIN_DV) & (rs.iloc[k] >= WATCH_RS)
           & (last < hi.iloc[k]) & (last >= hi.iloc[k] * (1 - NEAR)))
    for t in pre[pre.fillna(False)].index:
        if t in seen:
            continue
        col = c[t].to_numpy(float)
        h, depth, base_days = _base(col, k)
        if not (depth >= DEPTH):
            continue
        low = h * (1 - depth)
        if col[k] < low * LOW_UP:
            continue
        out["rows"].append({"t": t, "kind": "watch", "back": None, "close": float(col[k]), "prior_high": h,
                            "off": float(1 - col[k] / h), "depth": depth, "base_days": base_days,
                            "rs": int(round(float(rs[t].iloc[k]))), "dv50": float(dv[t].iloc[-1])})
    return out


# ---------------------------------------------------------------- SEC EPS / revenue
REV = ["us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap:Revenues", "us-gaap:SalesRevenueNet",
       "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax", "us-gaap:RevenuesNetOfInterestExpense",
       "us-gaap:SalesRevenueGoodsNet", "us-gaap:SalesRevenueServicesNet"]
EPS = ["us-gaap:EarningsPerShareDiluted", "us-gaap:EarningsPerShareBasic", "us-gaap:EarningsPerShareBasicAndDiluted"]
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "10-KT"}


def _facts(t: str, root: Path, cik: dict) -> dict | None:
    """Trimmed SEC companyfacts (revenue and EPS tags), cached for the session day."""
    if t not in cik:
        return None
    cache = root / SEC_CACHE / f"{t}.json"
    today = time.strftime("%Y-%m-%d")
    try:
        blob = json.loads(cache.read_text(encoding="utf-8"))
        if blob.get("fetched") == today:
            return blob.get("facts")
    except (OSError, ValueError):
        pass
    ua = os.environ.get("SEC_USER_AGENT") or "market-dashboard/1.0 research"
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik[t]):010d}.json"
    facts = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=20) as fh:
                j = json.loads(fh.read())
            g = j.get("facts", {}).get("us-gaap", {})
            facts = {f"us-gaap:{k}": g[k]["units"] for k in {x.split(":")[1] for x in REV + EPS} if k in g}
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                facts = {}
                break
            time.sleep(1 + attempt)
        except Exception:
            time.sleep(1 + attempt)
    time.sleep(0.15)  # SEC fair-access: well under 10 requests a second
    if facts is None:
        return None
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"fetched": today, "facts": facts}), encoding="utf-8")
    except OSError:
        pass
    return facts


def _quarters(facts: dict, tags: list[str], unit_ok) -> pd.DataFrame | None:
    rows: dict = {}
    for pri, tag in enumerate(tags):
        for unit, lst in (facts.get(tag) or {}).items():
            if not unit_ok(unit):
                continue
            for f in lst:
                if "start" not in f or f.get("form") not in FORMS:
                    continue
                key = (f["start"], f["end"])
                cur = rows.get(key)
                # point in time: the first filing of each period; tag order breaks ties
                if cur is None or f["filed"] < cur[1] or (f["filed"] == cur[1] and pri < cur[2]):
                    rows[key] = (f["val"], f["filed"], pri)
    if not rows:
        return None
    df = pd.DataFrame([(s, e, v, fd) for (s, e), (v, fd, _) in rows.items()], columns=["start", "end", "val", "filed"])
    for col in ("start", "end", "filed"):
        df[col] = pd.to_datetime(df[col])
    df["dur"] = (df["end"] - df["start"]).dt.days
    q = df[(df.dur >= 80) & (df.dur <= 100)][["end", "val", "filed"]]
    fy, m9 = df[(df.dur >= 350) & (df.dur <= 380)], df[(df.dur >= 260) & (df.dur <= 285)]
    add = []
    for _, a in fy.iterrows():
        n9 = m9[m9.start == a.start]
        if len(n9) and 75 <= (a.end - n9.iloc[0].end).days <= 100:
            add.append((a.end, a.val - n9.iloc[0].val, a.filed))
    if add:
        q = pd.concat([q, pd.DataFrame(add, columns=["end", "val", "filed"])])
    return q.sort_values(["end", "filed"]).drop_duplicates("end", keep="first").reset_index(drop=True)


def _yoy(q: pd.DataFrame | None, day: pd.Timestamp) -> tuple[float, float] | None:
    """(latest quarter value, same quarter a year earlier) as known on ``day``."""
    if q is None:
        return None
    k = q[q.filed <= day].sort_values("end")
    if len(k) < 5:
        return None
    row = k.iloc[-1]
    if (day - row.end).days > 200:
        return None
    prev = k[(k.end - (row.end - pd.Timedelta(days=364))).abs() <= pd.Timedelta(days=20)]
    if not len(prev):
        return None
    return float(row.val), float(prev.iloc[-1].val)


def fundamentals(t: str, day: str, root: Path, cik: dict) -> dict:
    facts = _facts(t, root, cik)
    if not facts:
        return {"eps_state": "na"}
    d = pd.Timestamp(day)
    out: dict = {"eps_state": "na"}
    e = _yoy(_quarters(facts, EPS, lambda u: u.startswith("USD/")), d)
    if e:
        e0, ep = e
        out.update(eps0=e0, eps_prev=ep)
        out["eps_state"] = ("turn" if ep <= 0 < e0 else "better" if e0 > ep else "worse")
    r = _yoy(_quarters(facts, REV, lambda u: u == "USD"), d)
    if r and r[1] > 0:
        out["rev_g"] = r[0] / r[1] - 1
    return out


def enrich(res: dict, root: Path) -> dict:
    try:
        cik = json.loads(CIK_MAP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cik = {}
    rows = res.get("rows", [])
    rows.sort(key=lambda r: (r["kind"] != "breakout", r.get("back") or 0, r.get("off") or 0))
    for i, r in enumerate(rows):
        if i >= MAX_FETCH:
            r["eps_state"] = "na"
            continue
        day = r.get("signal_date") or res["session"]
        try:
            r.update(fundamentals(r["t"], day, root, cik))
        except Exception as exc:  # display-only
            print(f"bagger watch EPS skipped for {r['t']}: {exc!r}", flush=True)
            r["eps_state"] = "na"
    good = {"better": 0, "turn": 0, "na": 1, "worse": 2}
    rows.sort(key=lambda r: (r["kind"] != "breakout", good.get(r.get("eps_state"), 1),
                             r.get("back") or 0, r.get("off") or 0))
    return res


# ---------------------------------------------------------------- ledger
def load_ledger(root: Path) -> dict:
    try:
        data = json.loads((root / LEDGER).read_text(encoding="utf-8"))
        if data.get("schema") == SCHEMA:
            return data
    except (OSError, ValueError):
        pass
    return {"schema": SCHEMA, "exit": f"signal close, -{TRAIL:.0%} trailing stop on closes, max {MAX_HOLD} sessions",
            "signals": {}}


def record_and_advance(ledger: dict, res: dict, frame: pd.DataFrame, session: str) -> dict:
    for r in res.get("today", []):
        ledger["signals"].setdefault(f"{session}:{r['t']}", {
            "ticker": r["t"], "session": session, "entry": round(r["signal_close"], 4),
            "depth": round(r["depth"], 4), "rs": r["rs"], "eps_state": r.get("eps_state", "na"),
            "status": "保有中", "peak": round(r["signal_close"], 4)})
    names = {s["ticker"] for s in ledger["signals"].values() if s.get("status") == "保有中"}
    by = {t: g.set_index("date")["close"].sort_index() for t, g in frame[frame["ticker"].isin(names)].groupby("ticker")}
    for st in ledger["signals"].values():
        if st.get("status") != "保有中" or st["ticker"] not in by:
            continue
        s = by[st["ticker"]]
        s = s[s.index > pd.Timestamp(st["session"])].dropna()
        peak, entry = st["entry"], st["entry"]
        for i, (d, px) in enumerate(s.items()):
            peak = max(peak, float(px))
            if px < peak * (1 - TRAIL) or i + 1 >= MAX_HOLD:
                st.update(status="手仕舞い", exit_date=str(d.date()), exit=round(float(px), 4))
                break
        st["peak"] = round(peak, 4)
        last = st.get("exit") if st["status"] == "手仕舞い" else (float(s.iloc[-1]) if len(s) else entry)
        st["ret"] = round(last / entry - 1, 4)
    return ledger


def save_ledger(ledger: dict, root: Path) -> None:
    import track_record
    track_record.save(ledger, root / LEDGER)


def ledger_summary(ledger: dict) -> dict:
    sig = list(ledger.get("signals", {}).values())
    rets = [s["ret"] for s in sig if s.get("ret") is not None]
    return {"signals": len(sig), "closed": sum(s.get("status") == "手仕舞い" for s in sig),
            "open": sum(s.get("status") == "保有中" for s in sig),
            "avg": float(np.mean(rets)) if rets else None,
            "win": float(np.mean([r > 0 for r in rets])) if rets else None,
            "big": sum(r >= 1 for r in rets)}


# ---------------------------------------------------------------- display
def _pct(v: float | None, signed: bool = True) -> str:
    if v is None or not np.isfinite(v):
        return "—"
    return (f"{v:+.1%}" if signed else f"{v:.0%}").replace("-", "−")


EPS_LABEL = {"better": ("EPS改善", "ok"), "turn": ("黒字転換", "ok"), "worse": ("EPS悪化", "bad"), "na": ("決算データなし", "na")}


def _eps_text(r: dict) -> str:
    lab, cls = EPS_LABEL.get(r.get("eps_state", "na"), EPS_LABEL["na"])
    val = ""
    if r.get("eps0") is not None and r.get("eps_prev") is not None:
        val = f' {r["eps_prev"]:.2f}→{r["eps0"]:.2f}'.replace("-", "−")
    rev = f'・売上{_pct(r["rev_g"])}' if r.get("rev_g") is not None else ""
    return f'<span class="bgw-eps {cls}">{lab}</span><span class="bgw-ev">{html.escape(val)}{rev}</span>'


def card_html(res: dict, regime: dict | None, summary: dict | None) -> str:
    e = html.escape
    on = regime.get("on") if isinstance(regime, dict) else None
    reg = ('<span class="bgw-reg on">地合いOK</span>' if on is True else
           '<span class="bgw-reg off">地合い停止中（QQQが200日線の下）</span>' if on is False else
           '<span class="bgw-reg off">地合い判定不可</span>')
    rows = res.get("rows", [])
    bos = [r for r in rows if r["kind"] == "breakout"]
    watch = [r for r in rows if r["kind"] == "watch"][:15]

    def row(r: dict) -> str:
        if r["kind"] == "breakout":
            when = "本日ブレイク" if r["back"] == 0 else f"{r['back']}日前にブレイク"
            tag = f'<span class="bgw-tag bo">{when}</span>'
            extra = (f'ブレイク日{_pct(r["day_chg"])}・ブレイク後{_pct(r["from_signal"])}・'
                     f'−25%トレイル <b>${r["stop"]:,.2f}</b>（高値終値${r["peak"]:,.2f}）')
        else:
            tag = f'<span class="bgw-tag w">高値まで{_pct(-r["off"])}</span>'
            extra = f'52週の終値高値 ${r["prior_high"]:,.2f}'
        return (f'<div class="bgw-row" data-tkone="{e(r["t"])}"><div class="bgw-main"><b>{e(r["t"])}</b>{tag}'
                f'<span class="bgw-px">${r["close"]:,.2f}</span></div>'
                f'<div class="bgw-sub">{_eps_text(r)}</div>'
                f'<div class="bgw-sub">押し{_pct(-r["depth"])}（前の高値から{r["base_days"]}営業日）・RS {r["rs"]}・{extra}</div></div>')

    def group(title: str, items: list[dict], empty: str) -> str:
        body = "".join(row(r) for r in items) or f'<div class="empty">{empty}</div>'
        return f'<div class="bgw-g">{title}<span class="n">{len(items)}</span></div>{body}'

    rec = ""
    if summary and summary.get("signals"):
        win = "—" if summary["win"] is None else f"{summary['win']:.0%}"
        rec = (f'<div class="bgw-rec">公開後の記録：ブレイク{summary["signals"]}件（手仕舞い{summary["closed"]}・'
               f'保有中{summary["open"]}）・勝率{win}・平均{_pct(summary["avg"])}・+100%以上{summary["big"]}件</div>')
    tickers = ",".join(r["t"] for r in bos + watch)
    copy = (f'<button class="cp" data-tk="{e(tickers)}" onclick="copyTk(event,this)">コピー '
            f'<span class="n">{len(bos) + len(watch)}</span></button>') if tickers else ""
    return (
        f'<div class="card ds-merged" id="{CARD_ID}"><div class="hdr"><h2>{TITLE}</h2>{copy}</div>'
        '<div class="sub">前の相場で主役だった銘柄が30%以上押してから、52週高値を取り返しにきたもの。'
        f'<b>6枠には入れない</b>監視リスト。EPS改善を上に並べる。{reg}</div>'
        + group("ブレイク済み（直近15営業日）", bos, "該当なし（直近15営業日に深い押しからのブレイクはない）")
        + group("監視中（52週高値まで−15%以内）", watch, "該当なし")
        + rec
        + '<details class="cxpl"><summary>根拠と条件</summary><div class="cxpl-b">'
        f'{e(STUDY)}。<br/>'
        '<b>ブレイク済み</b>：52週の終値高値を更新（直前20営業日は更新なし）・前の高値からの押しが30%以上・RS90以上・'
        '株価$10以上・売買代金$20M以上。ブレイク後に高値終値から−25%を割ったものは外す。<br/>'
        '<b>監視中</b>：押し30%以上・52週の終値高値の−15%以内（まだ抜いていない）・押しの安値から+25%以上・RS80以上。<br/>'
        '<b>EPS</b>：SECに提出済みの直近四半期を前年同期と比較（Q4は年次−9か月）。外国企業などはデータなし。<br/>'
        '<b>手仕舞いの目安</b>：高値終値から−25%。21EMAや50日線割れだと大化けの1〜3割しか取れなかった。'
        '200日線から+100%以上離れたら分割利確を検討（その後3か月の中央値がマイナスに変わる）。<br/>'
        '本日のブレイクは公開時点で記録し、シグナル日の終値・終値ベースの−25%トレイルで追跡する。'
        f'<br/><a href="{RESEARCH}" target="_blank" rel="noopener">研究ページを開く</a></div></details></div>'
    )


STYLE = ('<style id="bagger-watch-style">'
         f'#{CARD_ID} .bgw-g{{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:800;'
         'color:var(--ds-ink-2,#46443d);margin:10px 0 2px;letter-spacing:.02em}'
         f'#{CARD_ID} .bgw-g .n{{font-size:11px;font-weight:700;color:var(--ds-muted,#6b685e)}}'
         f'#{CARD_ID} .bgw-row{{padding:8px 0;border-top:1px solid var(--ds-line,#e0ddd5);cursor:pointer}}'
         f'#{CARD_ID} .bgw-main{{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap}}'
         f'#{CARD_ID} .bgw-main b{{font-size:14px;letter-spacing:.02em}}'
         f'#{CARD_ID} .bgw-px{{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:700}}'
         f'#{CARD_ID} .bgw-sub{{font-size:11.5px;color:var(--ds-muted,#6b685e);line-height:1.55;margin-top:2px;'
         'overflow-wrap:anywhere}'
         f'#{CARD_ID} .bgw-sub b{{color:#a3322a}}'
         f'#{CARD_ID} .bgw-tag{{font-size:10.5px;font-weight:800;border-radius:6px;padding:1px 6px;border:1px solid}}'
         f'#{CARD_ID} .bgw-tag.bo{{background:#e2f0e6;color:#17683f;border-color:#b9dcc4}}'
         f'#{CARD_ID} .bgw-tag.w{{background:#e3ecf8;color:#1f4b8f;border-color:#bccfe9}}'
         f'#{CARD_ID} .bgw-eps{{font-size:10.5px;font-weight:800;border-radius:6px;padding:0 6px;margin-right:4px}}'
         f'#{CARD_ID} .bgw-eps.ok{{background:#e2f0e6;color:#17683f}}'
         f'#{CARD_ID} .bgw-eps.bad{{background:#f6e1de;color:#a3322a}}'
         f'#{CARD_ID} .bgw-eps.na{{background:#ecebe6;color:#55524a}}'
         f'#{CARD_ID} .bgw-ev{{font-variant-numeric:tabular-nums}}'
         f'#{CARD_ID} .bgw-reg{{display:inline-block;margin-left:6px;font-size:10.5px;font-weight:800;border-radius:6px;padding:0 6px}}'
         f'#{CARD_ID} .bgw-reg.on{{background:#e2f0e6;color:#17683f}}#{CARD_ID} .bgw-reg.off{{background:#f6e1de;color:#a3322a}}'
         f'#{CARD_ID} .bgw-rec{{font-size:11.5px;color:var(--ds-ink-2,#46443d);margin-top:8px}}'
         f'#{CARD_ID} .cxpl-b a{{color:#1f4b8f;font-weight:700}}'
         '</style>')


def _remove_block(text: str) -> str:
    for marker in (f'id="{MSEC_ID}"', f'id="{CARD_ID}"'):
        m = re.search(rf'<div[^>]*{re.escape(marker)}', text)
        if not m:
            continue
        depth = 0
        for tag in re.finditer(r"<(/?)div\b[^>]*>", text[m.start():]):
            depth += -1 if tag.group(1) else 1
            if depth == 0:
                text = text[:m.start()] + text[m.start() + tag.end():]
                break
    return re.sub(r'<style id="bagger-watch-style">.*?</style>', "", text, count=1, flags=re.S)


def apply(text: str, res: dict, regime: dict | None, summary: dict | None) -> str:
    """Insert (or replace) the section in Setups, before the option sections."""
    text = _remove_block(text)
    sec = text.find('<section id="t-today"')
    if sec < 0:
        return text
    end = text.find("</section>", sec)
    block = (f'<div class="msec ds-merged-head" id="{MSEC_ID}"><div class="msec-l">{TITLE}'
             '<span class="msec-en">Re-Leader Breakouts</span></div>'
             '<div class="msec-q">深い押しから52週高値を取り返す元主役株。2016〜2025年の大化け株研究から。監視のみ</div></div>'
             + card_html(res, regime, summary))
    anchor = None
    for key in ("オプション配置", "支えへの接触"):
        m = re.search(r'<div class="msec[^"]*"[^>]*><div class="msec-l">[^<]*' + key, text[sec:end])
        if m:
            anchor = sec + m.start()
            break
    pos = anchor if anchor is not None else end
    text = text[:pos] + block + text[pos:]
    return text.replace("</head>", STYLE + "</head>", 1)


def run(text: str, frame: pd.DataFrame, session: str, root: Path, regime: dict | None) -> str:
    """Daily refresh: scan, add EPS, record today's breakouts, advance the ledger, render."""
    res = enrich(scan(frame, session), root)
    led = record_and_advance(load_ledger(root), res, frame, session)
    save_ledger(led, root)
    print(f"bagger watch: {sum(r['kind'] == 'breakout' for r in res['rows'])} breakouts "
          f"({len(res['today'])} today), {sum(r['kind'] == 'watch' for r in res['rows'])} watch", flush=True)
    return apply(text, res, regime, ledger_summary(led))


def main() -> int:
    """Display workflows: re-render from the saved inputs; never records."""
    import argparse
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from rule_refresh import load_frame
    from setups_curate import renumber
    from swing_screener import regime_from_market
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--html", default="source-mc57.html")
    a = ap.parse_args()
    root = Path(a.root)
    page = root / a.html
    session = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))["session_date"]
    frame = load_frame(root / "work" / "ohlcv.csv", session)
    if frame is None:
        print(f"saved OHLCV for {session} unavailable; bagger watch left as published", flush=True)
        return 0
    market = next((p for p in (root / "data" / "market_inputs.json", root / "work" / "market-inputs-cache.json")
                   if p.is_file()), None)
    regime = regime_from_market(market, session) if market else None
    res = enrich(scan(frame, session), root)
    text = apply(page.read_text(encoding="utf-8"), res, regime, ledger_summary(load_ledger(root)))
    page.write_text(renumber(text), encoding="utf-8")
    print(f"bagger watch: {len(res['rows'])} shown", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
