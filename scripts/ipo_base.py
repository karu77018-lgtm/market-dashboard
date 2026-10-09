"""IPOベース監視 (Setups tab): first bases of recent listings, watch only.

The swing rule cannot buy young stocks (RS189 and the 200-day trend need about a
year of history), so this card shows them separately.  It never feeds the 6
slots.  Definition = the local study of 2015-2026 (regime on, 237 trades, PF 1.63,
1.80 with same-amount adds; 52-week breakouts of seasoned stocks: PF 1.13):

* listed 15-504 sessions ago (data/listing-dates.json, extended with new listings)
* the post-listing high was set >= 15 sessions ago (a base of 3+ weeks)
* depth of the base (high -> lowest low since) 10-50%
* breakout: close above that high for the first time, volume >= 1.4x the prior
  50-day average (or all prior days when fewer)
* close >= $10 and 20-day average dollar volume >= $20M

Shown: breakouts of the last 5 sessions (still at or above the pivot -3%) and
bases waiting within 8% below the pivot.  Breakouts are frozen in
track-record/ipo-signals.json at first publication and followed with the same
execution as the track record (next open, -8% stop, same-amount adds at +10/+20%,
exit at the next open after a close below the 21-EMA of lows).
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CARD_ID = "ipo-base-watch"
MSEC_ID = "ipo-base-msec"
LISTINGS = Path("data/listing-dates.json")
LEDGER = Path("track-record/ipo-signals.json")
SCHEMA = "ipo-base-signals.1"
MIN_AGE, MAX_AGE, MIN_BASE = 15, 504, 15
DEPTH = (0.10, 0.50)
VOL_X, MIN_PX, MIN_DV = 1.4, 10.0, 20e6
RECENT, NEAR = 5, 0.08
STUDY = "2015〜2026年・地合いOK・237件：勝率30%・平均+3.3%・PF 1.63（買い増し込み1.80）。上場の古い銘柄の52週高値ブレイクはPF 1.13"


def load_listings(root: Path) -> dict[str, str]:
    try:
        return dict(json.loads((root / LISTINGS).read_text(encoding="utf-8")).get("dates") or {})
    except (OSError, ValueError):
        return {}


def update_listings(frame: pd.DataFrame, root: Path) -> int:
    """Add listings first seen inside the saved window (first bar well after its start)."""
    path = root / LISTINGS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"schema": "listing-dates.1", "dates": {}}
    dates = data.setdefault("dates", {})
    start = frame["date"].min()
    first = frame.groupby("ticker")["date"].min()
    new = {t: d.strftime("%Y-%m-%d") for t, d in first.items()
           if t not in dates and d > start + pd.Timedelta(days=40)}
    if new:
        dates.update(new)
        data["dates"] = dict(sorted(dates.items()))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    return len(new)


def _ticker_state(t: str, g: pd.DataFrame, listed: pd.Timestamp, session: pd.Timestamp) -> dict | None:
    g = g.sort_values("date")
    g = g[g["date"] >= listed]
    if g.empty or g["date"].iloc[-1] != session:
        return None
    h, l, c, v = (g[k].astype(float).to_numpy() for k in ("high", "low", "close", "volume"))
    n = len(g)
    # sessions since listing: bars when the whole history is in the window, else business days
    first = pd.Timestamp(g["date"].iloc[0])
    age = n - 1 if (first - listed).days <= 5 else len(pd.bdate_range(listed, session)) - 1
    if not (MIN_AGE <= age <= MAX_AGE) or n < MIN_AGE:
        return None
    dv20 = float(np.mean(c[-20:] * v[-20:]))
    if c[-1] < MIN_PX or dv20 < MIN_DV:
        return None
    out = {"t": t, "listed": listed.strftime("%Y-%m-%d"), "age": age, "close": c[-1], "dv20": dv20}
    # most recent breakout within RECENT sessions (same test as the study)
    for back in range(0, min(RECENT, n - MIN_BASE - 1)):
        i = n - 1 - back
        prior = h[:i]
        hi = float(prior.max())
        k = len(prior) - 1 - int(np.argmax(prior[::-1]))
        if not (c[i] > hi >= c[i - 1]) or i - k < MIN_BASE:
            continue
        depth = 1 - float(l[k:i].min()) / hi
        vavg = float(np.mean(v[max(0, i - 50):i]))
        if DEPTH[0] <= depth <= DEPTH[1] and vavg > 0 and v[i] >= VOL_X * vavg:
            if c[-1] < hi * 0.97:
                return None                        # already back inside the base
            out.update(kind="breakout", pivot=hi, depth=depth, base=i - k, back=back,
                       volx=v[i] / vavg, date=g["date"].iloc[i].strftime("%Y-%m-%d"), dist=c[-1] / hi - 1)
            return out
    hi = float(h.max())
    k = n - 1 - int(np.argmax(h[::-1]))
    base = n - 1 - k
    depth = 1 - float(l[k:].min()) / hi
    dist = c[-1] / hi - 1
    if base >= MIN_BASE and DEPTH[0] <= depth <= DEPTH[1] and -NEAR <= dist <= 0:
        out.update(kind="waiting", pivot=hi, depth=depth, base=base, dist=dist)
        return out
    return None


def scan(frame: pd.DataFrame, listings: dict[str, str], session: str) -> dict[str, list[dict]]:
    sess = pd.Timestamp(session)
    young = {}
    for t, d in listings.items():
        try:
            ld = pd.Timestamp(d)
        except (TypeError, ValueError):
            continue
        if (sess - ld).days <= MAX_AGE * 1.6:       # cheap prefilter; exact age below
            young[t] = ld
    rows = []
    sub = frame[frame["ticker"].isin(young)]
    for t, g in sub.groupby("ticker"):
        st = _ticker_state(t, g, young[t], sess)
        if st:
            rows.append(st)
    br = sorted((r for r in rows if r["kind"] == "breakout"), key=lambda r: (r["back"], -r["volx"]))
    wt = sorted((r for r in rows if r["kind"] == "waiting"), key=lambda r: (-r["dist"], r["t"]))
    return {"breakouts": br, "waiting": wt}


# ---------------------------------------------------------------- ledger
def load_ledger(root: Path) -> dict:
    try:
        data = json.loads((root / LEDGER).read_text(encoding="utf-8"))
        if data.get("schema") == SCHEMA:
            return data
    except (OSError, ValueError):
        pass
    return {"schema": SCHEMA, "signals": {}}


def record_and_advance(ledger: dict, res: dict, frame: pd.DataFrame, session: str, qqq: dict) -> dict:
    import track_record
    for r in res.get("breakouts", []):
        if r.get("back") == 0:
            key = f"{session}:{r['t']}"
            ledger["signals"].setdefault(key, {"ticker": r["t"], "session": session, "status": "約定待ち",
                                               "pivot": r["pivot"], "listed": r["listed"]})
    by = {t: g.set_index("date")[["open", "high", "low", "close"]] for t, g in
          frame[frame["ticker"].isin({s["ticker"] for s in ledger["signals"].values()})].groupby("ticker")}
    for key, st in ledger["signals"].items():
        track_record.advance(st, by.get(st["ticker"]), qqq)
    return ledger


def save_ledger(ledger: dict, root: Path) -> None:
    import track_record
    track_record.save(ledger, root / LEDGER)


def ledger_summary(ledger: dict) -> dict:
    import track_record
    ms = [track_record.metrics(s) for s in ledger.get("signals", {}).values()]
    done = [m for m in ms if m.get("closed") and "ret" in m]
    live = [m for m in ms if not m.get("closed") and "ret" in m]
    rets = [m["ret"] for m in done]
    gains, losses = sum(r for r in rets if r > 0), -sum(r for r in rets if r < 0)
    return {"signals": len(ms), "closed": len(done), "open": len(live),
            "win": (sum(r > 0 for r in rets) / len(rets)) if rets else None,
            "pf": (gains / losses) if losses > 0 else None, "avg": (sum(rets) / len(rets)) if rets else None}


# ---------------------------------------------------------------- display
def _pct(v: float | None, signed: bool = True) -> str:
    if v is None or not np.isfinite(v):
        return "—"
    s = f"{v:+.1%}" if signed else f"{v:.0%}"
    return s.replace("-", "−")


def card_html(res: dict, regime: dict | None, summary: dict | None) -> str:
    e = html.escape
    on = regime.get("on") if isinstance(regime, dict) else None
    reg = ('<span class="ipo-reg on">地合いOK</span>' if on is True else
           '<span class="ipo-reg off">地合い停止中（新規の対象外）</span>' if on is False else
           '<span class="ipo-reg off">地合い判定不可</span>')

    def row(r: dict) -> str:
        if r["kind"] == "breakout":
            when = "本日" if r["back"] == 0 else f"{r['back']}日前"
            tag = f'<span class="ipo-tag br">ブレイク {when}</span>'
            facts = f"出来高 {r['volx']:.1f}倍・ベース{r['base']}日・深さ{r['depth']:.0%}"
        else:
            tag = '<span class="ipo-tag wt">ブレイク待ち</span>'
            facts = f"ベース{r['base']}日・深さ{r['depth']:.0%}"
        return (f'<div class="ipo-row" data-tkone="{e(r["t"])}"><div class="ipo-main"><b>{e(r["t"])}</b>{tag}'
                f'<span class="ipo-px">${r["close"]:,.2f}</span></div>'
                f'<div class="ipo-sub">上場 {e(r["listed"][2:7].replace("-", "/"))}（{r["age"]}営業日）・'
                f'ピボット ${r["pivot"]:,.2f}（{_pct(r["dist"])}）・{facts}・売買代金 ${r["dv20"] / 1e6:,.0f}M</div></div>')

    br, wt = res.get("breakouts", []), res.get("waiting", [])
    tickers = ",".join(r["t"] for r in br + wt)
    body = "".join(row(r) for r in br) + "".join(row(r) for r in wt[:12])
    if not body:
        body = '<div class="empty">該当なし（上場2年以内でベースを作っている銘柄がない）</div>'
    more = f'<div class="ipo-more">ほかにブレイク待ち {len(wt) - 12}件</div>' if len(wt) > 12 else ""
    rec = ""
    if summary and summary.get("signals"):
        win = "—" if summary["win"] is None else f"{summary['win']:.0%}"
        pf = "—" if summary["pf"] is None else f"{summary['pf']:.2f}"
        rec = (f'<div class="ipo-rec">公開後の記録：シグナル{summary["signals"]}件（確定{summary["closed"]}・'
               f'保有中{summary["open"]}）・勝率{win}・PF {pf}・平均{_pct(summary["avg"])}</div>')
    copy = (f'<button class="cp" data-tk="{e(tickers)}" onclick="copyTk(event,this)">コピー '
            f'<span class="n">{len(br) + len(wt)}</span></button>') if tickers else ""
    return (
        f'<div class="card ds-merged" id="{CARD_ID}"><div class="hdr"><h2>IPOベース監視</h2>{copy}</div>'
        f'<div class="sub">上場2年以内の銘柄が、上場後の高値を3週間以上のベースから出来高を伴って抜けるところ。'
        f'今のルール（RS189・200日線）は上場1年未満を拾えないので別枠で監視。<b>通常スイング枠には入れない</b>。{reg}</div>'
        f'{body}{more}{rec}'
        f'<details class="cxpl"><summary>根拠と条件</summary><div class="cxpl-b">{e(STUDY)}。'
        '上場から15〜504営業日・上場後の高値から15日以上・深さ10〜50%・出来高が50日平均の1.4倍以上・株価$10以上・売買代金$20M以上。'
        '本日のブレイクは公開時点で記録し、翌営業日の始値・−8%損切り・+10%と+20%で同額買い増し・安値21EMA割れの翌始値で追跡。'
        '現存銘柄だけの検証なので、上場廃止した銘柄の分だけ実際より良く見えている可能性がある。</div></details></div>'
    )


STYLE = ('<style id="ipo-base-style">'
         f'#{CARD_ID} .ipo-row{{padding:8px 0;border-top:1px solid var(--ds-line,#e0ddd5)}}'
         f'#{CARD_ID} .ipo-row:first-of-type{{border-top:0}}'
         f'#{CARD_ID} .ipo-main{{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap}}'
         f'#{CARD_ID} .ipo-main b{{font-size:14px;letter-spacing:.02em}}'
         f'#{CARD_ID} .ipo-px{{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:700}}'
         f'#{CARD_ID} .ipo-sub{{font-size:11.5px;color:var(--ds-muted,#6b685e);line-height:1.55;margin-top:2px}}'
         f'#{CARD_ID} .ipo-tag{{font-size:10.5px;font-weight:800;border-radius:6px;padding:1px 6px;border:1px solid}}'
         f'#{CARD_ID} .ipo-tag.br{{background:#e2f0e6;color:#17683f;border-color:#b5d8c1}}'
         f'#{CARD_ID} .ipo-tag.wt{{background:#efede7;color:#46443d;border-color:#dedbd2}}'
         f'#{CARD_ID} .ipo-reg{{display:inline-block;margin-left:6px;font-size:10.5px;font-weight:800;border-radius:6px;padding:0 6px}}'
         f'#{CARD_ID} .ipo-reg.on{{background:#e2f0e6;color:#17683f}}#{CARD_ID} .ipo-reg.off{{background:#f6e1de;color:#a3322a}}'
         f'#{CARD_ID} .ipo-rec,#{CARD_ID} .ipo-more{{font-size:11.5px;color:var(--ds-ink-2,#46443d);margin-top:6px}}'
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
    return re.sub(r'<style id="ipo-base-style">.*?</style>', "", text, count=1, flags=re.S)


def apply(text: str, res: dict, regime: dict | None, summary: dict | None) -> str:
    """Insert (or replace) the IPO section right after 発火前 in Setups."""
    text = _remove_block(text)
    sec = text.find('<section id="t-today"')
    if sec < 0:
        return text
    end = text.find("</section>", sec)
    block = (f'<div class="msec ds-merged-head" id="{MSEC_ID}"><div class="msec-l">IPOベース（上場2年以内）'
             '<span class="msec-en">IPO Base</span></div><div class="msec-q">今のルールが拾えない若い銘柄の別枠。監視のみ</div></div>'
             + card_html(res, regime, summary))
    anchor = None
    for key in ("RSライン先行", "オプション配置", "支えへの接触", "リーダー監視", "リーダー母集団"):
        m = re.search(r'<div class="msec[^"]*"[^>]*><div class="msec-l">[^<]*' + key, text[sec:end])
        if m:
            anchor = sec + m.start()
            break
    pos = anchor if anchor is not None else end
    text = text[:pos] + block + text[pos:]
    return text.replace("</head>", STYLE + "</head>", 1)


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
        print(f"saved OHLCV for {session} unavailable; IPO watch left as published", flush=True)
        return 0
    market = next((p for p in (root / "data" / "market_inputs.json", root / "work" / "market-inputs-cache.json")
                   if p.is_file()), None)
    regime = regime_from_market(market, session) if market else None
    res = scan(frame, load_listings(root), session)
    text = apply(page.read_text(encoding="utf-8"), res, regime, ledger_summary(load_ledger(root)))
    page.write_text(renumber(text), encoding="utf-8")
    print(f"IPO watch: {len(res['breakouts'])} breakouts, {len(res['waiting'])} waiting", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
