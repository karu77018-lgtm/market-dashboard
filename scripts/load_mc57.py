"""
market-dashboard (source-mc57) データ読み込みヘルパー

使い方:
    from load_mc57 import load_manifest, load_ticker, load_all, REPO_DIR

    manifest = load_manifest()
    df = load_ticker("AAPL")          # 単一銘柄のOHLCV DataFrame
    data = load_all(["AAPL", "MSFT"]) # 複数銘柄をまとめて dict[str, DataFrame] で取得
"""
import json
from pathlib import Path
from functools import lru_cache

REPO_DIR = Path(__file__).resolve().parent.parent
CHART_DIR = REPO_DIR / "chart-data"


def load_manifest() -> dict:
    with open(REPO_DIR / "latest-manifest.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _ticker_index() -> dict:
    with open(CHART_DIR / "index.json", encoding="utf-8") as f:
        idx = json.load(f)
    return idx["ticker_to_shard"]


@lru_cache(maxsize=None)
def _load_shard(shard_no: int) -> dict:
    path = CHART_DIR / f"shard-{shard_no:02d}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_ticker(ticker: str):
    """指定銘柄のOHLCVをpandas DataFrameで返す。列: date, open, high, low, close, volume"""
    import pandas as pd

    idx = _ticker_index()
    if ticker not in idx:
        raise KeyError(f"{ticker} not found in chart-data index ({len(idx)} tickers available)")
    shard = _load_shard(idx[ticker])
    rows = shard[ticker]
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def load_all(tickers=None):
    """複数銘柄をまとめて取得。tickers=Noneなら全銘柄（重いので注意）。"""
    idx = _ticker_index()
    tickers = tickers or list(idx.keys())
    return {t: load_ticker(t) for t in tickers if t in idx}


def list_tickers():
    return sorted(_ticker_index().keys())


if __name__ == "__main__":
    m = load_manifest()
    print("session_date:", m.get("session_date"), "| mc57:", m.get("mc57"), "| status:", m.get("status"))
    print("universe (active):", m["universe"]["active_universe"])
    df = load_ticker("AAPL")
    print(df.tail())
