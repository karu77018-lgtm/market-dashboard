"""過熱セクターの目印 (display only; the 本命 rule and the slots are unchanged).

Study (research/swing-context-2026-11): 本命 signals from the hotter half of the sectors (median 63-day return of
the sector's names, ranked across the 11 sectors) did worse in 2014-19 and 2020-26 (PF 1.30 / 0.90 vs 2.06 / 3.91)
and in 11 of 13 years.  In the production engine, skipping them helped clearly only in 2021-26, so it is shown,
not applied, and every 本命 from now on is logged with its flag and checked 20 and 60 sessions later.
Sector labels: seed/sector-map.json (Yahoo, captured 2026-11-17; today's labels, not point-in-time).
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import fold

MAP = "seed/sector-map.json"
LOG = "seed/sector-heat-log.json"
CARD_ID = "sector-heat"
STATE_ID = "sector-heat-state"
STYLE_ID = "sector-heat-style"
ANCHOR_ID = "mc57-swing-screener"
MIN_NAMES = 20
JA = {"Technology": "テクノロジー", "Financial Services": "金融", "Healthcare": "ヘルスケア", "Industrials": "資本財",
      "Consumer Cyclical": "一般消費財", "Real Estate": "不動産", "Energy": "エネルギー", "Basic Materials": "素材",
      "Consumer Defensive": "生活必需品", "Communication Services": "通信", "Utilities": "公益"}


def load_map(root: Path) -> dict[str, str]:
    try:
        return json.loads((root / MAP).read_text(encoding="utf-8")).get("sectors", {})
    except (OSError, ValueError):
        return {}


def ranks(close: pd.DataFrame, sectors: dict[str, str], day: pd.Timestamp) -> pd.DataFrame:
    """Sector median 63-session return on `day` and its percentile rank (as in the study)."""
    c = close[close.index <= day]
    if len(c) < 64:
        return pd.DataFrame()
    r = (c.iloc[-1] / c.iloc[-64] - 1).dropna()
    lab = pd.Series(sectors).reindex(r.index).dropna()
    g = r.reindex(lab.index).groupby(lab).agg(["median", "size"])
    g = g[g["size"] >= MIN_NAMES].copy()
    g["rank"] = g["median"].rank(pct=True)
    g["hot"] = g["rank"] >= 0.5
    return g.sort_values("median", ascending=False)


def _pivots(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    f = frame[["ticker", "date", "open", "close"]].copy()
    f["ticker"] = f["ticker"].astype(str).str.upper()
    f["date"] = pd.to_datetime(f["date"], errors="coerce")
    for k in ("open", "close"):
        f[k] = pd.to_numeric(f[k], errors="coerce")
    f = f[f["date"].notna()].drop_duplicates(["ticker", "date"], keep="last")
    return (f.pivot(index="date", columns="ticker", values="close").sort_index(),
            f.pivot(index="date", columns="ticker", values="open").sort_index())


def best_of(root: Path, session: str) -> list[str]:
    try:
        s = json.loads((root / "track-record" / "signals.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(x.get("t")).upper() for x in ((s.get("sessions") or {}).get(session) or {}).get("best") or [] if x.get("t")]


def load_log(root: Path) -> dict:
    try:
        log = json.loads((root / LOG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log = {}
    log.setdefault("schema", "sector-heat-log.1")
    log.setdefault("entries", [])
    return log


def outcomes(entries: list[dict], close: pd.DataFrame, opn: pd.DataFrame) -> None:
    """Return from the next open to the close 20 and 60 sessions later (filled once known)."""
    idx = close.index
    for e in entries:
        if e.get("r60") is not None or e["t"] not in close:
            continue
        d = pd.Timestamp(e["session"])
        if d not in idx:
            continue
        i = idx.get_loc(d)
        if i + 1 >= len(idx):
            continue
        entry = opn[e["t"]].iloc[i + 1]
        if not np.isfinite(entry) or entry <= 0:
            continue
        e["entry"] = round(float(entry), 4)
        for n in (20, 60):
            if i + n < len(idx) and e.get(f"r{n}") is None:
                c = close[e["t"]].iloc[i + n]
                if np.isfinite(c):
                    e[f"r{n}"] = round(float(c / entry - 1) * 100, 2)


def summary(entries: list[dict]) -> dict:
    out = {}
    for hot in (True, False):
        es = [e for e in entries if e.get("hot") is hot]
        out["hot" if hot else "cold"] = {"n": len(es)} | {
            f"r{n}": (round(float(np.mean([e[f"r{n}"] for e in es if e.get(f"r{n}") is not None])), 1)
                      if any(e.get(f"r{n}") is not None for e in es) else None) for n in (20, 60)} | {
            f"n{n}": sum(1 for e in es if e.get(f"r{n}") is not None) for n in (20, 60)}
    return out


def build(frame: pd.DataFrame, root: Path, session: str) -> dict | None:
    sectors = load_map(root)
    if not sectors:
        return None
    close, opn = _pivots(frame)
    day = pd.Timestamp(session)
    g = ranks(close, sectors, day)
    if g.empty:
        return None
    log = load_log(root)
    have = {(e["session"], e["t"]) for e in log["entries"]}
    for t in best_of(root, session):
        if (session, t) in have:
            continue
        sec = sectors.get(t)
        row = g.loc[sec] if sec in g.index else None
        log["entries"].append({"session": session, "t": t, "sector": sec,
                               "rank": None if row is None else round(float(row["rank"]), 3),
                               "hot": None if row is None else bool(row["hot"])})
    outcomes(log["entries"], close, opn)
    log["updated"] = session
    path = root / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    today = [{"t": t, "sector": sectors.get(t), "hot": (bool(g.loc[sectors[t], "hot"]) if sectors.get(t) in g.index else None)}
             for t in best_of(root, session)]
    return {"session": session,
            "sectors": [{"name": n, "ja": JA.get(n, n), "r63": round(float(r["median"]) * 100, 1), "hot": bool(r["hot"]),
                         "n": int(r["size"])} for n, r in g.iterrows()],
            "today": today, "summary": summary(log["entries"]), "logged": len(log["entries"])}


# ---------------------------------------------------------------- rendering
def _s(v: float | None) -> str:
    return "—" if v is None else f"{v:+.1f}%".replace("-", "−")


def card_html(state: dict) -> str:
    e = html.escape
    hot = [s for s in state["sectors"] if s["hot"]]
    today = state.get("today") or []
    nh = sum(1 for x in today if x["hot"])
    key = (f'今日の本命{len(today)}件（過熱セクター{nh}件）｜過熱：' + "・".join(s["ja"] for s in hot[:4])
           + ("…" if len(hot) > 4 else ""))
    if today:
        items = "".join(
            f'<li><b>{e(x["t"])}</b> {e(JA.get(x["sector"] or "", x["sector"] or "分類なし"))}'
            + ('<span class="sh-hot">過熱セクター</span>' if x["hot"] else ('<span class="sh-ok">過熱でない</span>' if x["hot"] is False else ""))
            + '</li>' for x in today)
        lead = f'<ul class="sh-list">{items}</ul>'
    else:
        lead = '<div class="sh-p">今日の本命はありません。</div>'
    rows = "".join(f'<tr{" class=sh-on" if s["hot"] else ""}><td>{e(s["ja"])}</td><td>{_s(s["r63"])}</td>'
                   f'<td>{"過熱" if s["hot"] else ""}</td><td>{s["n"]}</td></tr>' for s in state["sectors"])
    sm = state["summary"]
    track = (f'<div class="sh-p">記録した本命{state["logged"]}件。'
             f'過熱セクター：20日後の平均{_s(sm["hot"]["r20"])}（{sm["hot"]["n20"]}件）・60日後{_s(sm["hot"]["r60"])}（{sm["hot"]["n60"]}件）、'
             f'それ以外：20日後{_s(sm["cold"]["r20"])}（{sm["cold"]["n20"]}件）・60日後{_s(sm["cold"]["r60"])}（{sm["cold"]["n60"]}件）。'
             '翌営業日の寄りから測った値で、売買ルールの手仕舞いとは別。</div>')
    body = (lead
            + '<div class="sh-p">過去検証（2014〜2026年）では、勢いの強いセクター（11セクターのうち63日の上昇率の中央値が上位半分）'
              'から出た本命のほうが成績が悪かった：PF 1.30・0.90（それ以外 2.06・3.91、2014〜19年・2020〜26年）、13年中11年。'
              'ただ、本番のエンジンで除外した効果がはっきりしたのは2021〜26年だけだったため、ルールには入れず目印として表示し、'
              '実際の結果をここで記録していきます。セクターは今日時点の分類（過去の分類ではない）。</div>'
            + f'<div class="sh-h">セクターの勢い（{e(state["session"])}・63日）</div>'
            + f'<table class="sh-t"><tr><th>セクター</th><th>上昇率の中央値</th><th></th><th>銘柄数</th></tr>{rows}</table>'
            + '<div class="sh-h">記録（実際の答え合わせ）</div>' + track
            + '<div class="sh-p sh-mut">表示のみで、本命の選び方・枠・手仕舞いは変えません（research/swing-context-2026-11）。</div>')
    raw = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    return (f'<div class="card sh-card" id="{CARD_ID}">'
            + fold.card("sector-heat", '<h2>過熱セクターの目印<span class="h2en">Sector Heat (tracking)</span></h2>', e(key), body)
            + f'<script id="{STATE_ID}" type="application/json">{raw}</script><span class="sh-end"></span></div>')


STYLE = (
    f'<style id="{STYLE_ID}">'
    '.sh-card .sh-p{font-size:12.5px;line-height:1.65;color:var(--ds-ink-2,#46443d);margin:4px 0}'
    '.sh-card .sh-mut{font-size:11.5px;color:var(--ds-muted,#6b685e)}'
    '.sh-card .sh-h{font-size:13px;font-weight:800;color:var(--ds-ink,#1c1b19);margin:10px 0 2px}'
    '.sh-card .sh-list{list-style:none;padding:0;margin:4px 0}.sh-card .sh-list li{font-size:13px;padding:3px 0}'
    '.sh-card .sh-hot{margin-left:6px;font-size:11px;font-weight:700;padding:1px 6px;border-radius:6px;background:#fdeceb;color:var(--ds-down,#b3362c)}'
    '.sh-card .sh-ok{margin-left:6px;font-size:11px;font-weight:700;padding:1px 6px;border-radius:6px;background:#e9f5ee;color:var(--ds-up,#17703f)}'
    '.sh-card .sh-t{width:100%;border-collapse:collapse;font-size:12px;margin:4px 0}'
    '.sh-card .sh-t th{font-size:11px;font-weight:600;color:var(--ds-muted,#6b685e);text-align:left;padding:3px 4px}'
    '.sh-card .sh-t td{padding:4px;border-top:1px solid var(--ds-line,#dedbd2);text-align:left;white-space:normal;color:var(--ds-ink-2,#46443d)}'
    '.sh-card .sh-t tr.sh-on td{background:#fdf3f2}.sh-card .sh-end{display:none}'
    '</style>'
)
CARD_RE = re.compile(rf'<div class="card sh-card" id="{CARD_ID}">.*?<span class="sh-end"></span></div>', re.S)
STATE_RE = re.compile(rf'<script id="{STATE_ID}" type="application/json">(.*?)</script>', re.S)
STYLE_RE = re.compile(rf'<style id="{STYLE_ID}">.*?</style>', re.S)


def _after_anchor(text: str) -> int | None:
    m = re.search(rf'<(div|section)\b[^>]*\bid="{ANCHOR_ID}"[^>]*>', text)
    if not m:
        return None
    depth = 0
    for t in re.finditer(r"<(/?)(div|section)\b[^>]*>", text[m.start():]):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return m.start() + t.end()
    return None


def apply(text: str, state: dict | None) -> str:
    if not state:
        return text
    card = card_html(state)
    if CARD_RE.search(text):
        out = CARD_RE.sub(lambda _: card, text, count=1)
    else:
        at = _after_anchor(text)
        if at is None:
            print("sector heat: swing screener card not found; card not inserted", flush=True)
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


def rerender(text: str, root: Path) -> str:
    return apply(text, embedded_state(text))


def run(text: str, frame: pd.DataFrame, root: Path, session: str) -> str:
    state = build(frame, root, session)
    if state is None:
        print("sector heat: inputs not usable; keeping the page as is", flush=True)
        return rerender(text, root)
    print(f"sector heat: hot={[s['name'] for s in state['sectors'] if s['hot']]} today={state['today']}", flush=True)
    return apply(text, state)
