"""RSライン先行 (Setups tab): leaders whose RS line makes a new high before the price.

The O'Neil-style "RS line leads price" condition, restricted to strong leaders
outside the rule's own selection.  Watch only, never added to the 6 slots.

Local study 2015-01 .. 2026-08 (current listings, QQQ above its 200-day line,
the rule's exits: -8% stop, same-amount adds at +10/+20%, close below the
21-EMA of lows), one trade at a time per ticker:

  trend template, any day                          PF 1.13
  trend template, price 3-8% below its high         PF 1.13
  this definition (526 trades, ~45 a year)          PF 2.04 (2.48 with adds)
     2015-2020 PF 3.34 / 2021-2026 PF 1.71 (with adds)
     price 2-5% below the high carries most of it; 5-8% below is weak (PF 1.13)

Definition (all on the session close):

* RS line = close / SPY close; today it is at its 63-session high for the first
  time in 20 sessions
* the price is 2-8% below its 252-session closing high (the price has not yet
  confirmed)
* trend template, price >= $10, 50-day dollar volume >= $20M, RS189 top 20%
* not in the rule's own selection (that one is already traded as 本命)

The 63-session window and the filters were chosen after trying about fifteen
variants (63/126/252 sessions all beat the baseline: PF 1.68-1.92), so the
numbers above are likely optimistic.  New signals are frozen in
track-record/rsline-signals.json at first publication and followed with the
track-record execution (next open, -8% stop, adds, 21-EMA-of-lows exit).

Shown: signals of the last 5 sessions that have not hit the stop, have not
closed below the 21-EMA of lows and are at most +5% above the signal close.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

CARD_ID = "rsline-lead"
MSEC_ID = "rsline-lead-msec"
LEDGER = Path("track-record/rsline-signals.json")
SCHEMA = "rsline-lead-signals.1"
WINDOW = 63
FRESH = 20
OFF = (0.02, 0.08)
MIN_RS189 = 80
LOOKBACK = 5
MAX_UP = 0.05
STOP = 0.08
STUDY = ("2015〜2026年・地合いOK・526件（年45件）：勝率37%・PF 2.04（買い増し込み2.48）。"
         "2015〜20年 3.34／2021〜26年 1.71。比較：トレンドテンプレートの銘柄をいつ買ってもPF 1.13、"
         "高値から−3〜8%の位置というだけでもPF 1.13")


def spy_close(root: Path) -> pd.Series | None:
    for p in (root / "data" / "market_inputs.json", root / "work" / "market-inputs-cache.json"):
        try:
            rows = json.loads(p.read_text(encoding="utf-8"))["series"]["SPY"]
        except Exception:
            continue
        s = pd.Series({pd.Timestamp(str(r["date"])[:10]): float(r["close"]) for r in rows
                       if r.get("date") and r.get("close") is not None})
        if len(s) > WINDOW:
            return s.sort_index()
    return None


def scan(frame: pd.DataFrame, spy: pd.Series | None, session: str) -> dict:
    """Signals of the last LOOKBACK sessions; today's are the ones to record."""
    from swing_screener import DV_PCT, RS189_PCT, _pct_rank, _pivot, _states
    out = {"session": session, "rows": [], "today": [], "reason": None}
    if spy is None:
        out["reason"] = "spy_missing"
        return out
    p = _pivot(frame)
    c, h, l, v = p["close"], p["high"], p["low"], p["volume"]
    if len(c) < 260:
        out["reason"] = "history_short"
        return out
    spy = spy.reindex(c.index).ffill()
    rsl = c.div(spy, axis=0)
    nh = rsl >= rsl.rolling(WINDOW, min_periods=WINDOW).max()
    prior = nh.shift(1, fill_value=False).astype(float).rolling(FRESH, min_periods=1).max().astype(bool)
    first = nh & ~prior
    off = 1 - c / c.rolling(252, min_periods=200).max()
    el21 = l.ewm(span=21, adjust=False).mean()
    dv20 = (c * v).rolling(20, min_periods=15).mean()
    state = _states(c, h, l, v)
    last = c.iloc[-1]
    for back in range(LOOKBACK):
        k = -1 - back
        s = state(k)
        liquid, tt = s["liquid"], s["tt"]
        selected = liquid & tt & (s["dv_pct"] >= DV_PCT) & (s["rs189_pct"] >= RS189_PCT)
        o = off.iloc[k]
        hit = first.iloc[k] & liquid & tt & ~selected & (s["rs189_pct"] >= MIN_RS189) \
            & (o > OFF[0]) & (o <= OFF[1])
        for t in hit[hit.fillna(False)].index:
            base = float(c[t].iloc[k])
            if back:
                after = slice(len(c) + k + 1, len(c))
                if (l[t].iloc[after] <= base * (1 - STOP)).any() or (c[t].iloc[after] < el21[t].iloc[after]).any():
                    continue
                if float(last[t]) > base * (1 + MAX_UP):
                    continue
            r = {"t": t, "back": back, "signal_date": str(c.index[k].date()), "signal_close": base,
                 "close": float(last[t]), "from_signal": float(last[t]) / base - 1, "off": float(o[t]),
                 "rs189": int(round(float(s["rs189_pct"][t]))), "dv20": float(dv20[t].iloc[-1])}
            out["rows"].append(r)
            if back == 0:
                out["today"].append(r)
    seen: set[str] = set()
    out["rows"] = [r for r in sorted(out["rows"], key=lambda r: (r["back"], r["off"]))
                   if not (r["t"] in seen or seen.add(r["t"]))]
    return out


