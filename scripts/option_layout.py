"""オプション配置の良い候補 (Setups tab, under validation).

Of the Positions-tab candidates (本命・まだ入れる・次の候補・好位置リーダー・拾う枠)
and the RS leaders (trend template x RS189 top 40),
show the ones whose option positioning leaves room above and support below:

* 上値の壁 (largest call OI at or above the price) is >= +10% away, or absent:
  nothing in the way of the first add (+10%)
* 下値の支え (largest put OI at or below the price) is 0..-8% away: support above
  the -8% stop
* the price is above 性質の境目 (dealer gamma flip): the calmer side
* open interest is not thin (options_walls conf == "OK")

There is no history of open interest (Cboe publishes today's only), so this is
validated forward: every candidate judged each day is stored in
track-record/option-layout.json with its walls and the pass/fail result, and once
20 sessions have passed the card compares the 20-session return of the ones that
passed with the ones that did not (one observation per ticker per 20 sessions).
Display only, never a gate.  Replaces the earlier 支えへの接触 card.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

CARD_ID = "option-layout"
MSEC_ID = "option-layout-msec"
LEDGER = Path("track-record/option-layout.json")
SCHEMA = "option-layout.1"
ROOM = 0.10
SUPPORT = (-0.08, 0.0)
HORIZON = 20
ROLES = ("本命", "まだ入れる", "次の候補", "好位置", "拾う枠", "RS上位")


# ---------------------------------------------------------------- candidates
def collect(swing: dict | None, pickup: dict | None) -> list[dict]:
    """Candidates in Positions order, each ticker once (first role wins)."""
    from swing_screener import buyable
    out: list[dict] = []
    seen: set[str] = set()

    def add(role: str, rows: list[dict]) -> None:
        for r in rows:
            t = r.get("ticker")
            if t and t not in seen and r.get("close"):
                seen.add(t)
                out.append({"t": t, "role": role, "close": float(r["close"])})

    if swing:
        reg = swing.get("regime")
        on = bool(reg) and reg.get("on") is True
        add("本命", [r for r in swing.get("core", []) if on and buyable(r)])
        add("まだ入れる", [r for r in swing.get("late", []) if on and buyable(r)])
        add("次の候補", swing.get("watch", [])[:15])
        add("好位置", swing.get("glead", [])[:10] + swing.get("glead_near", [])[:8])
    if pickup:
        add("拾う枠", [r for r in pickup.get("rows", []) if len(r.get("missing", [])) <= 1])
    if swing:  # RS leaders: trend template x RS189 top 40 (the option-wall study group)
        add("RS上位", [{"ticker": t, "close": px} for t, px, grp in swing.get("study", []) if grp == "rs189"])
    return out


def det_options(text: str) -> dict[str, dict]:
    start = text.find("window.DET=")
    if start < 0:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(text, start + len("window.DET="))
    except ValueError:
        return {}
    return {t: d["opt"] for t, d in obj.items() if isinstance(d, dict) and isinstance(d.get("opt"), dict)}


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def judge(opt: dict | None) -> tuple[bool, list[str]]:
    """(passes, reasons it does not) for one candidate's walls."""
    if not opt:
        return False, ["オプションなし"]
    why = []
    if opt.get("conf") != "OK":
        why.append("建玉が薄い")
    cwp, pwp, gfp = _f(opt.get("cwp")), _f(opt.get("pwp")), _f(opt.get("gfp"))
    if opt.get("cw") and (cwp is None or cwp < ROOM):
        why.append(f"上値の壁が近い（{_pct(cwp)}）")
    if not opt.get("pw") or pwp is None:
        why.append("下値の支えなし")
    elif not (SUPPORT[0] <= pwp <= SUPPORT[1]):
        why.append(f"支えが遠い（{_pct(pwp)}）")
    if not opt.get("gf") or gfp is None:
        why.append("境目不明")
    elif gfp >= 0:
        why.append(f"境目より下（{_pct(gfp)}）")
    return not why, why


