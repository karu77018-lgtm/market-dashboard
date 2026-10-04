"""Public track record of the new swing rule (forward, point-in-time).

Display + ledger only; no trading rule changes.

Ledger (track-record/signals.json, committed with the page and archived):
* sessions[day]: the 本命 of that session as first published, frozen.  A run
  whose swing card is missing records an input failure and does NOT freeze an
  empty list; a later good run of the same session becomes the first record.
  Later different lists only update ``latest`` / ``revisions``.
* trades["day:TICKER"]: the execution state of every frozen 本命, advanced one
  bar at a time on each daily refresh and never recomputed from the chart
  window.  Closed trades are final; a ticker that later leaves the data keeps
  its last state and is marked stale.

Execution (all at prices a reader could actually get, the list being published
after the close):
* entry at the next session's open; stop = entry x 0.92
* a gap at/below the stop exits at that open; otherwise a low at/below the stop
  exits at the stop
* a close below the 21-EMA of lows is confirmed at the close and exits at the
  NEXT open ("売り待ち" until then)
* 買い増し: a close at entry x 1.10 / 1.20 (rounded to 1e-9) buys the SAME AMOUNT
  as the first purchase at the next open (unless that open exits)
* QQQ is measured over exactly the same execution timestamps (open->open,
  open->stop-day close, or open->latest close)
No fees, slippage or taxes.  Each 本命 is one independent signal; capital, the
6-slot cap, the 40% cap and repeated signals of one ticker are NOT modelled.
"""
from __future__ import annotations

import html
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from rules_tab import RULE_ID

LEDGER = Path("track-record/signals.json")
SCHEMA = "mc57-track-record.2"
OLD_SCHEMAS = ("mc57-track-record.1",)
TAB_ID = "t-record"
TAB_LABEL = "成績"
STOP = 0.08
ADDS = (0.10, 0.20)
ALPHA = 2 / 22  # 21-EMA, adjust=False
SEC_RE = re.compile(r'<div class="sw-sec[^"]*"><span>([^<]+)<small>.*?</span>'
                    r'(?:<button class="cp" data-tk="([^"]*)")?', re.S)


class LedgerError(RuntimeError):
    """The ledger exists but cannot be trusted; never overwrite it."""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def published_best(text: str) -> tuple[str, list[str]]:
    """("ok", tickers) when the swing card and its 本命 header exist, else (reason, [])."""
    start = text.find('id="mc57-swing-screener"')
    if start < 0:
        return "no_card", []
    card = text[start:text.find("</section>", start)]
    for m in SEC_RE.finditer(card):
        if m.group(1).strip() == "本命":
            return "ok", [t.strip().upper() for t in (m.group(2) or "").split(",") if t.strip()]
    return "no_section", []


def card_regime(text: str) -> str | None:
    m = re.search(r'id="mc57-swing-screener"[^>]*data-regime="([a-z]+)"', text)
    return m.group(1) if m else None


