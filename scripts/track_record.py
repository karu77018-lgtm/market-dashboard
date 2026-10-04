"""Public track record of the new swing rule (forward, point-in-time).

Display + ledger only; no trading rule changes.

* record(): on each refresh, the swing card's 本命 for the session are appended
  to track-record/signals.json.  The first publication of a session is frozen
  (what a reader saw first); later reruns only update ``latest`` and count
  ``revisions``.  The file is committed with the page, so Git commit times
  prove when each list was published.
* evaluate(): every recorded 本命 is bought at the NEXT session's open (the
  list is published after the close, so that is the first price a reader can
  get) and managed with the rule's exits: -8% stop (gap below -> that open),
  else the first close below the 21-EMA of lows.  "買い増し込み" also adds the
  same amount at closes of +10% and +20%.  No fees, slippage or taxes.
* apply(): renders the 成績 tab.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

LEDGER = Path("track-record/signals.json")
SCHEMA = "mc57-track-record.1"
TAB_ID = "t-record"
TAB_LABEL = "成績"
STOP = 0.08
ADDS = (0.10, 0.20)
SEC_RE = re.compile(r'<div class="sw-sec[^"]*"><span>([^<]+)<small>.*?</span>'
                    r'(?:<button class="cp" data-tk="([^"]*)")?', re.S)


def published_best(text: str) -> list[str]:
    start = text.find('id="mc57-swing-screener"')
    if start < 0:
        return []
    card = text[start:text.find("</section>", start)]
    for m in SEC_RE.finditer(card):
        if m.group(1).strip() == "本命":
            return [t.strip().upper() for t in (m.group(2) or "").split(",") if t.strip()]
    return []


def load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") == SCHEMA:
            return data
    except (OSError, ValueError):
        pass
    return {"schema": SCHEMA, "rule": "スイングルール（新ルール・最大6銘柄）", "sessions": {}}


def record(text: str, path: Path, session: str, closes: dict[str, float], now: str | None = None) -> dict:
    """Append (or revise) the session's 本命.  Returns the ledger."""
    ledger = load(path)
    best = published_best(text)
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    rows = [{"t": t, "close": closes.get(t)} for t in best]
    entry = ledger["sessions"].get(session)
    if entry is None:
        ledger["sessions"][session] = {"recorded_at": now, "best": rows, "revisions": 0}
    elif [r["t"] for r in entry.get("latest", entry["best"])] != best:
        entry["latest"] = rows
        entry["revisions"] = int(entry.get("revisions", 0)) + 1
        entry["revised_at"] = now
    ledger.setdefault("start", min(ledger["sessions"]))
    ledger["sessions"] = dict(sorted(ledger["sessions"].items()))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    return ledger


def _trade(bars: pd.DataFrame, session: str) -> dict | None:
    """bars: one ticker, date-indexed, columns open/high/low/close."""
    bars = bars.sort_index()
    dates = [d.strftime("%Y-%m-%d") for d in bars.index]
    if session not in dates:
        return None
    i = dates.index(session)
    if i + 1 >= len(bars):
        return {"status": "約定待ち"}
    el21 = bars["low"].ewm(span=21, adjust=False).mean()
    o, h, l, c = (bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    entry = o[i + 1]
    stop = entry * (1 - STOP)
    units, cost, added = 1.0, entry, set()
    exit_px = reason = exit_day = None
    for j in range(i + 1, len(bars)):
        if j > i + 1 and o[j] <= stop:
            exit_px, reason = o[j], "損切り（窓）"
        elif l[j] <= stop:
            exit_px, reason = stop, "損切り −8%"
        elif c[j] < el21.iloc[j]:
            exit_px, reason = c[j], "安値21EMA割れ"
        if exit_px is not None:
            exit_day = dates[j]
            break
        for k, lvl in enumerate(ADDS):
            if k not in added and c[j] >= entry * (1 + lvl):
                added.add(k)
                units += 1
                cost += c[j]
    last = exit_px if exit_px is not None else c[-1]
    end = exit_day or dates[-1]
    return {"status": reason or "保有中", "closed": exit_px is not None, "entry_day": dates[i + 1],
            "entry": entry, "last": last, "end": end, "days": dates.index(end) - (i + 1) + 1,
            "ret": last / entry - 1, "ret_add": units * last / cost - 1, "adds": len(added)}


def evaluate(ledger: dict, frame: pd.DataFrame, qqq: dict[str, float] | None = None) -> list[dict]:
    out = []
    by_ticker = {t: g.set_index("date")[["open", "high", "low", "close"]] for t, g in frame.groupby("ticker")}
    for session, entry in ledger.get("sessions", {}).items():
        for row in entry.get("best", []):
            bars = by_ticker.get(row["t"])
            trade = _trade(bars, session) if bars is not None else None
            if trade is None:
                trade = {"status": "データなし"}
            trade.update({"ticker": row["t"], "session": session, "revised": int(entry.get("revisions", 0)) > 0})
            if qqq and trade.get("entry_day"):
                q0, q1 = qqq.get(session), qqq.get(trade["end"])
                if q0 and q1:
                    trade["qqq"] = q1 / q0 - 1
            out.append(trade)
    return out


def qqq_closes(path: Path) -> dict[str, float]:
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))["series"]["QQQ"]
        return {str(r["date"])[:10]: float(r["close"]) for r in rows if r.get("close") is not None}
    except Exception:
        return {}


