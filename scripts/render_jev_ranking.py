#!/usr/bin/env python3
"""Render the public, derived Jev ranking as an isolated dashboard tab."""
from __future__ import annotations

import argparse
import html
import hashlib
import re
import json
from pathlib import Path
from typing import Any


NAV_START = "<!-- JEV_RANKING_NAV_START -->"
NAV_END = "<!-- JEV_RANKING_NAV_END -->"
STYLE_START = "<!-- JEV_RANKING_STYLE_START -->"
STYLE_END = "<!-- JEV_RANKING_STYLE_END -->"
SECTION_START = "<!-- JEV_RANKING_START -->"
SECTION_END = "<!-- JEV_RANKING_END -->"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


def score(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number:+.1f}"


def rs_triplet(row: dict[str, Any]) -> str:
    def one(value: Any) -> str:
        try:
            return str(int(round(float(value))))
        except (TypeError, ValueError):
            return "—"
    return f"{one(row.get('rs21'))}・{one(row.get('rs63'))}・{one(row.get('rs189'))}"


def remove_between(text: str, start: str, end: str) -> str:
    while start in text:
        left = text.index(start)
        right = text.index(end, left) + len(end)
        text = text[:left] + text[right:]
    return text


def load_ranking(path: Path) -> dict[str, Any]:
    if not path.exists():
        payload = {
            "schema_version": "jev-public-ranking-v1",
            "status": "not_available",
            "session_date": None,
            "available_at": None,
            "formula": "100 * (mean(positive probabilities) - mean(risk probabilities))",
            "rows": [],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise RuntimeError("Jev ranking payload is invalid")
    return payload


def render_section(payload: dict[str, Any]) -> str:
    rows = [row for row in payload.get("rows", []) if isinstance(row, dict)]
    asof = payload.get("available_at") or payload.get("session_date") or "—"
    if rows:
        body = "".join(
            f"<tr class='jev-click' role='button' tabindex='0' aria-label='{esc(row.get('ticker', '—'))}の銘柄情報を開く' "
            f"onclick=\"showDet('{esc(row.get('ticker', ''))}')\" "
            f"onkeydown=\"if(event.key==='Enter'||event.key===' '){{event.preventDefault();showDet('{esc(row.get('ticker', ''))}')}}\">"
            f"<td class='jev-ticker'><b>{esc(row.get('ticker', '—'))}</b>"
            f"<span>{esc(' / '.join(row.get('candidate_sources') or ['候補']))}</span></td>"
            f"<td class='jev-score'>{score(row.get('expected_value_score'))}</td>"
            f"<td class='jev-rank'>{index}</td>"
            f"<td class='jev-rs'>{esc(rs_triplet(row))}</td>"
            f"<td>{pct(row.get('catalyst_probability'))}</td>"
            f"<td>{pct(row.get('risk_probability'))}</td>"
            f"<td class='jev-driver'>{esc(row.get('top_catalyst_label', '—'))}<span>"
            f"{pct(row.get('top_catalyst_probability'))}</span></td>"
            f"<td class='jev-driver'>{esc(row.get('top_risk_label', '—'))}<span>"
            f"{pct(row.get('top_risk_probability'))}</span></td>"
            "</tr>"
            for index, row in enumerate(rows, 1)
        )
        table = (
            "<div class='jev-table-wrap'><table class='ptab jev-table'><thead><tr>"
            "<th class='l'>銘柄・候補元</th><th>期待値</th><th>#</th><th>RS 21・63・189</th><th>好材料</th><th>リスク</th>"
            "<th class='l'>最大の好材料</th><th class='l'>最大のリスク</th>"
            f"</tr></thead><tbody>{body}</tbody></table></div>"
        )
        suffix = "（一部評価失敗）" if payload.get("status") == "partial" else ""
        status = f"{len(rows)}銘柄をJev 3回評価{suffix}"
    else:
        table = (
            "<div class='jev-empty'>Jev評価データはまだありません。次の自動更新で評価後に表示されます。</div>"
        )
        status = "評価待ち"
    return (
        f"{SECTION_START}<section id='t-jev' class='jev-ranking-section'>"
        "<div class='msec'><div class='msec-l'>Jev期待値ランキング"
        "<span class='msec-en'>Jev Evidence Ranking</span></div>"
        f"<div class='msec-q'>{esc(status)}</div></div>"
        "<div class='card jev-explain'><h2>ニュース材料の期待値"
        "<span class='h2en'>Research Shadow</span></h2>"
        "<div class='sub'>Jevの15問を各3回評価し、好材料7項目の平均確率からリスク7項目の平均確率を引いて100倍した順位です。"
        "株価の期待収益率ではなく、公開時点までのニュース材料を比較する研究スコアです。</div>"
        f"<div class='mut jev-asof'>評価時点 {esc(asof)} ／ 表示候補＋RS21・63・189各上位を重複除外</div></div>"
        f"<div class='card'>{table}</div></section>{SECTION_END}"
    )


STYLE = """<!-- JEV_RANKING_STYLE_START --><style id="jev-ranking-style">
.jev-table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}.jev-table{min-width:900px;table-layout:fixed}.jev-table th:nth-child(1){width:130px}.jev-table th:nth-child(2){width:65px}.jev-table th:nth-child(3){width:28px}.jev-ticker span{white-space:normal;overflow-wrap:anywhere}.jev-ticker{max-width:130px}
.jev-table td,.jev-table th{white-space:nowrap}.jev-rank{color:#777268;font-weight:700}
.jev-ticker span,.jev-driver span{display:block;color:#8b877d;font-size:9px;margin-top:2px}
.jev-score{font-weight:800;color:#2457a6}.jev-explain .sub{line-height:1.7}.jev-asof{margin-top:8px}
.jev-rs{font-variant-numeric:tabular-nums;color:#565243}
.jev-click{cursor:pointer}.jev-click:hover td{background:rgba(44,105,201,.06)}
.jev-click:focus{outline:2px solid #2c69c9;outline-offset:-2px}.jev-click:active td{background:rgba(44,105,201,.12)}
.jev-empty{padding:24px 8px;text-align:center;color:#777268;line-height:1.7}
</style><!-- JEV_RANKING_STYLE_END -->"""


def source_hash(text: str) -> str:
    text = re.sub(r'<meta\b(?=[^>]*\bname="dashboard-source-sha256")[^>]*>', '', text)
    text = re.sub(r'<script id="jev-ranking-loader"[^>]*></script>', '', text)
    # Jev's section is independent of source evidence.
    text = remove_between(text, SECTION_START, SECTION_END)
    return hashlib.sha256(text.encode()).hexdigest()


def bind_ranking(html_path: Path, ranking_path: Path) -> None:
    payload = load_ranking(ranking_path)
    payload["source_html_sha256"] = source_hash(html_path.read_text())
    ranking_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render(html_path: Path, ranking_path: Path) -> None:
    payload = load_ranking(ranking_path)
    text = html_path.read_text(encoding="utf-8")
    text = re.sub(r'<meta\b(?=[^>]*\bname="dashboard-source-sha256")[^>]*>', '', text)
    text = re.sub(r'<script id="jev-ranking-loader"[^>]*></script>', '', text)
    text = remove_between(text, STYLE_START, STYLE_END)
    text = remove_between(text, SECTION_START, SECTION_END)
    text = remove_between(text, NAV_START, NAV_END)
    nav_anchor = "</nav>"
    if nav_anchor not in text:
        raise RuntimeError("dashboard navigation anchor not found")
    nav = (
        f"{NAV_START}<a class=\"tabx\" href=\"#t-jev\" "
        "onclick=\"tab('t-jev',this);return false;\">Jev期待値</a>"
        f"{NAV_END}"
    )
    text = text.replace(nav_anchor, nav + nav_anchor, 1)
    if "</head>" not in text:
        raise RuntimeError("dashboard head anchor not found")
    text = text.replace("</head>", STYLE + "</head>", 1)
    footer = "<footer class='disc'>"
    if footer not in text:
        raise RuntimeError("dashboard footer anchor not found")
    shell = render_section({"rows": []}).replace('Jev評価データはまだありません。次の自動更新で評価後に表示されます。', 'Jev評価を読み込み中…')
    text = text.replace(footer, shell + footer, 1)
    digest = source_hash(text)
    text = text.replace('</head>', f'<meta name="dashboard-source-sha256" content="{digest}"/>' + '</head>', 1)
    text = text.replace('</body>', '<script id="jev-ranking-loader" src="assets/jev-ranking.js"></script></body>', 1)
    html_path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", default="source-mc57.html")
    parser.add_argument("--ranking", default="data/jev-ranking.json")
    parser.add_argument("--bind-only", action="store_true")
    args = parser.parse_args()
    if args.bind_only:
        bind_ranking(Path(args.html), Path(args.ranking))
        return 0
    render(Path(args.html), Path(args.ranking))
    print(json.dumps({"status": "rendered", "tab": "Jev期待値"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