def new_ledger() -> dict[str, Any]:
    return {"schema": SCHEMA, "rule": RULE_ID, "sessions": {}, "trades": {}, "failures": []}


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return new_ledger()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LedgerError(f"ledger unreadable: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("sessions"), dict):
        raise LedgerError("ledger has no sessions object")
    if data.get("schema") in OLD_SCHEMAS:
        data["schema"] = SCHEMA
        data.setdefault("trades", {})
        data.setdefault("failures", [])
    if data.get("schema") != SCHEMA:
        raise LedgerError(f"unknown ledger schema {data.get('schema')!r}")
    data.setdefault("trades", {})
    data.setdefault("failures", [])
    return data


def save(ledger: dict, path: Path) -> None:
    """Atomic write (temp file + rename) so a crash never leaves half a ledger."""
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(ledger, ensure_ascii=False, indent=1) + "\n"
    json.loads(blob)  # never write something we cannot read back
    fd, tmp = tempfile.mkstemp(prefix=".signals-", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(blob)
    os.replace(tmp, path)


def record(ledger: dict, text: str, session: str, closes: dict[str, float], now: str | None = None) -> dict:
    """Freeze (or revise) the session's 本命 in ``ledger`` (in place)."""
    now = now or now_utc()
    status, best = published_best(text)
    entry = ledger["sessions"].get(session)
    if status != "ok":
        ledger["failures"].append({"session": session, "at": now, "reason": status})
        ledger["failures"] = ledger["failures"][-200:]
        return ledger
    rows = [{"t": t, "close": closes.get(t)} for t in best]
    if entry is None:
        ledger["sessions"][session] = {"recorded_at": now, "best": rows, "regime": card_regime(text),
                                       "rule": RULE_ID, "revisions": 0}
    elif [r["t"] for r in entry.get("latest", entry["best"])] != best:
        entry["latest"] = rows
        entry["revisions"] = int(entry.get("revisions", 0)) + 1
        entry["revised_at"] = now
    ledger["sessions"] = dict(sorted(ledger["sessions"].items()))
    ledger["start"] = min(ledger["sessions"])
    return ledger


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _reached(close: float, entry: float, level: float) -> bool:
    return round(close / entry - 1, 9) >= level


def advance(state: dict, bars: pd.DataFrame | None, qqq: dict[str, dict]) -> dict:
    """Move one trade forward through bars after state['last_day'].  Closed trades are final."""
    if state.get("closed"):
        return state
    if bars is None or bars.empty:
        state["stale"] = True
        return state
    bars = bars.sort_index()
    dates = [d.strftime("%Y-%m-%d") for d in bars.index]
    session = state["session"]
    if "ema" not in state:
        if session not in dates:
            state["stale"] = True
            return state
        i = dates.index(session)
        lows = bars["low"].iloc[:i + 1].astype(float)
        state["ema"] = float(lows.ewm(span=21, adjust=False).mean().iloc[-1])
        state["last_day"] = session
    state.pop("stale", None)
    last_day = state["last_day"]
    for k, day in enumerate(dates):
        if day <= last_day:
            continue
        o, lo, c = (_f(bars[col].iloc[k]) for col in ("open", "low", "close"))
        if o is None or lo is None or c is None:
            state["stale"] = True
            break
        q = qqq.get(day) or {}
        state["days"] = int(state.get("days", 0)) + 1
        if state["status"] == "約定待ち":
            state.update({"status": "保有中", "entry_day": day, "entry": o, "stop": o * (1 - STOP),
                          "shares": 1 / o, "invested": 1.0, "adds": 0, "triggered": [], "pending_add": 0,
                          "pending_exit": False, "qqq_in": _f(q.get("open"))})
        else:
            if state.get("pending_exit"):
                _close(state, day, o, "安値21EMA割れ（翌始値）", _f(q.get("open")))
                break
            if o <= state["stop"]:
                _close(state, day, o, "損切り（窓）", _f(q.get("open")))
                break
            for _ in range(int(state.get("pending_add", 0))):
                state["shares"] += 1 / o
                state["invested"] += 1.0
                state["adds"] += 1
            state["pending_add"] = 0
        if lo <= state["stop"]:
            _close(state, day, state["stop"], "損切り −8%", _f(q.get("close")))
            break
        state["ema"] = ALPHA * lo + (1 - ALPHA) * state["ema"]
        state.update({"last_day": day, "last": c, "qqq_last": _f(q.get("close"))})
        if c < state["ema"]:
            state["pending_exit"] = True
            state["status"] = "売り待ち（21EMA割れ）"
            continue
        for n, lvl in enumerate(ADDS):
            if n not in state["triggered"] and _reached(c, state["entry"], lvl):
                state["triggered"].append(n)
                state["pending_add"] = int(state.get("pending_add", 0)) + 1
    return state


def _close(state: dict, day: str, price: float, reason: str, qqq_out: float | None) -> None:
    state.update({"closed": True, "status": reason, "exit_day": day, "exit": price, "last_day": day,
                  "last": price, "qqq_out": qqq_out, "pending_add": 0, "pending_exit": False})


def metrics(state: dict) -> dict:
    """Display numbers from a stored state (no recomputation from bars)."""
    out = {"ticker": state["ticker"], "session": state["session"], "status": state["status"],
           "closed": bool(state.get("closed")), "stale": bool(state.get("stale"))}
    entry = state.get("entry")
    if entry is None:
        return out
    px = state["exit"] if state.get("closed") else state.get("last", entry)
    out.update({"entry_day": state["entry_day"], "entry": entry, "last": px, "adds": state.get("adds", 0),
                "ret": px / entry - 1, "ret_add": state["shares"] * px / state["invested"] - 1})
    q0 = state.get("qqq_in")
    q1 = state.get("qqq_out") if state.get("closed") else state.get("qqq_last")
    if q0 and q1:
        out["qqq"] = q1 / q0 - 1
    end = state.get("exit_day") or state.get("last_day")
    out["end"] = end
    out["days"] = state.get("days")
    return out


def advance_all(ledger: dict, frame: pd.DataFrame, qqq: dict[str, dict]) -> None:
    by_ticker = {t: g.set_index("date")[["open", "high", "low", "close"]] for t, g in frame.groupby("ticker")}
    for session, entry in ledger["sessions"].items():
        for row in entry.get("best", []):
            key = f"{session}:{row['t']}"
            state = ledger["trades"].get(key) or {"ticker": row["t"], "session": session, "status": "約定待ち"}
            advance(state, by_ticker.get(row["t"]), qqq)
            ledger["trades"][key] = state


def qqq_bars(path: Path) -> dict[str, dict]:
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))["series"]["QQQ"]
    except Exception:
        return {}
    return {str(r["date"])[:10]: {"open": r.get("open"), "close": r.get("close")} for r in rows if r.get("date")}


