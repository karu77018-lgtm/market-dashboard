"""Rules tab: the swing rules shown on the dashboard (replaces the old Core 12 text).

Display only.  The numbers quoted here come from the offline backtests
(2015-01 to 2026-08, current listings, QQQ 200-day regime filter, 6-position
sizing with adds at +10% and +20%).  Since October 2026 the idle money goes to
the TQQQ rule (section 9, tqqq_rule.py) instead of QQQ.
"""
from __future__ import annotations

import re
from typing import Any

# Single source of the adopted rule version.  Every rule-dependent card carries
# it as data-rule so publication can refuse a page that mixes versions.
RULE_ID = "swing-v3.1-tqqq-sleeve"
RULE_CARDS = ("rules-card", "mc57-swing-screener", "mc57-breakout-health", "mc57-pickup-watch", "track-record-card")
_RULE_ATTR = re.compile(r'<div[^>]*\bid="([^"]+)"[^>]*\bdata-rule="([^"]*)"|<div[^>]*\bdata-rule="([^"]*)"[^>]*\bid="([^"]+)"')


def rule_versions(text: str) -> dict[str, str]:
    """{card id: data-rule} for the rule-dependent cards present in the page."""
    out: dict[str, str] = {}
    for m in _RULE_ATTR.finditer(text):
        cid, rule = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        if cid in RULE_CARDS:
            out[cid] = rule
    return out


def rule_problems(text: str, required: tuple[str, ...] = ("rules-card", "mc57-swing-screener")) -> list[str]:
    found = rule_versions(text)
    problems = [f"{cid}: missing" for cid in required if cid not in found]
    for cid in RULE_CARDS:
        if f'id="{cid}"' in text and found.get(cid) != RULE_ID:
            problems.append(f"{cid}: rule {found.get(cid)!r} != {RULE_ID!r}")
    return problems

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
         'padding:8px 10px;margin-top:12px}'
         '#t-rules .rtb.rtb-tight th,#t-rules .rtb.rtb-tight td{padding:5px 3px}#t-rules .rtb.rtb-tight td{font-size:11.5px}</style>')