def evaluate(cands: list[dict], opts: dict[str, dict]) -> list[dict]:
    rows = []
    for c in cands:
        o = opts.get(c["t"])
        ok, why = judge(o)
        rows.append({**c, "ok": ok, "why": why,
                     **{k: (_f(o.get(k)) if o else None) for k in ("cw", "cwp", "pw", "pwp", "gf", "gfp")}})
    return rows


# ---------------------------------------------------------------- ledger
def load_ledger(root: Path) -> dict:
    try:
        data = json.loads((root / LEDGER).read_text(encoding="utf-8"))
        if data.get("schema") == SCHEMA:
            return data
    except (OSError, ValueError):
        pass
    return {"schema": SCHEMA, "days": {}}


def record(ledger: dict, session: str, rows: list[dict]) -> dict:
    keep = ("t", "role", "close", "ok", "why", "cw", "cwp", "pw", "pwp", "gf", "gfp")
    ledger["days"][session] = {"rows": [{k: r.get(k) for k in keep} for r in rows]}
    return ledger


def forward(ledger: dict, frame: pd.DataFrame) -> dict:
    """Fill the 20-session return of rows old enough (from the frame's closes)."""
    closes = frame.pivot_table(index="date", columns="ticker", values="close").sort_index()
    dates = [d.strftime("%Y-%m-%d") for d in closes.index]
    pos = {d: i for i, d in enumerate(dates)}
    for session, day in ledger["days"].items():
        i = pos.get(session)
        if i is None or i + HORIZON >= len(dates):
            continue
        later = closes.iloc[i + HORIZON]
        for r in day["rows"]:
            if r.get("r20") is None and r["t"] in later.index and r.get("close"):
                px = _f(later[r["t"]])
                if px:
                    r["r20"] = round(px / r["close"] - 1, 5)
    return ledger


def summary(ledger: dict) -> dict:
    """Independent comparison: a ticker counts again in a group only after 20 sessions."""
    days = sorted(ledger.get("days", {}))
    order = {d: i for i, d in enumerate(days)}
    out: dict[str, Any] = {"since": days[0] if days else None, "days": len(days)}
    for flag, name in ((True, "ok"), (False, "ng")):
        last: dict[str, int] = {}
        rets = []
        for d in days:
            for r in ledger["days"][d]["rows"]:
                if bool(r.get("ok")) is not flag or r.get("r20") is None:
                    continue
                if r["t"] in last and order[d] - last[r["t"]] < HORIZON:
                    continue
                last[r["t"]] = order[d]
                rets.append(r["r20"])
        out[name] = {"n": len(rets), "avg": float(np.mean(rets)) if rets else None,
                     "win": float(np.mean([x > 0 for x in rets])) if rets else None}
    return out


def save_ledger(ledger: dict, root: Path) -> None:
    import track_record
    track_record.save(ledger, root / LEDGER)


# ---------------------------------------------------------------- display
def _pct(v: float | None) -> str:
    if v is None or not np.isfinite(v):
        return "—"
    return f"{v:+.1%}".replace("-", "−")


def _lvl(v: float | None, p: float | None) -> str:
    if not v:
        return "なし"
    px = f"${v:,.0f}" if v >= 100 else f"${v:,.2f}"
    return f"{px}（{_pct(p)}）"


