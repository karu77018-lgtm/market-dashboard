"""Rules tab: the swing rules shown on the dashboard (replaces the old Core 12 text).

Display only.  The numbers quoted here come from the offline backtests
(2015-01 to 2026-08, current listings, QQQ 200-day regime filter, 6-position
sizing with adds at +10% and +20%).
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


# 6-position rule: (year, stock-only %, idle cash QQQ 50% %, QQQ price %, stock-only intra-year max DD %, trades, win %)
# The "QQQ込" column shown on the page is the breakout-health switch (breakout_health.YEARLY).
YEARLY = [
    (2015, 2.1, 7.8, 8.7, -6.4, 16, 38), (2016, -7.6, -2.4, 5.9, -7.8, 18, 28),
    (2017, 11.5, 19.5, 31.5, -11.0, 34, 29), (2018, 13.1, 11.6, -1.0, -13.0, 23, 35),
    (2019, 5.9, 17.6, 37.8, -6.9, 24, 29), (2020, 145.2, 154.6, 47.6, -20.7, 39, 46),
    (2021, 38.7, 51.1, 26.8, -16.3, 36, 22), (2022, -6.9, -16.1, -33.1, -9.3, 12, 17),
    (2023, 11.2, 28.3, 53.8, -21.4, 46, 20), (2024, 136.4, 141.6, 24.8, -22.2, 57, 30),
    (2025, 36.1, 43.6, 20.2, -31.2, 34, 38), (2026, 79.0, 86.8, 16.7, -19.0, 18, 44),
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
        ["同時保有", "コア最大6銘柄（テーマ枠込みで最大9）"],
        ["サイズ", "最初は資金の約1/6（16.7%）。損切り8%なので1回のリスクは資金の約1.3%"],
        ["買い", "本命が出た日の終値"],
        ["損切り", "買値−8%（窓を開けて下回ったら始値）"],
        ["買い増し", "終値が買値+10%で同額、+20%でもう一度同額。1銘柄の上限は資金の40%"],
        ["手仕舞い", "安値21EMAを割って引けたら。日数制限なし"],
        ["余剰資金", "50%をQQQ。ブレイク成功度が不調かつQQQが200日線より上の日は100%（下の7）"],
    ])
    card = [
        "<b>本命</b>：今日買うもの",
        "<b>まだ入れる</b>：1〜2日前に本命になり、成立時の終値+3%以内・損切りや安値21EMA割れなし・当日+3%未満のもの。損切りは今の価格から−8%",
        "<b>次の候補</b>：選定OKで形待ち。残り条件を「あと何%」で表示。並びは 優先S・A×あと1 → B×あと1 → S・A×あと2 → その他。地合い停止中も表示",
        "<b>好位置リーダー（検討可）</b>：本命の一歩外のリーダー（TT・売買代金上位50%・RS189とRS63が上位20%・週足SAR転換8週以内・HL→ラインの50〜75%・形OK）。"
        "検証ではPF 2.12・年19件（本命と重なるもの除く）。ただし本命の6枠に機械的に混ぜると年率が42.4%→38〜40%に下がる（悪い年の負けは浅くなる）ので監視のみ。"
        "空き枠があるときに裁量で入るなら、本命と同じ売買ルールで6枠に含める。形が1つ足りないものは「あと1つ」で表示",
        "<b>テーマ枠</b>：下の別枠ルール",
        "<b>条件OKだが買わない</b>（折りたたみ）：週足SARベアかHL寄りのもの",
    ]
    dont = [
        "3銘柄以下まで絞らない（値動きのブレと機会の減少で、かえって年率が下がる）",
        "最初から大きく張らない（5銘柄×25%は買う銘柄の運で年率29〜39%とぶれる。勝ちに買い増して集中するほうが安定）",
        "優先度で買う・買わないを決めない（S・Aだけに絞ると件数が減って年率が大きく落ちる）",
        "ピボットから伸びた銘柄も外さない（外すとDDは浅くなるが年率が下がる）",
        "連敗した銘柄も休ませない（連敗の次の1回はむしろPFが高い）",
        "途中で利確しない・建値ストップを使わない（+25%で建値へ動かすルールは効果なし）",
        "当日・前日+3%を超えた銘柄を追わない",
        "地合い停止中に新規で買わない",
    ]
    li = lambda items: '<ul class="rules">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>"
    return (
        '<div class="card"><h2>スイングルール（新ルール） <span class="h2en">Swing Rules</span></h2>'
        '<div class="sub" style="color:#467ed6">売買代金トップの中から一番強い銘柄を、形がそろった日の終値で買う。'
        '最大6銘柄に絞り、損は−8%で切り、勝ちは+10%・+20%で買い増して安値21EMAを割るまで伸ばす。毎日の候補はPositionsタブ「スイング候補」。</div>'
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
        + '<div class="rnote">集中度の比較（余剰資金のQQQ切替込み）：最大10銘柄・+10%で半分買い増し＝年率32.4%・DD−23.5%／'
        '<b>最大6銘柄・+10%と+20%で同額買い増し＝年率42.4%・DD−30.3%</b>。買う銘柄の優先順位をランダムにしても年率31〜38%（中央36%）。'
        '選び方はRS189順が最良（RS63順・RS21順・値幅順より上）。集中の効果は2021年以降の強いリーダー相場で大きく、'
        '下落の幅が耐えにくくなったら銘柄数を8〜10に戻す。</div>'
        + '<div class="rh">5. テーマ枠（別枠）</div>'
        '<div class="sub">窓+5〜20%・終値+5%以上・出来高3〜15倍・上半分引け・50日線上・値幅3〜7%・相関の高い銘柄のRS平均50〜90。'
        'リスク0.5%、同時3銘柄、60営業日で手仕舞い。</div>'
        '<div class="rh">6. カードの見方</div>' + li(card)
        + '<div class="rh">7. 余剰資金の配分（ブレイク成功度）</div>'
        '<div class="sub"><b>ブレイク成功度</b>＝直近63営業日の本命シグナル（地合いは問わない）が10日後に平均何%動いたか。'
        '0%以上＝好調、マイナス＝不調。<b>不調かつQQQが200日線より上の日は余剰資金を100%QQQ</b>、それ以外は50%。'
        '個別株の売買は変えない。DailyタブとPositionsタブに今日の値を表示。</div>'
        + li(["指数は上がるのに勢い株が伸びない年（2016・2021・2023年）を不調と判定し、その年をQQQで埋める",
              "未来のデータは使わない（10日後の結果が出たシグナルだけで計算）。ただし63日平均を10日遅れで見るので、判定の切り替わりは数週間遅れる（好調・不調は平均54日続く）",
              "年率38.5%→42.4%、最大DD−30.3%のまま。ただし平均QQQ比率は約63%で、63%固定でも40.0%。判定そのものの上乗せは年+1〜2pt程度（日数・基準を変えた36通り中35通りでプラス）",
              "QQQが200日線より下ではQQQを増やさない（2022年のような下げで傷を深くしない）",
              "不調でも新規エントリーは止めない・リスクも減らさない（止めると年率が下がる）",
              "サイトのF1〜F3・MC57・リーダーの強さは「崩れるか」の計器で、この切り替えには効かない"])
        + '<div class="rh">8. 拾う枠（監視・参考）</div>'
        '<div class="sub">本体（売買代金上位5%）の外で、しっかり伸びている中堅株の監視リスト。Positionsタブの別カードに表示。<b>資金は割り当てない</b>（裁量で拾う場合の目安）。</div>'
        + li(["候補：株価$5以上・売買代金$10M以上／RS21・63・189がすべて85以上／52週安値の2倍以上・高値から−35%以内／週足SARブル8週以内／1日の値幅4%以上／業種の強さ上位半分／地合いOK",
              "入るなら本体と同じ形がそろった日（形OK）。手仕舞いは50日線割れ、損切り−10%",
              "形OKのPF 1.92（2015〜18年 1.85／2019〜22年 1.98／2023〜26年 1.89）。ただし単独運用は年率約14%・最大DD−45%で、本体に足すと全体の伸びは下がる",
              "業績（EPS・売上の伸びや加速）は成績をほとんど改善しなかった。値動きに出る特徴（3期間RS・SAR転換直後・2倍後のベース・高ボラ・強い業種）が効く"])
        + '<div class="rh">やらないこと</div>' + li(dont)
        + '<div class="rh">成績（単年）</div>'
        '<div class="rnote">個別株＝個別株だけ、QQQ込＝余剰資金を7のルールでQQQに置いた場合。年内DD＝個別株だけの年内最大下落。2026年は1〜8月。</div>'
        + _yearly()
        + '<div class="rwarn"><b>成績</b>（2015年1月〜2026年8月、地合い込み・最大6銘柄ルール）：個別株だけで年率32.1%・最大DD−31.2%（約26倍）。'
        '余剰資金を7のルールでQQQに置くと年率42.4%・DD−30.3%（約61倍、50%固定なら38.5%）。負けた年は2016年（個別株のみ）と2022年。<br>'
        '現存銘柄だけで検証（上場廃止銘柄は未検証）、税金・テーマ枠は含まない。'
        '集中の上乗せは2021年以降が大きく（2015〜20年は年率21%→27%）、今後も同じとは限らない。売買の推奨ではなく検証結果のまとめ。</div></div>'
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