def _table(head: list[str], rows: list[list[str]], num_cols: tuple[int, ...] = ()) -> str:
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join(
        "<tr>" + "".join(f'<td class="n">{c}</td>' if i in num_cols else f"<td>{c}</td>"
                         for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<table class="rtb"><tr>{th}</tr>{body}</table>'


# 6-position rule, re-run in October 2026 on one data set (HY OAS with its real one-day publication lag):
# (year, stock-only %, idle money QQQ (section 7 switch) %, idle money TQQQ rule (section 7 switch) %,
#  QQQ price %, stock-only intra-year max DD %)
YEARLY = [
    (2015, 2.8, 9.4, 3.1, 8.7, -6.1), (2016, -7.1, 0.6, 11.8, 5.9, -7.1),
    (2017, 2.2, 14.9, 45.0, 31.5, -7.2), (2018, 19.8, 19.7, 24.5, -1.0, -12.9),
    (2019, 4.4, 19.4, 23.1, 37.8, -6.8), (2020, 87.9, 97.8, 122.2, 47.6, -21.4),
    (2021, 49.5, 72.3, 120.4, 26.8, -16.0), (2022, -6.6, -17.2, -10.1, -33.1, -9.1),
    (2023, 14.2, 41.9, 49.0, 53.8, -19.1), (2024, 140.0, 150.9, 157.2, 24.8, -20.5),
    (2025, 51.2, 62.2, 92.3, 20.2, -31.4), (2026, 75.8, 79.8, 100.5, 16.7, -19.2),
]
# (label, CAGR %, max DD %, multiple) for the same run, 2015-01 .. 2026-08
TOTALS = [("なし（個別株だけ）", 31.0, -31.4, 23), ("QQQ（旧）", 40.6, -31.6, 53),
          ("TQQQルール枠（現行）", 55.1, -33.8, 166)]


def _pct(v: float) -> str:
    color = "#c62828" if v < 0 else "#18813d" if v > 0 else "#565243"
    return f'<span style="color:{color}">{v:+.1f}%</span>'.replace("-", "−")


def _yearly() -> str:
    rows = [[str(y) if y < 2026 else "2026*", _pct(a), _pct(b), _pct(t), _pct(q), f"{d:.1f}%".replace("-", "−")]
            for y, a, b, t, q, d in YEARLY]
    table = _table(["年", "個別株", "QQQ込（旧）", "TQQQ枠込", "QQQ", "年内DD"], rows,
                   num_cols=(1, 2, 3, 4, 5)).replace('class="rtb"', 'class="rtb rtb-tight"', 1)
    return f'<div style="max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch">{table}</div>'


def _totals() -> str:
    rows = [[k, f"{c:.1f}%", f"{d:.1f}%".replace("-", "−"), f"{m}倍"] for k, c, d, m in TOTALS]
    return _table(["余剰資金", "年率", "最大DD", "約11.7年"], rows, num_cols=(1, 2, 3))


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
            f' <span>→ 余剰資金のTQQQルール枠 {pct}%{"" if health["on"] else f"（{why}）"}</span></div>')


def _regime_line(regime: dict[str, Any] | None) -> str:
    if not regime or regime.get("on") is None:
        return ('<div class="rreg off">今日の地合い：判定不可 <span>QQQの終値が取れないか日付が一致しないため、'
                '新規は停止扱い</span></div>')
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
        ["余剰資金", "50%をTQQQルール枠（下の9）。ブレイク成功度が不調かつQQQが200日線より上の日は100%（下の7）。残りは現金"],
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
        f'<div class="card" id="rules-card" data-rule="{RULE_ID}"><h2>スイングルール（新ルール） <span class="h2en">Swing Rules</span></h2>'
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
        + '<div class="rnote">集中度の比較（余剰資金をQQQ切替で置いた当時の検証）：最大10銘柄・+10%で半分買い増し＝年率32.4%・DD−23.5%／'
        '<b>最大6銘柄・+10%と+20%で同額買い増し＝年率42.4%・DD−30.3%</b>。買う銘柄の優先順位をランダムにしても年率31〜38%（中央36%）。'
        '選び方はRS189順が最良（RS63順・RS21順・値幅順より上）。集中の効果は2021年以降の強いリーダー相場で大きく、'
        '下落の幅が耐えにくくなったら銘柄数を8〜10に戻す。</div>'
        + '<div class="rh">5. テーマ枠（別枠）</div>'
        '<div class="sub">窓+5〜20%・終値+5%以上・出来高3〜15倍・上半分引け・50日線上・値幅3〜7%・相関の高い銘柄のRS平均50〜90。'
        'リスク0.5%、同時3銘柄、60営業日で手仕舞い。</div>'
        '<div class="rh">6. カードの見方</div>' + li(card)
        + '<div class="rh">7. 余剰資金の配分（ブレイク成功度）</div>'
        '<div class="sub"><b>ブレイク成功度</b>＝直近63営業日の本命シグナル（地合いは問わない）が10日後に平均何%動いたか。'
        '0%以上＝好調、マイナス＝不調。<b>不調かつQQQが200日線より上の日は余剰資金を100%TQQQルール枠</b>、それ以外は50%（残りは現金）。'
        '個別株の売買は変えない。DailyタブとPositionsタブに今日の値を表示。枠の中身（TQQQ・金・短期国債の比率）は9のルールで決まる。</div>'
        + li(["指数は上がるのに勢い株が伸びない年（2016・2021・2023年）を不調と判定し、その年を指数側（TQQQルール枠）で埋める",
              "未来のデータは使わない（10日後の結果が出たシグナルだけで計算）。ただし63日平均を10日遅れで見るので、判定の切り替わりは数週間遅れる（好調・不調は平均54日続く）",
              "QQQで検証した当初：年率38.5%→42.4%、最大DD−30.3%のまま。ただし平均QQQ比率は約63%で、63%固定でも40.0%。判定そのものの上乗せは年+1〜2pt程度（日数・基準を変えた36通り中35通りでプラス）",
              "置き先をTQQQルール枠にした再計算：年率55.1%・最大DD−33.8%（QQQのままなら40.6%・−31.6%）。資産全体に占めるTQQQは平均約30%。枠外の現金をなくして常に100%にすると57.9%・−45.0%（DDの底は2025年4月）",
              "QQQが200日線より下では枠を増やさない（2022年のような下げで傷を深くしない）",
              "不調でも新規エントリーは止めない・リスクも減らさない（止めると年率が下がる）",
              "サイトのF1〜F3・MC57・リーダーの強さは「崩れるか」の計器で、この切り替えには効かない"])
        + '<div class="rh">8. 拾う枠（監視・参考）</div>'
        '<div class="sub">本体（売買代金上位5%）の外で、しっかり伸びている中堅株の監視リスト。Positionsタブの別カードに表示。<b>資金は割り当てない</b>（裁量で拾う場合の目安）。</div>'
        + li(["候補：株価$5以上・売買代金$10M以上／RS21・63・189がすべて85以上／52週安値の2倍以上・高値から−35%以内／週足SARブル8週以内／1日の値幅4%以上／業種の強さ上位半分／地合いOK",
              "入るなら本体と同じ形がそろった日（形OK）。手仕舞いは50日線割れ、損切り−10%",
              "形OKのPF 1.92（2015〜18年 1.85／2019〜22年 1.98／2023〜26年 1.89）。ただし単独運用は年率約14%・最大DD−45%で、本体に足すと全体の伸びは下がる",
              "業績（EPS・売上の伸びや加速）は成績をほとんど改善しなかった。値動きに出る特徴（3期間RS・SAR転換直後・2倍後のベース・高ボラ・強い業種）が効く"])
        + _tqqq_section()
        + '<div class="rh">やらないこと</div>' + li(dont)
        + '<div class="rh">成績（単年）</div>'
        '<div class="rnote">個別株＝個別株だけ、QQQ込（旧）＝余剰資金を7のルールでQQQに置いた場合、TQQQ枠込＝7のルールでTQQQルール枠（9）に置いた場合（現行）。'
        '年内DD＝個別株だけの年内最大下落。2026年は1〜8月。2026年10月に同じデータで計算し直した値（以前の表示より個別株の年ごとの値が少し違う）。</div>'
        + _yearly() + _totals()
        + '<div class="rwarn"><b>成績</b>（2015年1月〜2026年8月、地合い込み・最大6銘柄ルール）：個別株だけで年率31.0%・最大DD−31.4%（約23倍）。'
        '余剰資金を7のルールでTQQQルール枠に置くと<b>年率55.1%・最大DD−33.8%（約166倍）</b>。QQQのままなら40.6%・−31.6%（約53倍）。'
        '2015〜20年は年率33.6%（QQQなら23.7%）、2021〜26年は81.5%（同61.0%）。負けた年は2022年（−10.1%、QQQなら−17.2%）。<br>'
        '2026年10月9日訂正：HY OASを公表日より1営業日早く使っていたため、公表の遅れどおりに直して再計算（以前の表示は年率60.2%・約244倍）。<br>'
        '現存銘柄だけで検証（上場廃止銘柄は未検証）、税金・テーマ枠は含まない。TQQQは3倍レバレッジETFで、2000年や2008年のような長い下げでは'
        'ルール単体で−50%前後まで下がりうる（9を参照）。集中の上乗せは2021年以降が大きく、今後も同じとは限らない。売買の推奨ではなく検証結果のまとめ。</div></div>'
    )