def card_html(rows: list[dict] | None, summ: dict | None, session: str | None) -> str:
    e = html.escape
    if rows is None:
        body = '<div class="empty">次の更新（毎日の引け後）から表示します</div>'
        rows = []
    else:
        good = [r for r in rows if r["ok"]]
        body = "".join(
            f'<div class="opl-row" data-tkone="{e(r["t"])}"><div class="opl-main"><b>{e(r["t"])}</b>'
            f'<span class="opl-tag">{e(r["role"])}</span><span class="opl-px">${r["close"]:,.2f}</span></div>'
            f'<div class="opl-sub">上値の壁 {_lvl(r["cw"], r["cwp"])}・下値の支え {_lvl(r["pw"], r["pwp"])}・'
            f'境目 {_lvl(r["gf"], r["gfp"])}</div></div>' for r in good
        ) or '<div class="empty">該当なし（候補はどれも上に壁が近いか、支えが遠い）</div>'
        bad = [r for r in rows if not r["ok"]]
        if bad:
            body += (f'<details class="cxpl opl-bad"><summary>外れた候補（{len(bad)}）</summary><div class="cxpl-b">'
                     + "".join(f'<div><b>{e(r["t"])}</b> {e(r["role"])}：{e("・".join(r["why"]))}</div>' for r in bad)
                     + '</div></details>')
    rec = ""
    if summ and summ.get("days"):
        ok, ng = summ.get("ok") or {}, summ.get("ng") or {}
        if ok.get("n") or ng.get("n"):
            fmt = lambda g: (f'{g["n"]}件・平均{_pct(g["avg"])}・勝率{g["win"]:.0%}' if g.get("n") else "0件")
            rec = (f'<div class="opl-rec">20営業日後の騰落（銘柄ごとに20日に1回で集計）：該当 {fmt(ok)} ／ '
                   f'外れた候補 {fmt(ng)}</div>')
        else:
            rec = (f'<div class="opl-rec">記録 {summ["days"]}日分（{e(str(summ["since"]))}〜）。'
                   f'20営業日たった分から、該当と外れた候補の成績を比べて表示します。</div>')
    tickers = ",".join(r["t"] for r in rows if r.get("ok"))
    copy = (f'<button class="cp" data-tk="{e(tickers)}" onclick="copyTk(event,this)">コピー '
            f'<span class="n">{tickers.count(",") + 1}</span></button>') if tickers else ""
    asof = f"（{e(session)} 終値・建玉は前営業日）" if session else ""
    return (
        f'<div class="card ds-merged" id="{CARD_ID}"><div class="hdr"><h2>オプション配置の良い候補</h2>{copy}</div>'
        f'<div class="sub">Positionsタブの候補とRS上位のうち、上に壁がなく、損切りより上に支えがあるもの{asof}。'
        '<b>検証中</b>：建玉の過去データがないので、毎日記録して成績を確かめている。買う・買わないはPositionsタブのルールで決める。</div>'
        f'{body}{rec}'
        '<details class="cxpl"><summary>条件と見方</summary><div class="cxpl-b">'
        '対象：本命・まだ入れる・次の候補・好位置リーダー・拾う枠（形OKかあと1つ）・RS上位（トレンドテンプレート×RS189上位40）。条件（すべて）：'
        '上値の壁（コール建玉が最大の権利行使価格）が+10%以上先（最初の買い増しまで上が空いている）／'
        '下値の支え（プット建玉が最大の価格）が0〜−8%（−8%の損切りより上）／'
        '性質の境目（ディーラーのガンマが正負に入れ替わる価格）より上（値動きが落ち着きやすい側）／建玉が十分。'
        '45日以内の満期が対象。壁は値動きに合わせて動くので日々変わる。'
        '20営業日後の騰落を、該当した候補と外れた候補で比べ、差が続けて出るかで残すか決める。</div></details></div>'
    )


STYLE = ('<style id="option-layout-style">'
         f'#{CARD_ID} .opl-row{{padding:8px 0;border-top:1px solid var(--ds-line,#e0ddd5)}}'
         f'#{CARD_ID} .opl-row:first-of-type{{border-top:0}}'
         f'#{CARD_ID} .opl-main{{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap}}'
         f'#{CARD_ID} .opl-main b{{font-size:14px;letter-spacing:.02em}}'
         f'#{CARD_ID} .opl-px{{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:700}}'
         f'#{CARD_ID} .opl-sub{{font-size:11.5px;color:var(--ds-muted,#6b685e);line-height:1.55;margin-top:2px}}'
         f'#{CARD_ID} .opl-tag{{font-size:10.5px;font-weight:800;border-radius:6px;padding:1px 6px;border:1px solid;'
         'background:#efede7;color:#46443d;border-color:#dedbd2}'
         f'#{CARD_ID} .opl-rec{{font-size:11.5px;color:var(--ds-ink-2,#46443d);margin-top:6px}}'
         f'#{CARD_ID} .opl-bad .cxpl-b div{{padding:2px 0}}'
         '</style>')