# ---------------------------------------------------------------- ledger
def load_ledger(root: Path) -> dict:
    try:
        data = json.loads((root / LEDGER).read_text(encoding="utf-8"))
        if data.get("schema") == SCHEMA:
            return data
    except (OSError, ValueError):
        pass
    return {"schema": SCHEMA, "signals": {}}


def record_and_advance(ledger: dict, res: dict, frame: pd.DataFrame, session: str, qqq: dict,
                       regime_on: bool | None) -> dict:
    import track_record
    if regime_on is True:  # the study counted regime-on days only
        for r in res.get("today", []):
            ledger["signals"].setdefault(f"{session}:{r['t']}", {
                "ticker": r["t"], "session": session, "status": "約定待ち",
                "off": round(r["off"], 4), "rs189": r["rs189"]})
    names = {s["ticker"] for s in ledger["signals"].values()}
    by = {t: g.set_index("date")[["open", "high", "low", "close"]]
          for t, g in frame[frame["ticker"].isin(names)].groupby("ticker")}
    for st in ledger["signals"].values():
        track_record.advance(st, by.get(st["ticker"]), qqq)
    return ledger


def save_ledger(ledger: dict, root: Path) -> None:
    import track_record
    track_record.save(ledger, root / LEDGER)


def ledger_summary(ledger: dict) -> dict:
    import ipo_base
    return ipo_base.ledger_summary(ledger)


# ---------------------------------------------------------------- display
def _pct(v: float | None) -> str:
    if v is None or not np.isfinite(v):
        return "—"
    return f"{v:+.1%}".replace("-", "−")


def card_html(res: dict, regime: dict | None, summary: dict | None) -> str:
    e = html.escape
    on = regime.get("on") if isinstance(regime, dict) else None
    reg = ('<span class="rsl-reg on">地合いOK</span>' if on is True else
           '<span class="rsl-reg off">地合い停止中（新規の対象外）</span>' if on is False else
           '<span class="rsl-reg off">地合い判定不可</span>')
    rows = res.get("rows", [])

    def row(r: dict) -> str:
        when = "本日" if r["back"] == 0 else f"{r['back']}日前"
        moved = "" if r["back"] == 0 else f"・シグナル日の終値 ${r['signal_close']:,.2f}から{_pct(r['from_signal'])}"
        return (f'<div class="rsl-row" data-tkone="{e(r["t"])}"><div class="rsl-main"><b>{e(r["t"])}</b>'
                f'<span class="rsl-tag">RSライン高値 {when}</span><span class="rsl-px">${r["close"]:,.2f}</span></div>'
                f'<div class="rsl-sub">株価は52週高値の{_pct(-r["off"])}{"（強い位置）" if r["off"] <= 0.05 else ""}・RS189 {r["rs189"]}・'
                f'損切り −8% ${r["signal_close"] * (1 - STOP):,.2f}{moved}・売買代金 ${r["dv20"] / 1e6:,.0f}M</div></div>')

    if rows:
        body = "".join(row(r) for r in rows[:12])
    elif res.get("reason") == "spy_missing":
        body = '<div class="empty">SPYのデータが取れず判定できませんでした</div>'
    else:
        body = '<div class="empty">該当なし（直近5営業日にRSラインが先行した強い銘柄はない）</div>'
    rec = ""
    if summary and summary.get("signals"):
        win = "—" if summary["win"] is None else f"{summary['win']:.0%}"
        pf = "—" if summary["pf"] is None else f"{summary['pf']:.2f}"
        rec = (f'<div class="rsl-rec">公開後の記録：シグナル{summary["signals"]}件（確定{summary["closed"]}・'
               f'保有中{summary["open"]}）・勝率{win}・PF {pf}・平均{_pct(summary["avg"])}</div>')
    tickers = ",".join(r["t"] for r in rows)
    copy = (f'<button class="cp" data-tk="{e(tickers)}" onclick="copyTk(event,this)">コピー '
            f'<span class="n">{len(rows)}</span></button>') if tickers else ""
    return (
        f'<div class="card ds-merged" id="{CARD_ID}"><div class="hdr"><h2>RSライン先行</h2>{copy}</div>'
        '<div class="sub">市場（SPY）に対する強さの線（RSライン）が先に高値を更新し、株価はまだ高値の少し下にある強い銘柄。'
        f'本命（売買代金上位5%・RS189上位10%）の外から拾う。<b>通常スイング枠には入れない</b>。{reg}</div>'
        f'{body}{rec}'
        f'<details class="cxpl"><summary>根拠と条件</summary><div class="cxpl-b">{e(STUDY)}。'
        '株価が高値の−2〜−5%にあるもの（「強い位置」）が特に強く、−5〜−8%は弱い（PF 1.13）。'
        f'条件：RSライン（終値÷SPY）が{WINDOW}営業日の高値（{FRESH}営業日ぶり）・株価は52週の終値高値の−2〜−8%・'
        'トレンドテンプレート・RS189上位20%・株価$10以上・売買代金$20M以上・本命の選定外。'
        '直近5営業日のシグナルのうち、損切り・安値21EMA割れがなく、シグナル日の終値+5%以内のものを表示。'
        '本日のシグナルは公開時点で記録し、翌営業日の始値・−8%損切り・+10%と+20%で同額買い増し・安値21EMA割れの翌始値で追跡。'
        '63営業日の窓や絞り込みは15通りほど試して選んだもので（126日・252日でもPF 1.7〜1.9）、現存銘柄だけの検証でもあるため、'
        '実際より良く見えている可能性がある。</div></details></div>'
    )


