"""Phone notices for changes in the added cards (display only; nothing about orders or rules).

The refresh compares what the cards say now with what was already notified (seed/alert-state.json, committed by
the refresh) and writes the new messages there with its run id.  The workflow's market_alert job then opens one
issue that mentions the owner, so GitHub's app notifies the phone.  A first run only records the current state.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

STATE = "seed/alert-state.json"
KEEP = 300
QUIET_LAMPS = ("特別な合図なし", "F3は高いが200日線の上")


def _md(day: str | None) -> str:
    if not day:
        return ""
    y, m, d = day[:10].split("-")
    return f"{int(m)}/{int(d)}"


def events(text: str) -> tuple[list[tuple[str, str]], str | None]:
    """(key, message) for everything the cards currently say that is worth a notice; plus the lamps' reading."""
    import phase_check as pc
    import ftd_check as fc
    import regime_history as rh
    import prediction_log as pl
    out: list[tuple[str, str]] = []
    ph = pc.embedded_state(text)
    if ph:
        q, s = ph["qqq"], ph.get("spy") or {}
        kind = pc.phase_of(ph)
        if kind in ("up5", "up10"):
            r = q[kind]
            n, ok, basis = pc.rate_of(r, kind)
            rise = "+5%（上げの初動）" if kind == "up5" else "+10%（上げ）"
            out.append((f"phase:{kind}:{r['date']}",
                        f"QQQが{_md(q['low'])}の安値から{rise}：本物の底になる率 {pc._pct(n, ok)}%（{basis}）。"
                        f"終値で{q['low_close']:.2f}を割ると失敗。"))
        elif kind == "down":
            out.append((f"phase:down:{q.get('peak')}", f"QQQが高値から−10%に入りました（下げ・今{q['dd']:+.1f}%）。".replace("-", "−")))
        for f in q.get("failed") or []:
            out.append((f"fail:{f['kind']}:{f['date']}", f"QQQの戻り（{_md(f['date'])}、○{f['score']}つ）は{_md(f['broke'])}に安値を割って失敗。"))
        end = q.get("last_end")
        if not q.get("in_decline") and end:
            out.append((f"phase:recovered:{end['date']}", f"QQQが高値から−2%以内に戻りました（{_md(end['low'])}の安値からの戻りは本物の底）。"))
        ev = s.get("event") or {}
        if ev.get("status") == "open":
            k = "hi" if ev.get("vix") is not None and ev["vix"] >= pc.VIX_CUT else "lo"
            n, hit = pc.REF_DOWN[k][:2]
            out.append((f"down5:{ev['date']}", f"S&P500が高値から−5%（下げの初動）：VIX {ev.get('vix')}、−10%まで下げる率 {pc._pct(n, hit)}%。"))
    ft = fc.embedded_state(text)
    for row in (ft or {}).get("rows", []):
        r = row.get("ftd")
        if not r:
            continue
        if r.get("broken"):
            out.append((f"ftdx:{row['sym']}:{r['date']}", f"FTDは騙し：{row['label']}の{_md(r['date'])}のFTDは{_md(r['broken']['date'])}に安値を割りました。"))
        elif r["age"] < fc.WINDOW:
            p, _ = fc.odds(r)
            act = "見送り" if len(fc.headwinds(r)) >= fc.SKIP_AT else "翌日の寄りで入る"
            out.append((f"ftd:{row['sym']}:{r['date']}",
                        f"FTD点灯：{row['label']} {_md(r['date'])} Day{r['day']} +{r['pct']:.1f}%。騙し{p}%、判定：{act}"
                        f"（逆風{len(fc.headwinds(r))}/3）。撤退の目安 {r['low']:.2f}。"))
    lamp = None
    rg = rh.embedded_state(text)
    if rg:
        _, head, _ = rh.reading(rg)
        lamp = head
    log = pl.load(Path(os.environ.get("MARKET_ROOT", ".")))
    for e in log.get("entries", []):
        if e.get("outcome") is not None:
            out.append((f"res:{e['id']}", f"答え合わせ：{pl.KINDS[e['kind']]}（{_md(e['event'])}、予測{e['prob']}%）→ "
                                          f"{'起きた' if e['outcome'] else '起きなかった'}。"))
    return out, lamp


def run(text: str, root: Path, session: str) -> list[str]:
    os.environ.setdefault("MARKET_ROOT", str(root))
    path = root / STATE
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
        first = False
    except (OSError, ValueError):
        st, first = {"seen": [], "lamp": None}, True
    evs, lamp = events(text)
    seen = set(st.get("seen", []))
    msgs = [m for k, m in evs if k not in seen]
    if lamp and lamp not in QUIET_LAMPS and lamp != st.get("lamp"):
        msgs.append(f"警戒灯の読み方が変わりました：{lamp}。")
    if first:
        msgs = []
    st["seen"] = (list(st.get("seen", [])) + [k for k, _ in evs if k not in seen])[-KEEP:]
    st["lamp"] = lamp
    st["last"] = {"run": os.environ.get("GITHUB_RUN_ID", "local"), "session": session, "messages": msgs}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for m in msgs:
        print("market alert: " + m, flush=True)
    return msgs
