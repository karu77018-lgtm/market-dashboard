from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_jev_ranking import render  # noqa: E402


def test_render_adds_one_isolated_tab_and_is_idempotent(tmp_path: Path):
    html_path = tmp_path / "dashboard.html"
    html_path.write_text(
        "<html><head></head><body><nav><a>Daily</a></nav>"
        "<section id='t-market'>original</section>"
        "<footer class='disc'>note</footer></body></html>",
        encoding="utf-8",
    )
    ranking_path = tmp_path / "data" / "jev-ranking.json"
    ranking_path.parent.mkdir()
    ranking_path.write_text(json.dumps({
        "status": "ready",
        "session_date": "2026-09-28",
        "available_at": "2026-09-28T22:00:00Z",
        "rows": [{
            "ticker": "AAA", "mc57_rank": 1, "expected_value_score": 12.5,
            "catalyst_probability": 0.4, "risk_probability": 0.275,
            "top_catalyst_label": "需要加速", "top_catalyst_probability": 0.7,
            "top_risk_label": "希薄化", "top_risk_probability": 0.3,
        }],
    }), encoding="utf-8")

    render(html_path, ranking_path)
    render(html_path, ranking_path)
    rendered = html_path.read_text(encoding="utf-8")
    assert rendered.count("Jev期待値</a>") == 1
    assert rendered.count("jev-ranking-section") == 1
    assert "original" in rendered
    assert "AAA" in rendered
    assert "+12.5" in rendered
