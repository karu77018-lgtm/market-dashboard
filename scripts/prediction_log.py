"""予測の答え合わせ (display only): every probability the added cards state is written down once, the day it is
first shown, and checked against what happened.  This is the only out-of-sample record of those numbers.

Recorded (fixed at the first refresh that shows them):
- up5 / up10: 局面チェック's chance that a QQQ bounce off the low is a real bottom.
  Outcome: back within 2% of the 252-session closing high (○) before a close below the low (×).
- down5: the chance that the S&P 500 (SPY) goes on from -5% to -10%.  Outcome: -10% (○) before back within 2% (×).
- ftd: the FTD card's chance that a follow-through day is a fake.  Outcome: a close below the FTD-day low within
  25 sessions (○ = fake) or not (×).
The log is committed (seed/prediction-log.json) by the refresh, so it survives the two-year price download.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pandas as pd

import decline_anatomy as da
import fold

LOG = "seed/prediction-log.json"
CARD_ID = "prediction-log"
STATE_ID = "prediction-log-state"
STYLE_ID = "prediction-log-style"
SHOW = 12
KINDS = {"up5": "QQQの戻り（安値から+5%）が本物の底になる", "up10": "QQQの戻り（安値から+10%）が本物の底になる",
         "down5": "S&P500が−5%から−10%まで下げる", "ftd": "FTDが騙しになる"}


def load(root: Path) -> dict:
    try:
        log = json.loads((root / LOG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log = {}
    log.setdefault("schema", "prediction-log.1")
    log.setdefault("entries", [])
    return log


def save(root: Path, log: dict) -> bool:
    path = root / LOG
    text = json.dumps(log, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def candidates(phase: dict | None, ftd: dict | None, session: str) -> list[dict]:
    """Predictions the page states on this session."""
    import phase_check as pc
    import ftd_check as fc
    out = []
    if phase:
        q = phase.get("qqq") or {}
        for kind in ("up5", "up10"):
            r = q.get(kind) if q.get("in_decline") else None
            if r:
                n, ok, basis = pc.rate_of(r, kind)
                out.append({"id": f"{kind}-QQQ-{r['date']}", "kind": kind, "sym": "QQQ", "event": r["date"],
                            "prob": pc._pct(n, ok), "basis": basis, "low": q.get("low_close")})
        ev = (phase.get("spy") or {}).get("event") or {}
        if ev.get("status") == "open":
            k = "hi" if ev.get("vix") is not None and ev["vix"] >= pc.VIX_CUT else "lo"
            n, hit = pc.REF_DOWN[k][:2]
            out.append({"id": f"down5-SPY-{ev['date']}", "kind": "down5", "sym": "SPY", "event": ev["date"],
                        "prob": pc._pct(n, hit), "basis": f"VIX {ev.get('vix')}"})
    if ftd:
        for row in ftd.get("rows", []):
            r = row.get("ftd")
            if r and not r.get("broken") and r["age"] < fc.WINDOW:
                p, basis = fc.odds(r)
                if p is not None:
                    out.append({"id": f"ftd-{row['sym']}-{r['date']}", "kind": "ftd", "sym": row["sym"], "event": r["date"],
                                "prob": int(p), "basis": basis or f"Day{r['day']}", "low": r["low"]})
    for c in out:
        c.update(recorded=session, outcome=None, resolved=None)
    return out


def _closes(market: dict, sym: str) -> pd.Series | None:
    px = da._closes(market)
    return None if px is None or sym not in px else px[sym].dropna()


def resolve(entries: list[dict], market: dict | None) -> None:
    if not market:
        return
    cache: dict[str, pd.Series | None] = {}
    for e in entries:
        if e.get("outcome") is not None:
            continue
        s = cache.setdefault(e["sym"], _closes(market, e["sym"]))
        if s is None or s.empty:
            continue
        dd = s / s.rolling(252, min_periods=200).max() - 1
        after = s[s.index > pd.Timestamp(e["event"])]
        res = None
        if e["kind"] in ("up5", "up10"):
            for d, c in after.items():
                if e.get("low") is not None and c < e["low"]:
                    res = (0, d)
                    break
                if dd.get(d, -1) >= -0.02:
                    res = (1, d)
                    break
        elif e["kind"] == "down5":
            for d in after.index:
                if dd[d] <= -0.10:
                    res = (1, d)
                    break
                if dd[d] >= -0.02:
                    res = (0, d)
                    break
        elif e["kind"] == "ftd":
            win = after.iloc[:25]
            broke = win[win < e["low"]] if e.get("low") is not None else win.iloc[:0]
            if len(broke):
                res = (1, broke.index[0])
            elif len(win) >= 25:
                res = (0, win.index[-1])
        if res:
            e["outcome"], e["resolved"] = res[0], str(res[1].date())


def update(log: dict, phase: dict | None, ftd: dict | None, session: str, market: dict | None) -> dict:
    have = {e["id"] for e in log["entries"]}
    for c in candidates(phase, ftd, session):
        if c["id"] not in have:     # fixed the first time it is shown
            log["entries"].append(c)
    resolve(log["entries"], market)
    log["entries"].sort(key=lambda e: (e["recorded"], e["event"], e["id"]))
    log["updated"] = session
    return log


# ---------------------------------------------------------------- rendering
def _md(day: str | None) -> str:
    if not day:
        return ""
    t = pd.Timestamp(day)
    return f"{t.month}/{t.day}"


def summary(log: dict) -> dict:
    done = [e for e in log["entries"] if e.get("outcome") is not None]
    n = len(done)
    return {"n": n, "open": len(log["entries"]) - n,
            "pred": round(sum(e["prob"] for e in done) / n) if n else None,
            "hit": round(sum(e["outcome"] for e in done) / n * 100) if n else None,
            "brier": round(sum((e["prob"] / 100 - e["outcome"]) ** 2 for e in done) / n, 3) if n else None}


def card_html(log: dict) -> str:
    sm = summary(log)
    rows = ""
    for e in list(reversed(log["entries"]))[:SHOW]:
        if e.get("outcome") is None:
            res = '<span class="pl-o">結果待ち</span>'
        else:
            res = (f'<span class="pl-y">○ 起きた</span>' if e["outcome"] else '<span class="pl-n">× 起きず</span>') \
                + f'<small>{_md(e["resolved"])}</small>'
        rows += (f'<tr><td>{_md(e["event"])}<small>{html.escape(e["sym"])}</small></td>'
                 f'<td>{html.escape(KINDS[e["kind"]])}<small>{html.escape(str(e.get("basis") or ""))}</small></td>'
                 f'<td><b>{e["prob"]}%</b></td><td>{res}</td></tr>')
    if sm["n"] >= 1:
        head = (f'解決済み{sm["n"]}件：予測した確率の平均{sm["pred"]}%に対し、実際にそうなったのは{sm["hit"]}%'
                f'（判定待ち{sm["open"]}件）。')
        if sm["n"] < 20:
            head += "まだ件数が少なく、ずれは偶然の範囲です。20件を超えたら較正（確率どおりに当たっているか）を見ます。"
    else:
        head = f'記録した予測{len(log["entries"])}件、まだ結果の出たものはありません。'
    first = log["entries"][0]["recorded"] if log["entries"] else ""
    body = (f'<div class="pl-p">{head}</div>'
            + (f'<table class="pl-t"><tr><th>日付</th><th>予測</th><th>確率</th><th>結果</th></tr>{rows}</table>' if rows else "")
            + '<div class="pl-p pl-mut">サイトに出た確率を、初めて表示された日の値のまま記録し、結果が出たら自動で照合します。'
              f'過去の検証とは別の、実際の答え合わせです（記録開始 {html.escape(first)}）。表示のみ。</div>')
    raw = json.dumps(log, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    key = (f'解決{sm["n"]}件・予測平均{sm["pred"]}%→実際{sm["hit"]}%' if sm["n"] else f'記録{len(log["entries"])}件・結果待ち')
    return (f'<div class="card pl-card" id="{CARD_ID}">'
            + fold.card("prediction-log", '<h2>予測の答え合わせ<span class="h2en">Prediction Log</span></h2>', key, body)
            + f'<script id="{STATE_ID}" type="application/json">{raw}</script><span class="pl-end"></span></div>')


STYLE = (
    f'<style id="{STYLE_ID}">'
    '.pl-card .pl-p{font-size:12.5px;line-height:1.65;color:var(--ds-ink-2,#46443d);margin:4px 0}'
    '.pl-card .pl-mut{font-size:11.5px;color:var(--ds-muted,#6b685e)}'
    '.pl-card .pl-t{width:100%;border-collapse:collapse;font-size:12px;margin:6px 0;table-layout:fixed}'
    '.pl-card .pl-t th:nth-child(1){width:48px}.pl-card .pl-t th:nth-child(3){width:40px}.pl-card .pl-t th:nth-child(4){width:70px}'
    '.pl-card .pl-t th{font-size:11px;font-weight:600;color:var(--ds-muted,#6b685e);text-align:left;padding:3px 4px}'
    '.pl-card .pl-t td{padding:5px 4px;border-top:1px solid var(--ds-line,#dedbd2);vertical-align:top;text-align:left;'
    'word-break:break-word;white-space:normal;color:var(--ds-ink-2,#46443d)}'
    '.pl-card .pl-t td small{display:block;font-size:10.5px;color:var(--ds-muted,#6b685e)}'
    '.pl-card .pl-y{color:var(--ds-up,#17703f);font-weight:700}.pl-card .pl-n{color:var(--ds-down,#b3362c);font-weight:700}'
    '.pl-card .pl-o{color:var(--ds-muted,#6b685e)}.pl-card .pl-end{display:none}'
    '</style>'
)
CARD_RE = re.compile(rf'<div class="card pl-card" id="{CARD_ID}">.*?<span class="pl-end"></span></div>', re.S)
STYLE_RE = re.compile(rf'<style id="{STYLE_ID}">.*?</style>', re.S)


def apply(text: str, log: dict | None) -> str:
    if not log or not log.get("entries"):
        return text
    card = card_html(log)
    if CARD_RE.search(text):
        out = CARD_RE.sub(lambda _: card, text, count=1)
    else:
        m = re.search(r'<div class="card pc-card" id="phase-check">.*?<span class="pc-end"></span></div>', text, re.S)
        if not m:
            print("prediction log: phase card not found; card not inserted", flush=True)
            return text
        out = text[:m.end()] + card + text[m.end():]
    out = STYLE_RE.sub("", out)
    out = out.replace("</head>", STYLE + "</head>", 1) if "</head>" in out else out
    return fold.ensure(out)


def rerender(text: str, root: Path) -> str:
    return apply(text, load(root))


def run(text: str, root: Path, session: str) -> str:
    import phase_check as pc
    import ftd_check as fc
    log = update(load(root), pc.embedded_state(text), fc.embedded_state(text), session, da.load_market(root))
    if save(root, log):
        print(f"prediction log: {len(log['entries'])} entries, {summary(log)}", flush=True)
    return apply(text, log)