def _p(v: float | None) -> str:
    if v is None:
        return "—"
    color = "#c62828" if v < 0 else "#18813d" if v > 0 else "#565243"
    return f'<span style="color:{color}">{v:+.1%}</span>'.replace("-", "−")


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def summary(trades: list[dict]) -> dict:
    done = [t for t in trades if t.get("closed") and "ret" in t]
    live = [t for t in trades if not t.get("closed") and "ret" in t]
    allt = done + live
    rel = [t["ret"] - t["qqq"] for t in allt if "qqq" in t]
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    return {
        "signals": len(trades), "closed": len(done), "open": len(live),
        "win": (sum(t["ret"] > 0 for t in done) / len(done)) if done else None,
        "avg": mean([t["ret"] for t in done]), "median": _median([t["ret"] for t in done]),
        "avg_add": mean([t["ret_add"] for t in done]),
        "days": mean([t["days"] for t in done if t.get("days")]),
        "vs_qqq": mean(rel), "vs_qqq_n": len(rel),
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
         f'#{TAB_ID} .tr-warn{{font-size:11.5px;background:#f6e3dc;color:#8a2f1d;border:1px solid #e3b4a3;border-radius:8px;padding:6px 9px;margin:6px 0}}'
         f'body:has(#{TAB_ID}:target) nav a.tabx{{background:#ebeae5;color:#5a5850;border-color:#575342}}'
         f'body:has(#{TAB_ID}:target) nav a[href="#{TAB_ID}"]{{background:#3774d3;color:#f1f0ef;border-color:#eef3fb}}'
         '</style>')


def tab_html(ledger: dict | None, trades: list[dict], error: str | None = None) -> str:
    e = html.escape
    ledger = ledger or new_ledger()
    s = summary(trades)
    start = ledger.get("start") or "—"
    days = len(ledger.get("sessions", {}))
    fmt = lambda v, f: "—" if v is None else f(v)
    grid = "".join(f"<div><i>{k}</i><b>{v}</b></div>" for k, v in (
        ("本命の数", str(s["signals"])), ("確定", str(s["closed"])), ("保有中", str(s["open"])),
        ("勝率（確定）", fmt(s["win"], lambda v: f"{v:.0%}")), ("平均（確定）", _p(s["avg"])),
        ("中央値（確定）", _p(s["median"])), ("買い増し込み平均", _p(s["avg_add"])),
        ("平均保有日数", fmt(s["days"], lambda v: f"{v:.0f}日")),
        (f"QQQとの差（{s['vs_qqq_n']}件）", _p(s["vs_qqq"])),
    ))
    order = sorted(trades, key=lambda t: (t["session"], t["ticker"]), reverse=True)
    rows = "".join(
        f'<tr><td><b data-tkone="{e(t["ticker"])}">{e(t["ticker"])}</b></td><td>{e(t["session"][5:].replace("-", "/"))}</td>'
        f'<td>{"$" + format(t["entry"], ",.2f") if t.get("entry") else "—"}</td>'
        f'<td>{"$" + format(t["last"], ",.2f") if t.get("last") else "—"}</td>'
        f'<td>{_p(t.get("ret"))}</td><td>{_p(t.get("ret_add"))}</td>'
        f'<td>{_p(t["ret"] - t["qqq"]) if "qqq" in t else "—"}</td>'
        f'<td>{t["days"] if t.get("days") else "—"}</td>'
        f'<td>{e(t["status"])}{"（データ途絶）" if t.get("stale") else ""}{"＊" if t.get("revised") else ""}</td></tr>'
        for t in order) or '<tr><td colspan="9" style="text-align:center;color:#706e64">まだ記録がありません。次の更新から記録します。</td></tr>'
    fails = [f for f in ledger.get("failures", []) if f.get("session") not in ledger.get("sessions", {})]
    warn = ""
    if error:
        warn += f'<div class="tr-warn">記録ファイルを読めなかったため、今回は記録も表示も更新していません（{e(error)}）。</div>'
    if fails:
        warn += (f'<div class="tr-warn">入力欠落で本命を記録できなかった日：'
                 f'{e("、".join(sorted({f["session"] for f in fails})))}（0件とは扱っていません）</div>')
    return (
        f'<section id="{TAB_ID}"><div class="card" id="track-record-card" data-rule="{RULE_ID}">'
        '<div class="chd"><h2>公開成績（新ルール・前向き記録）<span class="h2en">Track Record</span></h2></div>'
        f'<div class="sub">毎日の「本命」を公開した時点で記録し、<b>実際に取れる価格</b>で追跡。'
        f'記録開始 {e(start)}（{days}営業日分）。ルール版 {e(RULE_ID)}。</div>'
        + warn +
        f'<div class="tr-grid">{grid}</div>'
        '<div class="tr-wrap"><table><tr><th>銘柄</th><th>本命の日</th><th>買値（翌始値）</th><th>現在/売値</th>'
        f'<th>損益</th><th>買い増し込み</th><th>QQQとの差</th><th>日数</th><th>状態</th></tr>{rows}</table></div>'
        '<div class="tr-note"><b>何の成績か</b>：本命1件ごとの<b>シグナル成績</b>です。資金残高・最大6銘柄・1銘柄40%上限・'
        '同じ銘柄の重複シグナルは考慮していないため、6銘柄ポートフォリオの実績や、Rulesタブの検証年率とは直接比べられません。<br/>'
        '<b>約定</b>：本命は引け後に公開するので<b>翌営業日の始値</b>で買い。損切りは買値−8%（窓で下回ればその始値）。'
        '安値21EMA割れは引けで確定するため<b>翌営業日の始値</b>で売り（それまで「売り待ち」）。'
        '買い増し込みは、終値が買値+10%・+20%に届いた翌営業日の始値で<b>最初と同じ金額</b>を追加した場合。<br/>'
        '<b>QQQとの差</b>：同じ約定時点（始値→始値、始値→損切り日の終値、保有中は直近終値）のQQQとの差。取れない分は「—」。<br/>'
        '<b>記録のしかた</b>：本命はその日の最初の公開内容で確定し、約定・確定の結果とともに '
        '<code>track-record/signals.json</code> に保存（Gitの履歴と毎日のスナップショットに残る）。'
        'あとで再計算して本命が変わった日は＊印（成績は最初の公開内容で計算）。手数料・スリッページ・税金は含みません。<br/>'
        '過去の成績は将来の成績を保証しません。売買の推奨ではなく、ルールの検証記録です。</div>'
        '</div></section>'
    )


