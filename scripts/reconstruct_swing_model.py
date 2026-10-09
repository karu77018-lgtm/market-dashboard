"""Explicit, reproducible five-name model backcast from published chart OHLC.

Never executed by display refreshes. Frozen original fills/results remain untouched.
The generated modeled_portfolio becomes the single current portfolio on daily refresh.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import pandas as pd
import track_portfolio as tp
import tqqq_rule


def replay(root: Path, ledger: dict, *, input_commit: str, generated_at: str) -> dict:
    """Replay frozen signals with ONE chart price version, never original stock fills."""
    original = ledger.get('portfolio') or {}
    start, until = original.get('start'), original.get('last_day')
    if not start or not until:
        raise ValueError('Original portfolio dates are required')
    sessions = {d: copy.deepcopy(s) for d, s in ledger['sessions'].items() if start <= d <= until}
    index_path = root / 'chart-data/index.json'
    index = json.loads(index_path.read_text())
    if index.get('session_date') != until:
        raise ValueError('Chart snapshot and original cutoff must match')
    names = sorted({r['t'] for s in sessions.values() for r in s['best']})
    paths = {'chart-data/index.json', 'track-record/tqqq-rule.json', 'track-record/signals.json'}
    rows = []
    for t in names:
        n = index['ticker_to_shard'].get(t)
        if n is None:
            raise ValueError(f'Missing chart ticker: {t}')
        path = f'chart-data/shard-{n:02d}.json'
        paths.add(path)
        bars = json.loads((root / path).read_text())[t]
        for bar in bars:
            if bar[0] <= until:
                rows.append([t] + bar)
    frame = pd.DataFrame(rows, columns=['ticker', 'date', 'open', 'high', 'low', 'close', 'volume'])
    frame['date'] = pd.to_datetime(frame['date'], errors='raise')
    if frame.duplicated(['ticker', 'date']).any():
        raise ValueError('Duplicate chart bars')
    prices = frame[['open', 'high', 'low', 'close']]
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
           for row in prices.itertuples(index=False, name=None) for v in row):
        raise ValueError('Invalid chart OHLC')
    for t in names:
        if len(frame[(frame.ticker == t) & (frame.date <= pd.Timestamp(start))]) < 21:
            raise ValueError(f'Insufficient EMA history: {t}')
    # QQQ is only the comparison benchmark when fund NAV is supplied. Its frozen
    # quoted opens/closes are separate from the stock execution prices above.
    qqq = {}
    for day, _, close in original['equity']:
        if not start <= day <= until:
            continue
        opens = {float(t['qqq_in']) for t in ledger['trades'].values()
                 if t.get('entry_day') == day and t.get('qqq_in') is not None}
        if day != start and len(opens) != 1:
            raise ValueError(f'Missing or conflicting benchmark open: {day}')
        if close is None:
            raise ValueError(f'Missing benchmark close: {day}')
        qqq[day] = {'open': next(iter(opens)) if opens else close, 'close': close}
    for day in qqq:
        if day == start:
            continue
        for t in names:
            if not ((frame.ticker == t) & (frame.date == pd.Timestamp(day))).any():
                raise ValueError(f'Missing chart bar: {t} {day}')
    fund = tqqq_rule.fund_bars(tqqq_rule.load(root / tqqq_rule.LEDGER))
    pf = tp.advance(tp.new_portfolio(start), sessions, frame, qqq, until, fund=fund)
    if pf['last_day'] != until or pf.get('waiting') or pf.get('skipped') or any(p.get('stale') for p in pf['positions'].values()):
        raise ValueError('Incomplete reconstruction; no model may be published')
    pf['reconstruction'] = {
        'kind': 'chart-ohlcv-backcast', 'as_of': until, 'generated_at': generated_at,
        'input_commit': input_commit,
        'inputs': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sorted(paths)},
        'signal_policy': 'original-frozen-lists-and-order; old rule labels unchanged',
        'price_policy': 'all stock fills/stops/EMA/marks use committed chart OHLC; no frozen stock-fill overrides',
        'benchmark_policy': 'QQQ opens/closes from original recorded benchmark quotes; not stock fill inputs',
        'price_note': '公開チャートの改訂済みOHLCを統一使用。旧記録の約定価格とは一部異なります。',
        'forward_policy': 'advance this saved model only after last_day; never rebuild on display',
    }
    return pf


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('.'))
    p.add_argument('--input-commit', required=True)
    p.add_argument('--generated-at', required=True)
    args = p.parse_args()
    path = args.root / 'track-record/signals.json'
    ledger = json.loads(path.read_text())
    if ledger.get('modeled_portfolio'):
        raise ValueError('Existing model must not be silently overwritten')
    ledger['modeled_portfolio'] = replay(args.root, ledger, input_commit=args.input_commit, generated_at=args.generated_at)
    # No old keys, frozen signals, quantities or fills are changed.
    import track_record
    track_record.save(ledger, path)


if __name__ == '__main__':
    main()
