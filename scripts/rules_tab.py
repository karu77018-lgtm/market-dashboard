"""Rules tab: the swing rules shown on the dashboard (replaces the old Core 12 text).

Display only.  The numbers quoted here come from the offline backtests
(stock-only portfolio, 2015-01 to 2026-08, with the QQQ 200-day regime filter).
"""
from __future__ import annotations

import re
from typing import Any

STYLE = ('<style>#t-rules .rtb{width:100%;border-collapse:collapse;font-size:12px;margin:4px 0 6px}'
         '#t-rules .rtb th,#t-rules .rtb td{border-bottom:1px solid #e0ddd5;padding:5px 6px;text-align:left;'
         'vertical-align:top;line-height:1.5;white-space:normal;word-break:break-word;overflow-wrap:anywhere}'
         '#t-rules .rtb{table-layout:auto;min-width:0;max-width:100%}#t-rules .rtb th{font-size:10.5px;color:#706e64;font-weight:700}'
         '#t-rules .rtb td:first-child{font-weight:800;white-space:nowrap;color:#1b1a18}#t-rules .rtb th:first-child{white-space:nowrap}'
         '#t-rules .rtb td.n{white-space:nowrap;text-align:right;font-variant-numeric:tabular-nums}'
         '#t-rules .rreg{font-size:12px;font-weight:700;padding:7px 10px;border-radius:8px;margin:2px 0 6px}'
         '#t-rules .rreg.on{background:rgba(34,197,94,.14);color:#18813d;border:1px solid rgba(34,197,94,.45)}'
         '#t-rules .rreg.off{background:rgba(239,68,68,.10);color:#c62828;border:1px solid rgba(239,68,68,.4)}'
         '#t-rules .rreg span{font-weight:500;color:#565243;font-size:11px}'
         '#t-rules .rnote{font-size:11px;color:#706e64;line-height:1.55;margin:2px 0 4px}'
         '#t-rules .rwarn{font-size:11px;line-height:1.6;color:#565243;background:#e9e7e0;border-radius:8px;'
         'padding:8px 10px;margin-top:12px}</style>')