def _p(v: float | None) -> str:
    if v is None:
        return "—"
    color = "#c62828" if v < 0 else "#18813d" if v > 0 else "#565243"
    return f'<span style="color:{color}">{v:+.1%}</span>'.replace("-", "−")


def summary(trades: list[dict]) -> dict:
    done = [t for t in trades if t.get("closed")]
    live = [t for t in trades if t.get("entry_day") and not t.get("closed")]
    allt = done + live
    rel = [t["ret"] - t["qqq"] for t in allt if "qqq" in t]
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
    return {
        "signals": len(trades), "closed": len(done), "open": len(live),
        "win": (sum(t["ret"] > 0 for t in done) / len(done)) if done else None,
        "avg": mean([t["ret"] for t in done]), "median": med([t["ret"] for t in done]),
        "avg_add": mean([t["ret_add"] for t in done]),
        "days": mean([t["days"] for t in done]),
        "all_avg": mean([t["ret"] for t in allt]), "vs_qqq": mean(rel),
    }


STYLE = ('<style id="track-record-style">'
         f'#{TAB_ID} .tr-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:8px 0}}'
         f'#{TAB_ID} .tr-grid div{{background:#f2f1ee;border:1px solid #e3e1db;border-radius:10px;padding:8px;text-align:center}}'
         f'#{TAB_ID} .tr-grid i{{display:block;font-style:normal;font-size:11px;color:#575242}}'
         f'#{TAB_ID} .tr-grid b{{font-size:17px;font-variant-numeric:tabular-nums}}'
         f'#{TAB_ID} .tr-wrap{{max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}}'
         f'#{TAB_ID} table{{width:100%;border-collapse:collapse;font-size:12px;min-width:560px}}'
         f'#{TAB_ID} th,#{TAB_ID} td{{border-bottom:1px solid #e0ddd5;padding:5px 6px;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}'
         f'#{TAB_ID} th{{font-size:10.5px;color:#706e64}}#{TAB_ID} td:first-child,#{TAB_ID} th:first-child{{text-align:left}}'
         f'#{TAB_ID} .tr-note{{font-size:11px;color:#706e64;line-height:1.6;margin-top:8px}}'
         f'body:has(#{TAB_ID}:target) nav a.tabx{{background:#ebeae5;color:#5a5850;border-color:#575342}}'
         f'body:has(#{TAB_ID}:target) nav a[href="#{TAB_ID}"]{{background:#3774d3;color:#f1f0ef;border-color:#eef3fb}}'
         '</style>')


