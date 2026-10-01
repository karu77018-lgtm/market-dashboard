"""Small display corrections. No portfolio calculation or trade rule changes."""
from __future__ import annotations
import html
import json
from pathlib import Path
from bs4 import BeautifulSoup


def apply(text: str, root: Path) -> str:
    text = text.replace("NQ運用判定（専用）", "NQ露出上限")
    soup = BeautifulSoup(text, "html.parser")
    # Only the two legacy Core 12 tables need containment; table styling stays.
    for table in soup.select('#t-port table'):
        if 'core-table-wrap' not in table.parent.get('class', []):
            wrapper = soup.new_tag('div', attrs={'class': 'core-table-wrap',
                'style': 'max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch'})
            table.wrap(wrapper)
    expo = soup.select_one('#taExpo')
    if expo:
        content = expo.get_text().replace('目標露出：', '目標露出（上限）：').replace(' ・ フル投資', '')
        expo.clear()
        label = soup.new_tag('span', attrs={'class': 'mut', 'style': 'font-weight:600'})
        label.string = '目標露出（上限）：'
        expo.append(label)
        expo.append(content.split('：', 1)[-1])
    estimate = soup.select_one('#taEst')
    if estimate:
        estimate.clear()
        estimate.append(BeautifulSoup('<span class="sar-badge est">推定・TradingViewで色を確認</span>', 'html.parser'))
    for script in soup.find_all('script'):
        raw = script.string
        if raw and 'function _nqExpo' in raw:
            script.string = raw.replace('フル投資：個別100%・レバ100%。', '目標露出（上限）：個別100%・レバ100%。').replace('目標露出：', '目標露出（上限）：').replace(' ・ フル投資', '').replace("'フル投資'", "'上限まで許容'").replace("return '個別 '", "return '目標露出（上限）：個別 '")
    card = soup.select_one('#taCard')
    badge = soup.select_one('#t-port .def-badge')
    old = soup.select_one('#taExecutionNote')
    if old:
        old.decompose()
    if card and badge and 'F2 点灯' in badge.get_text():
        note = soup.new_tag('div', attrs={'id': 'taExecutionNote', 'class': 'sub'})
        note.string = 'SOXL/TQQQの新規トランシェ保留中（F2）。露出上限と執行上の注意は別。売買ルール本体は変更しません。'
        card.select_one('.ta-top').insert_after(note)
    old = soup.select_one('#mc57-correction-note')
    if old:
        old.decompose()
    path = root / 'data/mc57.json'
    mc = json.loads(path.read_text()) if path.exists() else {}
    corrections = mc.get('corrections', [])
    if corrections:
        c = corrections[-1]
        target = soup.select_one('[data-history-key="mc57"] details.cxpl')
        if target:
            note = soup.new_tag('div', attrs={'id': 'mc57-correction-note', 'class': 'sub'})
            note.string = f"訂正公開 {c['published_at']}：{c['previous_mc57']:.2f} → {c['corrected_mc57']:.2f}。理由：{c['reason']}"
            target.append(note)
    return str(soup).replace('<footer class="disc">', "<footer class='disc'>")


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--root', default='.')
    a = p.parse_args()
    root = Path(a.root)
    path = root / 'source-mc57.html'
    path.write_text(apply(path.read_text(), root), encoding='utf-8')