def _table(head: list[str], rows: list[list[str]], num_cols: tuple[int, ...] = ()) -> str:
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join(
        "<tr>" + "".join(f'<td class="n">{c}</td>' if i in num_cols else f"<td>{c}</td>"
                         for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<table class="rtb"><tr>{th}</tr>{body}</table>'


# (year, stock-only %, with QQQ 50% %, QQQ price %, stock-only intra-year max DD %, trades, win %)
# The "QQQ込" column shown on the page is the breakout-health switch (breakout_health.YEARLY).
YEARLY = [
    (2015, -0.1, 5.9, 8.7, -4.9, 21, 43), (2016, -5.7, -1.0, 5.9, -4.3, 19, 26),
    (2017, 7.6, 17.8, 31.5, -5.7, 39, 33), (2018, 7.8, 7.0, -1.0, -9.3, 25, 36),
    (2019, 3.9, 17.0, 37.8, -4.9, 24, 29), (2020, 98.4, 105.9, 47.6, -19.6, 52, 44),
    (2021, 12.5, 22.0, 26.8, -17.5, 44, 20), (2022, -5.0, -16.2, -33.1, -6.9, 13, 15),
    (2023, 0.4, 16.9, 53.8, -20.0, 59, 22), (2024, 96.6, 103.0, 24.8, -15.9, 74, 35),
    (2025, 25.0, 31.9, 20.2, -24.5, 43, 40), (2026, 76.0, 83.5, 16.7, -17.1, 26, 46),
]


def _pct(v: float) -> str:
    color = "#c62828" if v < 0 else "#18813d" if v > 0 else "#565243"
    return f'<span style="color:{color}">{v:+.1f}%</span>'.replace("-", "−")


def _yearly() -> str:
    from breakout_health import YEARLY as SWITCH
    sw = {y: b for y, _, b in SWITCH}
    rows = [[str(y) if y < 2026 else "2026*", _pct(a), _pct(sw.get(y, b)), _pct(q), f"{d:.1f}%".replace("-", "−")]
            for y, a, b, q, d, n, w in YEARLY]
    return _table(["年", "個別株", "QQQ込", "QQQ", "年内DD"], rows, num_cols=(1, 2, 3, 4))


def _health_line(health: dict[str, Any] | None, regime: dict[str, Any] | None) -> str:
    try:
        from breakout_health import _fmt, allocation
    except Exception:
        return ""
    if not health or health.get("on") is None:
        return ""
    pct, why = allocation(health, regime)
    word = "好調" if health["on"] else "不調"
    return (f'<div class="rreg {"on" if health["on"] else "off"}">今日のブレイク成功度：{_fmt(health["value"])}（{word}）'
            f' <span>→ 余剰資金のQQQ {pct}%{"" if health["on"] else f"（{why}）"}</span></div>')


def _regime_line(regime: dict[str, Any] | None) -> str:
    if not regime or regime.get("on") is None:
        return ""
    on = bool(regime["on"])
    detail = ""
    if regime.get("close") and regime.get("ma"):
        detail = f' <span>QQQ {regime["close"]:.2f} / 200日線 {regime["ma"]:.2f}（{regime.get("date", "")}）</span>'
    label = "今日の地合い：新規OK" if on else "今日の地合い：新規停止"
    return f'<div class="rreg {"on" if on else "off"}">{label}{detail}</div>'


def rules_html(regime: dict[str, Any] | None = None, health: dict[str, Any] | None = None) -> str:
    form = _table(["条件", "基準", "意味"], [
        ["値幅", "10日平均値幅÷50日平均値幅 ≤ 0.90", "値動きが縮んでいる"],
        ["出来高", "5日平均出来高÷50日平均 ≤ 0.90", "売りが枯れている"],
        ["当日", "+3%未満", "追いかけない"],
        ["前日", "+3%以下", "追いかけない"],
    ])
    tiers = _table(["優先", "中身", "PF"], [
        ["S", "好位置（HL→ラインの50〜75%）×週足SAR転換0〜5週", "15.0"],
        ["A", "週足SAR転換2〜5週（位置は問わない）", "2.97"],
        ["B", "SAR転換週・1週目・6〜8週", "1.80"],
        ["C", "SAR9週以降", "1.53"],
        ["D", "SARベア・HL構造なし", "1.05"],
    ], num_cols=(2,))
    trade = _table(["場面", "やること"], [
        ["サイズ", "1銘柄のリスクは資金の1%。損切り8%なので1銘柄＝資金の約12.5%"],
        ["買い", "本命が出た日の終値"],
        ["損切り", "買値−8%（窓を開けて下回ったら始値）"],
        ["買い増し", "終値が買値+10%で、持ち株の半分を1回だけ"],
        ["手仕舞い", "安値21EMAを割って引けたら。日数制限なし"],
        ["同時保有", "コア最大10銘柄（テーマ枠込みで最大15）"],
        ["余剰資金", "50%をQQQ。ブレイク成功度が不調かつQQQが200日線より上の日は100%（下の7）"],
    ])
    card = [
        "<b>本命</b>：今日買うもの",
        "<b>まだ入れる</b>：1〜2日前に本命になり、成立時の終値+3%以内・損切りや安値21EMA割れなし・当日+3%未満のもの。損切りは今の価格から−8%",
        "<b>次の候補</b>：選定OKで形待ち。残り条件を「あと何%」で表示。並びは 優先S・A×あと1 → B×あと1 → S・A×あと2 → その他。地合い停止中も表示",
        "<b>テーマ枠</b>：下の別枠ルール",
        "<b>条件OKだが買わない</b>（折りたたみ）：週足SARベアかHL寄りのもの",
    ]
    dont = [
        "優先度で買う・買わないを決めない（S・Aだけに絞ると個別株の年率が12%に落ちる）",
        "ピボットから伸びた銘柄も外さない（外すとDDは浅くなるが、年率22.3%→約21%に下がる）",
        "連敗した銘柄も休ませない（2連敗で20日休むと年率22.4%→18.8%。連敗の次の1回はむしろPFが高い）",
        "最初からフルロットで買わない（年率14.5%・DD−30%。買い増し方式のほうが伸びて浅い）",
        "途中で利確しない・建値ストップを使わない（+25%で建値へ動かすルールは効果なし）",
        "当日・前日+3%を超えた銘柄を追わない",
        "地合い停止中に新規で買わない",
    ]
    li = lambda items: '<ul class="rules">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>"
    return (
        '<div class="card"><h2>スイングルール（新ルール） <span class="h2en">Swing Rules</span></h2>'
        '<div class="sub" style="color:#467ed6">売買代金トップの中から一番強い銘柄を、形がそろった日の終値で買う。'
        '損は−8%で切り、勝ちは買い増して安値21EMAを割るまで伸ばす。毎日の候補はPositionsタブ「スイング候補」。</div>'
        + _regime_line(regime) + _health_line(health, regime)
        + '<div class="rh">0. 地合い</div>'
        '<div class="sub">QQQが200日線より上の日だけ新規で買う。割れている日は新規停止（持ち株は通常の手仕舞いルールのまま）。</div>'
        '<div class="rh">1. 選定（3つすべて）</div>'
        + li(["<b>トレンドテンプレート</b>：株価＞50日線＞150日線＞200日線、200日線が20日前より上、52週高値から−25%以内",
              "<b>売買代金</b>：50日平均が上位5%",
              "<b>RS189</b>：189日リターンが上位10%"])
        + '<div class="rnote">順位は株価$10以上・50日平均売買代金$20M以上の銘柄の中で付ける。</div>'
        '<div class="rh">2. 形（4つすべて＝全条件OK）</div>' + form
        + '<div class="rh">3. 本命＝買うもの</div>'
        '<div class="sub">全条件OK × <b>週足SARブル</b> × <b>HL寄り（HL→ラインの0〜50%）以外</b> × 地合いOK。'
        '本命は優先度に関係なく全部買う。枠が足りない日はRS189の高い順。</div>'
        '<div class="rnote">優先度は並び順とバッジだけに使う。週足SARは0.02・0.02・0.08、金曜終値で確定した週のみ。</div>'
        + tiers
        + '<div class="rh">4. 売買</div>' + trade
        + '<div class="rh">5. テーマ枠（別枠）</div>'
        '<div class="sub">窓+5〜20%・終値+5%以上・出来高3〜15倍・上半分引け・50日線上・値幅3〜7%・相関の高い銘柄のRS平均50〜90。'
        'リスク0.5%、同時3銘柄、60営業日で手仕舞い。</div>'
        '<div class="rh">6. カードの見方</div>' + li(card)
        + '<div class="rh">7. 余剰資金の配分（ブレイク成功度）</div>'
        '<div class="sub"><b>ブレイク成功度</b>＝直近63営業日の本命シグナル（地合いは問わない）が10日後に平均何%動いたか。'
        '0%以上＝好調、マイナス＝不調。<b>不調かつQQQが200日線より上の日は余剰資金を100%QQQ</b>、それ以外は50%。'
        '個別株の売買は変えない。DailyタブとPositionsタブに今日の値を表示。</div>'
        + li(["指数は上がるのに勢い株が伸びない年（2016・2021・2023年）を不調と判定し、その年をQQQで埋める",
              "年率28.5%→32.3%、最大DD−23.5%のまま（同じ平均QQQ比率の固定配分より年率+2.2pt・DDも浅い）",
              "QQQが200日線より下ではQQQを増やさない（2022年のような下げで傷を深くしない）",
              "不調でも新規エントリーは止めない・リスクも減らさない（止めると年率が下がる）",
              "サイトのF1〜F3・MC57・リーダーの強さは「崩れるか」の計器で、この切り替えには効かない"])
        + '<div class="rh">やらないこと</div>' + li(dont)
        + '<div class="rh">成績（単年）</div>'
        '<div class="rnote">個別株＝個別株だけ、QQQ込＝余剰資金を7のルールでQQQに置いた場合。年内DD＝個別株だけの年内最大下落。2026年は1〜8月。</div>'
        + _yearly()
        + '<div class="rwarn"><b>成績</b>（2015年1月〜2026年8月、地合い込み）：個別株だけで年率22.3%・最大DD−24.5%（約10.5倍）。'
        '余剰資金を7のルールでQQQに置くと年率32.3%・DD−23.5%（約26倍、50%固定なら28.5%）。<br>'
        '現存銘柄だけで検証（上場廃止銘柄は未検証）、税金・テーマ枠は含まない。'
        '2021〜24年のように地合いの悪い期間は弱い。売買の推奨ではなく検証結果のまとめ。</div></div>'
    )


SECTION = re.compile(r'(<section id="t-rules">)(.*?)(</section>)', re.S)


def apply(text: str, regime: dict[str, Any] | None = None, health: dict[str, Any] | None = None) -> str:
    """Replace the whole Rules tab content.  No-op if the tab is missing."""
    m = SECTION.search(text)
    if not m:
        return text
    out = text[:m.start(2)] + rules_html(regime, health) + text[m.end(2):]
    if STYLE not in out:
        out = out.replace("</head>", STYLE + "</head>", 1)
    return out
