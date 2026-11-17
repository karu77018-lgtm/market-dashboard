import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import market_alerts as ma  # noqa: E402


def test_first_run_is_silent_then_only_new_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "7")
    evs = [("phase:up5:2026-11-11", "A"), ("down5:2026-11-05", "B")]
    monkeypatch.setattr(ma, "events", lambda text: (list(evs), "特別な合図なし"))
    (tmp_path / "seed").mkdir()
    assert ma.run("", tmp_path, "2026-11-16") == []                                   # records only
    assert ma.run("", tmp_path, "2026-11-17") == []                                   # nothing new
    evs.append(("ftd:QQQ:2026-11-18", "C"))
    monkeypatch.setattr(ma, "events", lambda text: (list(evs), "F3の回復の合図（11/18〜）"))
    got = ma.run("", tmp_path, "2026-11-18")
    assert got == ["C", "警戒灯の読み方が変わりました：F3の回復の合図（11/18〜）。"]
    st = json.loads((tmp_path / ma.STATE).read_text(encoding="utf-8"))
    assert st["last"] == {"run": "7", "session": "2026-11-18", "messages": got}
    assert ma.run("", tmp_path, "2026-11-18") == []                                   # a second refresh of the day: no repeat


def test_events_read_the_cards():
    text = (ROOT / "source-mc57.html").read_text(encoding="utf-8")
    evs, _ = ma.events(text)
    assert all(isinstance(k, str) and isinstance(m, str) and m for k, m in evs)