STYLE = ('<style id="rsline-lead-style">'
         f'#{CARD_ID} .rsl-row{{padding:8px 0;border-top:1px solid var(--ds-line,#e0ddd5)}}'
         f'#{CARD_ID} .rsl-row:first-of-type{{border-top:0}}'
         f'#{CARD_ID} .rsl-main{{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap}}'
         f'#{CARD_ID} .rsl-main b{{font-size:14px;letter-spacing:.02em}}'
         f'#{CARD_ID} .rsl-px{{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:700}}'
         f'#{CARD_ID} .rsl-sub{{font-size:11.5px;color:var(--ds-muted,#6b685e);line-height:1.55;margin-top:2px}}'
         f'#{CARD_ID} .rsl-tag{{font-size:10.5px;font-weight:800;border-radius:6px;padding:1px 6px;border:1px solid;'
         'background:#e3ecf8;color:#1f4b8f;border-color:#bccfe9}'
         f'#{CARD_ID} .rsl-reg{{display:inline-block;margin-left:6px;font-size:10.5px;font-weight:800;border-radius:6px;padding:0 6px}}'
         f'#{CARD_ID} .rsl-reg.on{{background:#e2f0e6;color:#17683f}}#{CARD_ID} .rsl-reg.off{{background:#f6e1de;color:#a3322a}}'
         f'#{CARD_ID} .rsl-rec{{font-size:11.5px;color:var(--ds-ink-2,#46443d);margin-top:6px}}'
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
    return re.sub(r'<style id="rsline-lead-style">.*?</style>', "", text, count=1, flags=re.S)


def apply(text: str, res: dict, regime: dict | None, summary: dict | None) -> str:
    """Insert (or replace) the section right after the IPO base section in Setups."""
    text = _remove_block(text)
    sec = text.find('<section id="t-today"')
    if sec < 0:
        return text
    end = text.find("</section>", sec)
    block = (f'<div class="msec ds-merged-head" id="{MSEC_ID}"><div class="msec-l">RSライン先行'
             '<span class="msec-en">RS Line Leaders</span></div>'
             '<div class="msec-q">株価より先に市場に対する強さが高値を更新した、本命の外のリーダー。監視のみ</div></div>'
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
    """Daily refresh: scan, record today's signals, advance the ledger, render."""
    import track_record
    res = scan(frame, spy_close(root), session)
    led = record_and_advance(load_ledger(root), res, frame, session,
                             track_record.qqq_bars(root / "data" / "market_inputs.json"),
                             regime.get("on") if isinstance(regime, dict) else None)
    save_ledger(led, root)
    print(f"RS line leaders: {len(res['rows'])} shown ({len(res['today'])} today)", flush=True)
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
        print(f"saved OHLCV for {session} unavailable; RS line leaders left as published", flush=True)
        return 0
    market = next((p for p in (root / "data" / "market_inputs.json", root / "work" / "market-inputs-cache.json")
                   if p.is_file()), None)
    regime = regime_from_market(market, session) if market else None
    res = scan(frame, spy_close(root), session)
    text = apply(page.read_text(encoding="utf-8"), res, regime, ledger_summary(load_ledger(root)))
    page.write_text(renumber(text), encoding="utf-8")
    print(f"RS line leaders: {len(res['rows'])} shown", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
