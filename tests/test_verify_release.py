from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_release  # noqa: E402

FILES = ("source-mc57.html", "latest-manifest.json", "data/mc57.json", "chart-data/index.json",
         "market-history/index.json")


def copy_site(tmp: Path) -> Path:
    for rel in FILES:
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp / rel)
    return tmp


def test_published_commit_passes_gate(tmp_path: Path):
    assert verify_release.problems(copy_site(tmp_path)) == []


def test_gate_blocks_mismatched_session_and_old_rule(tmp_path: Path):
    root = copy_site(tmp_path)
    mc = json.loads((root / "data/mc57.json").read_text())
    mc["session_date"] = "1999-01-01"
    (root / "data/mc57.json").write_text(json.dumps(mc))
    html = (root / "source-mc57.html").read_text()
    (root / "source-mc57.html").write_text(html.replace('id="rules-card" data-rule="', 'id="rules-card" data-rule="old-', 1))
    found = verify_release.problems(root)
    assert any("session mismatch" in p for p in found) and any(p.startswith("rule:") for p in found)
    (root / "latest-manifest.json").write_text("{")
    assert verify_release.problems(root)[0].startswith("published file unreadable")


def test_pages_deploy_only_publishes_the_gated_checkout():
    wf = (ROOT / ".github/workflows/deploy-pages.yml").read_text()
    order = ["name: Release gate on committed files", "name: All tabs render on desktop and iPhone widths",
             "name: Assemble the site from exactly this commit", "uses: actions/upload-pages-artifact@v3",
             "deploy:", "needs: verify", "uses: actions/deploy-pages@v4"]
    positions = [wf.index(marker) for marker in order]
    assert positions == sorted(positions)
    assert "pages/builds" not in (ROOT / ".github/workflows/complete-restoration.yml").read_text()