def trades_for_display(ledger: dict) -> list[dict]:
    out = []
    for session, entry in ledger.get("sessions", {}).items():
        for row in entry.get("best", []):
            state = ledger.get("trades", {}).get(f"{session}:{row['t']}") or {
                "ticker": row["t"], "session": session, "status": "約定待ち"}
            m = metrics(state)
            m["revised"] = int(entry.get("revisions", 0)) > 0
            out.append(m)
    return out


def apply(text: str, ledger: dict | None, trades: list[dict], error: str | None = None) -> str:
    if f'id="{TAB_ID}"' in text:
        text = re.sub(rf'<section id="{TAB_ID}">.*?</section>', '', text, count=1, flags=re.S)
    anchor = '<section id="t-alloc">'
    end = text.find("</section>", text.find(anchor)) if anchor in text else -1
    if end < 0:
        return text
    end += len("</section>")
    text = text[:end] + tab_html(ledger, trades, error) + text[end:]
    if f'<a class="tabx" href="#{TAB_ID}"' not in text:
        link = (f'<a class="tabx" href="#{TAB_ID}" onclick="tab(\'{TAB_ID}\',this);return false;">{TAB_LABEL}</a>')
        m = re.search(r'<a class="tabx"[^>]*href="#t-alloc"[^>]*>.*?</a>', text)
        if m:
            text = text[:m.end()] + link + text[m.end():]
    if 'id="track-record-style"' not in text:
        text = text.replace("</head>", STYLE + "</head>", 1)
    return text


def run(text: str, frame: pd.DataFrame, session: str, root: Path, qqq_path: Path | None = None) -> str:
    """Daily refresh: freeze today's 本命, advance every open trade, save, render."""
    path = root / LEDGER
    try:
        ledger = load(path)
    except LedgerError as exc:
        print(f"track record ledger not updated: {exc}", flush=True)
        return apply(text, None, [], error=str(exc))
    last = frame[frame["date"] == pd.Timestamp(session)].set_index("ticker")["close"].to_dict()
    record(ledger, text, session, {k: float(v) for k, v in last.items()})
    advance_all(ledger, frame, qqq_bars(qqq_path or root / "data" / "market_inputs.json"))
    save(ledger, path)
    return apply(text, ledger, trades_for_display(ledger))


def render_only(text: str, root: Path) -> str:
    """Display workflows: render the committed ledger; never record or advance."""
    try:
        ledger = load(root / LEDGER)
    except LedgerError as exc:
        return apply(text, None, [], error=str(exc))
    return apply(text, ledger, trades_for_display(ledger))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--html", default="source-mc57.html")
    a = ap.parse_args()
    root = Path(a.root)
    page = root / a.html
    page.write_text(render_only(page.read_text(encoding="utf-8"), root), encoding="utf-8")