def tab_html(ledger: dict, trades: list[dict]) -> str:
    e = html.escape
    s = summary(trades)
    start = ledger.get("start") or "—"
    days = len(ledger.get("sessions", {}))
    fmt = lambda v, f: "—" if v is None else f(v)
    grid = "".join(f"<div><i>{k}</i><b>{v}</b></div>" for k, v in (
        ("本命の数", str(s["signals"])), ("確定", str(s["closed"])), ("保有中", str(s["open"])),
        ("勝率（確定）", fmt(s["win"], lambda v: f"{v:.0%}")), ("平均（確定）", _p(s["avg"])),
        ("中央値（確定）", _p(s["median"])), ("買い増し込み平均", _p(s["avg_add"])),
        ("平均保有日数", fmt(s["days"], lambda v: f"{v:.0f}日")), ("QQQとの差（全件）", _p(s["vs_qqq"])),
    ))
    order = sorted(trades, key=lambda t: (t["session"], t["ticker"]), reverse=True)
    rows = "".join(
        f'<tr><td><b data-tkone="{e(t["ticker"])}">{e(t["ticker"])}</b></td><td>{e(t["session"][5:].replace("-", "/"))}</td>'
        f'<td>{"$" + format(t["entry"], ",.2f") if t.get("entry") else "—"}</td>'
        f'<td>{"$" + format(t["last"], ",.2f") if t.get("last") else "—"}</td>'
        f'<td>{_p(t.get("ret"))}</td><td>{_p(t.get("ret_add"))}</td>'
        f'<td>{_p(t["ret"] - t["qqq"]) if "qqq" in t else "—"}</td>'
        f'<td>{t["days"] if t.get("days") else "—"}</td><td>{e(t["status"])}{"＊" if t.get("revised") else ""}</td></tr>'
        for t in order) or '<tr><td colspan="9" style="text-align:center;color:#706e64">まだ記録がありません。次の更新から記録します。</td></tr>'
    return (
        f'<section id="{TAB_ID}"><div class="card" id="track-record-card">'
        '<div class="chd"><h2>公開成績（新ルール・前向き記録）<span class="h2en">Track Record</span></h2></div>'
        f'<div class="sub">毎日の「本命」を公開した時点で記録し、<b>翌営業日の始値で買った</b>場合の結果を、'
        f'ルールどおりの手仕舞い（−8%損切り・安値21EMA割れ）で集計。記録開始 {e(start)}（{days}営業日分）。</div>'
        f'<div class="tr-grid">{grid}</div>'
        '<div class="tr-wrap"><table><tr><th>銘柄</th><th>本命の日</th><th>買値（翌始値）</th><th>現在/売値</th>'
        f'<th>損益</th><th>買い増し込み</th><th>QQQとの差</th><th>日数</th><th>状態</th></tr>{rows}</table></div>'
        '<div class="tr-note"><b>記録のしかた</b>：本命はその日の最初の公開内容で確定し、'
        '<code>track-record/signals.json</code> に毎日追記します。Gitのコミット日時で、いつ何を出したかを後から確認できます。'
        'あとで再計算して本命が変わった日は＊印（成績は最初の公開内容で計算）。<br/>'
        '<b>計算</b>：損益は1単位、買い増し込みは+10%・+20%の終値で同額を追加した場合。QQQとの差は本命の日の終値から'
        '売った日（保有中は直近）までのQQQとの比較。手数料・スリッページ・税金は含みません。<br/>'
        '過去の成績は将来の成績を保証しません。売買の推奨ではなく、ルールの検証記録です。</div>'
        '</div></section>'
    )


def apply(text: str, ledger: dict, trades: list[dict]) -> str:
    if f'id="{TAB_ID}"' in text:
        text = re.sub(rf'<section id="{TAB_ID}">.*?</section>', '', text, count=1, flags=re.S)
    anchor = '<section id="t-alloc">'
    end = text.find("</section>", text.find(anchor)) if anchor in text else -1
    if end < 0:
        return text
    end += len("</section>")
    text = text[:end] + tab_html(ledger, trades) + text[end:]
    if f'href="#{TAB_ID}"' not in text:
        link = (f'<a class="tabx" href="#{TAB_ID}" onclick="tab(\'{TAB_ID}\',this);return false;">{TAB_LABEL}</a>')
        m = re.search(r'<a class="tabx"[^>]*href="#t-alloc"[^>]*>.*?</a>', text)
        if m:
            text = text[:m.end()] + link + text[m.end():]
    if 'id="track-record-style"' not in text:
        text = text.replace("</head>", STYLE + "</head>", 1)
    return text


def run(text: str, frame: pd.DataFrame, session: str, root: Path) -> str:
    """Record today's 本命, evaluate the ledger and render the tab (display-only)."""
    last = frame[frame["date"] == pd.Timestamp(session)].set_index("ticker")["close"].to_dict()
    ledger = record(text, root / LEDGER, session, {k: float(v) for k, v in last.items()})
    trades = evaluate(ledger, frame, qqq_closes(root / "data" / "market_inputs.json"))
    return apply(text, ledger, trades)


def frame_from_chart_data(root: Path) -> pd.DataFrame:
    rows = []
    for f in sorted((root / "chart-data").glob("shard-*.json")):
        for ticker, series in json.loads(f.read_text(encoding="utf-8")).items():
            rows.extend((ticker, *b[:6]) for b in series)
    frame = pd.DataFrame(rows, columns=["ticker", "date", "open", "high", "low", "close", "volume"])
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


if __name__ == "__main__":
    # Render-only (display workflows): uses the committed ledger and the published
    # candles; never records.  Recording happens only in the daily refresh.
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--html", default="source-mc57.html")
    a = ap.parse_args()
    root = Path(a.root)
    page = root / a.html
    ledger = load(root / LEDGER)
    trades = evaluate(ledger, frame_from_chart_data(root), qqq_closes(root / "data" / "market_inputs.json"))
    page.write_text(apply(page.read_text(encoding="utf-8"), ledger, trades), encoding="utf-8")