def _cut_div(text: str, start: int) -> str:
    depth = 0
    for tag in re.finditer(r"<(/?)div\b[^>]*>", text[start:]):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return text[:start] + text[start + tag.end():]
    return text


def _remove_block(text: str) -> tuple[str, int | None]:
    """Remove this section (or the old 支えへの接触 one); return where it was."""
    at = None
    for marker in (f'id="{MSEC_ID}"', f'id="{CARD_ID}"'):
        m = re.search(rf'<div[^>]*{re.escape(marker)}', text)
        if m:
            at = m.start() if at is None else min(at, m.start())
            text = _cut_div(text, m.start())
    sec = text.find('<section id="t-today"')
    if sec >= 0:
        end = text.find("</section>", sec)
        m = re.search(r'<div class="msec[^"]*"[^>]*><div class="msec-l">[^<]*支えへの接触', text[sec:end])
        if m:
            at = sec + m.start()
            text = _cut_div(text, at)
            if text.startswith('<div class="card', at):
                text = _cut_div(text, at)
    text = re.sub(r'<style id="option-layout-style">.*?</style>', "", text, count=1, flags=re.S)
    return text, at


def apply(text: str, rows: list[dict] | None, summ: dict | None, session: str | None) -> str:
    text, at = _remove_block(text)
    sec = text.find('<section id="t-today"')
    if sec < 0:
        return text
    end = text.find("</section>", sec)
    pos = at if at is not None and sec < at <= end else end
    block = (f'<div class="msec ds-merged-head" id="{MSEC_ID}"><div class="msec-l">オプション配置（検証中）'
             '<span class="msec-en">Option Layout</span></div>'
             '<div class="msec-q">候補とRS上位のうち、上に壁がなく下に支えがあるもの</div></div>'
             + card_html(rows, summ, session))
    text = text[:pos] + block + text[pos:]
    return text.replace("</head>", STYLE + "</head>", 1)


def run(text: str, frame: pd.DataFrame, session: str, root: Path,
        walls_fn: Callable[[dict, str], dict] | None = None) -> str:
    """Daily refresh: judge today's candidates, record, compare forward, render."""
    import pickup_watch
    import swing_screener
    swing, pickup = swing_screener.LAST, pickup_watch.LAST
    if swing is None:
        return apply(text, None, None, session)
    cands = collect(swing, pickup)
    opts = det_options(text)
    missing = {c["t"]: c["close"] for c in cands if c["t"] not in opts}
    if missing and walls_fn is not None:
        try:
            found = walls_fn(missing, session) or {}
            for opt in found.values():
                opt["grp"] = "cand"
            if found:
                from options_walls import update_det
                text = update_det(text, found)
                opts.update(found)
        except Exception as exc:  # display-only
            print(f"option layout walls skipped: {exc!r}", flush=True)
    rows = evaluate(cands, opts)
    led = forward(record(load_ledger(root), session, rows), frame)
    save_ledger(led, root)
    print(f"option layout: {sum(r['ok'] for r in rows)}/{len(rows)} candidates pass", flush=True)
    return apply(text, rows, summary(led), session)


def main() -> int:
    """Display workflows: re-render the latest recorded day; never records."""
    import argparse
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from setups_curate import renumber
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--html", default="source-mc57.html")
    a = ap.parse_args()
    root = Path(a.root)
    page = root / a.html
    led = load_ledger(root)
    session = max(led["days"]) if led["days"] else None
    rows = led["days"][session]["rows"] if session else None
    text = page.read_text(encoding="utf-8")
    if rows is None and f'id="{CARD_ID}"' in text:
        print("option layout: no ledger yet; card left as published", flush=True)
        return 0
    page.write_text(renumber(apply(text, rows, summary(led), session)), encoding="utf-8")
    print(f"option layout: {0 if rows is None else sum(bool(r['ok']) for r in rows)} shown", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