def _tqqq_section() -> str:
    li = lambda items: '<ul class="rules">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>"
    rule = _table(["部分", "中身"], [
        ["合成", "切替型×0.625＋改良案×0.375。25%刻み（目標との差が0.75刻み以上で動かす）"],
        ["切替型", "QQQが200日線より上、またはQQQが21EMAより上で21EMAが5日前より上なら保有。トレンド外でも投げ売り後の反発"
                   "（10日以内にVIX28以上→VIXが5日平均を下回りQQQ上昇／出来高が20日平均の1.5倍・上半分引け・QQQが20日高値から−8%超）は最大15日・TQQQ−15%まで持つ"],
        ["改良案", "常に保有"],
        ["サイズ", "両方とも min(1, 100%÷TQQQの20日ボラ)"],
        ["緊急モード", "切替型：QQQが52週高値から−15%以下か10日で−10%。改良案：−25%以下。"
                       "比率＝トレンド内×min(1, 1＋下落率÷30%)×min(1, 70%÷ボラ)。解除はゴールデンクロス・高値圏回復（切替型−5%、改良案−10%以内）・①"],
        ["①早期再エントリー", "<b>採用</b>。緊急モード中でも、HY OAS（FRED BAMLH0A0HYM2）が40日平均未満かつ直近10日最高値×0.9未満なら緊急解除"],
        ["過熱警報", "QQQが200日線+35%超でTQQQ 0%、+10%未満に冷えたら解除"],
        ["信用スプレッド", "HY OASが40日平均×1.1超の日はTQQQ最大25%"],
        ["TQQQ以外", "金の6か月（126日）リターンがプラスなら金、そうでなければ短期国債"],
        ["執行", "QQQの終値で判定→翌営業日にTQQQを売買（楽天証券）。サイト上部のカードに今日の目標"],
    ])
    perf = _table(["期間", "年率", "最大DD"], [
        ["2015〜2026/8", "46.3%", "−51.1%"],
        ["2000〜2026", "29.8%", "−56.1%"],
    ], num_cols=(1, 2))
    return ('<div class="rh">9. TQQQルール（余剰資金の置き先）</div>'
            '<div class="sub">シグナルはQQQ、売買はTQQQ。平時は攻め、長い下げ（緊急時）だけ守る切り替え型。7の比率（50%か100%）のうち、'
            'このルールの目標比率をTQQQに、残りを金か短期国債に置く（例：枠50%・目標75%なら余剰資金の37.5%がTQQQ）。</div>'
            + rule + '<div class="rnote">ルール単体の成績（余剰資金の100%をこの枠に置いた場合）。2000〜2026年はITバブル崩壊と金融危機を含む。</div>' + perf
            + li(["HY OASは<b>前営業日までに公表された値</b>を使う（その日の値は引けの時点でまだ出ていない）。"
                  "以前はこれを1営業日早く使っていて成績が高く出ていた（2015〜2026/8で56.9%→46.3%に訂正）",
                  "①（早期再エントリー）の効果はほぼ中立：2015〜2026/8は+0.8pt（46.3%、なしなら45.5%）、2000〜2026年は−0.3pt",
                  "HY上限（25%）は年率を約2pt下げる代わりに最大DDを浅くする（2015〜2026/8で−57%→−51%）",
                  "長い下げの途中の反発を取りにいく追加ルールは60通り試してすべて悪化 → 入れない",
                  "だまし検出やDDを浅くする代わりに年率を大きく落とす版は採用しない（リターン優先）",
                  "<b>②信用125%（参考・未採用）</b>：目標100%・HY OASが40日平均未満・TQQQの20日ボラ60%未満の日だけ信用で125%。"
                  "使う場合は楽天証券でTQQQが信用取引の対象か要確認"])
            + '<div class="rnote">NQトレンド信号（NQ-SAR）・SOXLのレバ枠・非常口は運用停止（アーカイブタブ）。</div>')


SECTION = re.compile(r'(<section id="t-rules">)(.*?)(</section>)', re.S)


def apply(text: str, regime: dict[str, Any] | None = None, health: dict[str, Any] | None = None) -> str:
    """Replace the whole Rules tab content.  No-op if the tab is missing."""
    m = SECTION.search(text)
    if not m:
        return text
    out = text[:m.start(2)] + rules_html(regime, health) + text[m.end(2):]
    if STYLE not in out:
        out = re.sub(r"<style>#t-rules \.rtb\{.*?</style>", "", out, flags=re.S)  # an older version of STYLE
        out = out.replace("</head>", STYLE + "</head>", 1)
    return out
