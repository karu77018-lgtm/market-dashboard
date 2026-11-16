"""FTDの騙しチェック (display only), placed inside the フォロースルー・デイ card.

For QQQ and SPY it replays the card's own FTD rules (build_dashboard_4.build_ftd) on the
refresh's market inputs, takes the latest FTD of the last 25 sessions and shows how often such
an FTD turned out fake in the past (a close below the FTD-day low within 25 sessions), using only
what was known that day: the day count, then the next day's move and distribution days.
Study and numbers: research/ftd-fakes-2026-11.  No order, rule or ledger changes.

The computed state is embedded in the block so the display-only workflow can re-render it.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BLOCK_ID = "ftd-check"
STATE_ID = "ftd-check-state"
STYLE_ID = "ftd-check-style"
STATE_SEED = "seed/ftd-check-state.json"
INDICES = (("QQQ", "NASDAQ100"), ("SPY", "S&P500"))
FTD_PCT = 0.0125     # same as build_dashboard_4.FTD_PCT
WINDOW = 25          # sessions a fake is judged over
DIST_DROP = 0.002    # distribution day: down 0.2% or more on higher volume

# share of FTDs that were fakes (QQQ 1999- and SPY 1993-, 239 FTDs)
BASE = 56
BY_DAY = ((4, 4, 70), (5, 5, 55), (6, 7, 58), (8, 10, 40), (11, 15, 33), (16, 10**6, 66))
NEXT_DAY = {(True, True): 77, (True, False): 44, (False, True): 44, (False, False): 32}  # (risky day, next day down)
WARNINGS = {0: 31, 1: 48, 2: 74}                                                        # at day 3
BOND = (62, 49)      # long bonds down on the FTD day: fake share with / without
DOLLAR = (65, 48)    # dollar up over the prior 20 sessions
BOND_CUT, DOLLAR_CUT = -0.07, 0.45


def _frame(market: dict, sym: str) -> pd.DataFrame | None:
    rows = (market.get("series") or {}).get(sym) or []
    if not rows:
        return None
    f = pd.DataFrame(rows)
    need = {"date", "low", "close"}
    if not need.issubset(f.columns):
        return None
    f["date"] = pd.to_datetime(f["date"].astype(str).str[:10], errors="coerce")
    f = f.dropna(subset=["date"]).drop_duplicates("date", keep="last").set_index("date").sort_index()
    for k in ("open", "high", "low", "close", "volume"):
        if k in f:
            f[k] = pd.to_numeric(f[k], errors="coerce")
    return f.dropna(subset=["close", "low"])


def events(df: pd.DataFrame) -> list[dict]:
    """Every FTD with its end (the card's rules; see build_dashboard_4.build_ftd)."""
    c, l = df["close"].to_numpy(float), df["low"].to_numpy(float)
    v = df["volume"].to_numpy(float) if "volume" in df else np.full(len(c), np.nan)
    s50 = df["close"].rolling(50).mean().to_numpy()
    hi = df["close"].rolling(252, min_periods=252).max().to_numpy()
    with np.errstate(invalid="ignore"):
        corr = np.where(np.isnan(s50), False, (c < s50) | (c / hi - 1 <= -0.08))
    low_v = day1 = None
    cur: dict | None = None
    armed, post_max, below50, out = False, np.nan, 0, []
    for j in range(1, len(c)):
        cj, cp, lj = c[j], c[j - 1], l[j]
        if cur is not None:
            post_max = cj if not np.isfinite(post_max) else max(post_max, cj)
            if np.isfinite(s50[j]):
                below50 = below50 + 1 if cj < s50[j] else 0
                armed = armed or cj >= s50[j]
            deep = np.isfinite(post_max) and cj / post_max - 1 <= -0.08
            if cj < cur["low"]:
                why = "low"
            elif armed and (deep or below50 >= 5):
                why = "new"
            else:
                continue
            cur.update(end=j, why=why)
            out.append(cur)
            cur, armed, below50, post_max = None, False, 0, np.nan
            day1, low_v = None, lj
            continue
        if day1 is not None:
            if lj < low_v:
                low_v, day1 = lj, None
                continue
            att = j - day1 + 1
            if att >= 4 and np.isfinite(v[j]) and np.isfinite(v[j - 1]) and cj / cp - 1 >= FTD_PCT and v[j] > v[j - 1]:
                cur = {"i": j, "day": att, "pct": cj / cp - 1, "low": lj}
                armed, below50, post_max = False, 0, cj
            continue
        if not corr[j]:
            low_v = None
            continue
        if low_v is None or lj < low_v:
            low_v = lj
            if cj > cp:
                day1 = j
        elif cj > cp:
            day1 = j
    if cur is not None:
        cur.update(end=None, why=None)
        out.append(cur)
    return out


def _ret(s: pd.Series | None, day: pd.Timestamp, n: int) -> float | None:
    if s is None or day not in s.index:
        return None
    i = s.index.get_loc(day)
    if i < n or not s.iloc[i - n]:
        return None
    return float(s.iloc[i] / s.iloc[i - n] - 1) * 100


def check(df: pd.DataFrame, tlt: pd.Series | None = None, usd: pd.Series | None = None) -> dict | None:
    """The latest FTD of the last WINDOW sessions and what is known about it today."""
    ev = events(df)
    last = len(df) - 1
    ev = [e for e in ev if last - e["i"] <= WINDOW]
    if not ev:
        return None
    e = ev[-1]
    i, c, v = e["i"], df["close"].to_numpy(float), df["volume"].to_numpy(float)
    end = e["end"] if e["end"] is not None else None
    known = (end if end is not None else last) - i            # sessions observed after the FTD
    d0 = df.index[i]
    risky = e["day"] <= 7 or e["day"] >= 16
    out: dict[str, Any] = {"date": str(d0.date()), "day": int(e["day"]), "pct": round(float(e["pct"]) * 100, 2),
                           "low": round(float(e["low"]), 2), "close": round(float(c[i]), 2), "risky": bool(risky),
                           "age": int(last - i), "broken": None, "next_down": None, "dist": None, "warnings": None,
                           "bond": _ret(tlt, d0, 1), "usd": _ret(usd, d0, 20)}
    if end is not None:
        out["broken"] = {"date": str(df.index[end].date()), "after": int(end - i), "why": e["why"]}
    k = min(known, 3)
    if k >= 1:
        out["next_down"] = bool(c[i + 1] < c[i])
        dist = any(c[i + t] < c[i + t - 1] * (1 - DIST_DROP) and v[i + t] > v[i + t - 1] for t in range(1, k + 1))
        out["dist"] = bool(dist)
        if k >= 3:
            out["warnings"] = int(out["next_down"]) + int(dist)
    return out


def odds(r: dict) -> tuple[int | None, str]:
    """Past share of fakes for what is known now, and on what it is based."""
    if r.get("broken"):
        return None, ""
    if r["age"] >= WINDOW:
        return None, ""
    if r.get("warnings") is not None:
        n = r["warnings"]
        return WARNINGS[n], f"3日目までの警告{n}個（翌日マイナス・売り抜け日）"
    if r.get("next_down") is not None:
        return NEXT_DAY[(r["risky"], r["next_down"])], ("日数" + ("リスク高め" if r["risky"] else "は良好") + "・翌日" + ("マイナス" if r["next_down"] else "プラス"))
    for lo, hi, p in BY_DAY:
        if lo <= r["day"] <= hi:
            return p, f'Day{r["day"]}'
    return BASE, ""


def build_state(market: dict, session: str | None = None) -> dict | None:
    out: dict[str, Any] = {"session": None, "rows": []}
    tlt = _frame(market, "TLT")
    usd = _frame(market, "DX-Y.NYB")
    for sym, label in INDICES:
        df = _frame(market, sym)
        if df is None or len(df) < 260 or "volume" not in df:
            continue
        if session:
            df = df[df.index <= pd.Timestamp(session)]
        out["session"] = out["session"] or str(df.index[-1].date())
        r = check(df, None if tlt is None else tlt["close"], None if usd is None else usd["close"])
        out["rows"].append({"sym": sym, "label": label, "ftd": r})
    return out if out["rows"] else None


# ---------------------------------------------------------------- rendering
def _md(day: str) -> str:
    t = pd.Timestamp(day)
    return f"{t.month}/{t.day}"


STYLE = (
    f'<style id="{STYLE_ID}">'
    '.ftd-chk{margin:10px 0 2px;padding-top:9px;border-top:1px dashed var(--ds-line,#dedbd2)}'
    '.ftd-chk .fc-h{font-size:13px;font-weight:800;color:var(--ds-ink,#1c1b19);margin-bottom:4px}'
    '.ftd-chk .fc-row{display:flex;gap:10px;align-items:baseline;padding:6px 0;border-bottom:1px solid var(--ds-line,#dedbd2)}'
    '.ftd-chk .fc-row:last-of-type{border-bottom:0}'
    '.ftd-chk .fc-x{flex:0 0 74px;font-size:11.5px;font-weight:700;color:var(--ds-muted,#6b685e)}'
    '.ftd-chk .fc-b{flex:1;min-width:0;font-size:12.5px;line-height:1.6;color:var(--ds-ink-2,#46443d)}'
    '.ftd-chk .fc-p{font-size:16px;font-weight:800;margin-right:6px}'
    '.ftd-chk .fc-hi{color:var(--ds-down,#b3362c)}.ftd-chk .fc-mid{color:var(--ds-warn,#8a5a12)}.ftd-chk .fc-lo{color:var(--ds-up,#17703f)}'
    '.ftd-chk .fc-s{display:block;font-size:11.5px;color:var(--ds-muted,#6b685e)}'
    '.ftd-chk details{margin-top:6px}'
    '.ftd-chk summary{font-size:12.5px;font-weight:800;cursor:pointer;color:var(--ds-accent,#2659ab)}'
    '.ftd-chk ul{margin:4px 0 2px;padding-left:1.15em}'
    '.ftd-chk li{font-size:12.5px;line-height:1.6;margin:2px 0;color:var(--ds-ink-2,#46443d)}'
    '.ftd-chk .fc-note{font-size:11.5px;color:var(--ds-muted,#6b685e);line-height:1.55;margin-top:4px}'
    '.ftd-chk .fc-end{display:none}'
    '</style>'
)


def row_html(row: dict) -> str:
    e = html.escape
    r = row.get("ftd")
    head = f'<div class="fc-row"><span class="fc-x">{e(row["label"])}</span><div class="fc-b">'
    if r is None:
        return head + f'直近{WINDOW}営業日にFTDはありません。</div></div>'
    when = f'{_md(r["date"])}点灯・Day{r["day"]}・+{r["pct"]:.1f}%'
    if r.get("broken"):
        b = r["broken"]
        what = "FTD日の安値を終値で割れ" if b["why"] == "low" else "再び調整入り"
        return head + (f'<span class="fc-p fc-hi">騙し</span>{when}。{b["after"]}営業日後の{_md(b["date"])}に{what}。'
                       '<span class="fc-s">次のFTDを待つ局面です。</span></div></div>')
    if r["age"] >= WINDOW:
        return head + f'<span class="fc-p fc-lo">通過</span>{when}。{WINDOW}営業日割れずに経過（騙しの判定期間を通過）。</div></div>'
    p, basis = odds(r)
    cls = "fc-hi" if p >= 60 else "fc-mid" if p >= 45 else "fc-lo"
    signs = []
    if r.get("next_down") is not None:
        signs.append("翌日" + ("マイナス" if r["next_down"] else "プラス"))
    if r.get("dist") is not None:
        signs.append("売り抜け日" + ("あり" if r["dist"] else "なし"))
    extra = []
    if r.get("bond") is not None and r["bond"] <= BOND_CUT:
        extra.append(f'FTD当日に長期債が下落（{r["bond"]:+.1f}%）'.replace("-", "−"))
    if r.get("usd") is not None and r["usd"] >= DOLLAR_CUT:
        extra.append(f'直前20日でドル高（{r["usd"]:+.1f}%）'.replace("-", "−"))
    ref = (f'<span class="fc-s">参考の逆風：{"、".join(extra)}。過去は長期債安で騙し{BOND[0]}%（他{BOND[1]}%）、'
           f'ドル高で{DOLLAR[0]}%（他{DOLLAR[1]}%）。</span>' if extra else "")
    return head + (f'<span class="fc-p {cls}">騙し {p}%</span>{when}（{r["age"]}日目）'
                   f'<span class="fc-s">根拠：{e(basis)}{"・" + "・".join(signs) if signs and "翌日" not in basis else ""}。'
                   f'撤退の目安＝FTD日の安値 {r["low"]:.2f} を終値で割ったら。</span>{ref}</div></div>')


ENTRY = (
    '<details><summary>FTD後の入り方（過去の検証）</summary><ul>'
    '<li>FTDは引けで確定するので、入るのは翌日の寄り。平均で良かったのは「翌日の寄りで入り、終値でFTD日の安値を割ったら次の寄りで撤退」。'
    '指数で1回あたり平均+1.2%、最悪−11.6%（撤退しないと平均+2.1%・最悪−39%）。FTD日の終値で入れた場合とほぼ同じでした。</li>'
    '<li>撤退をFTD日安値の逆指値にしても平均+1.1%。2010年以降の最悪は−4.3%（終値で判断すると−9.7%）。</li>'
    '<li>確認を待つ（翌日プラスなら翌々日に入る、3日目に警告なしなら4日目に入る）と、負けは減るが取り逃しのほうが大きく、平均は+0.3〜+0.6%に下がった（前半・後半とも）。</li>'
    '<li>騙しになりやすいDay4〜7・Day16以降は量を半分にすると、平均+1.1%のまま、投資している期間が3分の2に減った（効率が最も良い）。</li>'
    '<li>3倍（TQQQ相当）では、撤退ありの最悪−34%、撤退なしは−83%。レバレッジでは撤退ラインが必須。</li>'
    '<li>スイング候補（本命）の個別株は、FTD後の警告の有無で成績が一貫して変わらなかった。個別株はこれまでのルールのまま。</li>'
    '</ul></details>'
)


def block_html(state: dict) -> str:
    raw = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    rows = "".join(row_html(r) for r in state.get("rows", []))
    return (f'<div class="ftd-chk" id="{BLOCK_ID}"><div class="fc-h">騙しチェック</div>{rows}{ENTRY}'
            f'<div class="fc-note">騙し＝{WINDOW}営業日以内に終値でFTD日の安値を割ること。過去のFTDの{BASE}%が騙し（QQQ 1999年〜・SPY 1993年〜の239回）。'
            '分かっていることだけで出した過去の割合で、予測の保証ではありません。表示のみで、売買ルールは変えません。'
            f'{html.escape(state.get("session") or "")} 終値時点。</div>'
            f'<script id="{STATE_ID}" type="application/json">{raw}</script><span class="fc-end"></span></div>')


BLOCK_RE = re.compile(rf'<div class="ftd-chk" id="{BLOCK_ID}">.*?<span class="fc-end"></span></div>', re.S)
STATE_RE = re.compile(rf'<script id="{STATE_ID}" type="application/json">(.*?)</script>', re.S)
STYLE_RE = re.compile(rf'<style id="{STYLE_ID}">.*?</style>', re.S)


def _insert_at(text: str) -> int | None:
    """Just after the last index row of the フォロースルー・デイ card."""
    h = text.find("<h2>フォロースルー・デイ")
    if h < 0:
        return None
    nxt = text.find('<div class="card', h)
    region = text[h:nxt if nxt > 0 else len(text)]
    last = region.rfind('<div class="ftd-row">')
    if last < 0:
        return None
    m = re.compile(r'<div class="ftd-row">.*?<div class="dddays">.*?</div></div>', re.S).match(region, last)
    return h + m.end() if m else None


def apply(text: str, state: dict | None) -> str:
    if not state:
        return text
    block = block_html(state)
    if BLOCK_RE.search(text):
        out = BLOCK_RE.sub(lambda _: block, text, count=1)
    else:
        at = _insert_at(text)
        if at is None:
            print("ftd check: FTD card not found; block not inserted", flush=True)
            return text
        out = text[:at] + block + text[at:]
    out = STYLE_RE.sub("", out)
    return out.replace("</head>", STYLE + "</head>", 1) if "</head>" in out else out


def embedded_state(text: str) -> dict | None:
    m = STATE_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1).replace("<\\/", "</"))
    except ValueError:
        return None


def rerender(text: str, root: Path) -> str:
    """Display-only path: from the state stored in the page, or the committed seed of this session."""
    state = embedded_state(text)
    if state is None:
        try:
            seed = json.loads((root / STATE_SEED).read_text(encoding="utf-8"))
            manifest = json.loads((root / "latest-manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return text
        if seed.get("session") != manifest.get("session_date"):
            return text
        state = seed
    return apply(text, state)


def run(text: str, root: Path, session: str) -> str:
    import decline_anatomy  # same market inputs loader
    market = decline_anatomy.load_market(root)
    state = build_state(market, session) if market else None
    if state is None:
        print("ftd check: market inputs not usable; keeping the page as is", flush=True)
        return rerender(text, root)
    print("ftd check: " + "; ".join(f'{r["sym"]} {(r["ftd"] or {}).get("date")} day{(r["ftd"] or {}).get("day")} '
                                     f'odds={odds(r["ftd"])[0] if r["ftd"] else None}' for r in state["rows"]), flush=True)
    return apply(text, state)
