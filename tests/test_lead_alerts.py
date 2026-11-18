import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lead_alerts as la  # noqa: E402

DATES = [f"2026-01-{d:02d}" for d in range(1, 31)]


def _data(hb_drop_at=None, f3_hi=None, nfci_rise=False):
    hb = {d: 100.0 for d in DATES}
    if hb_drop_at:
        for d in DATES[hb_drop_at:]:
            hb[d] = 90.0
    return {"sphb": hb, "splv": {d: 50.0 for d in DATES},
            "f3": {d: (0.7 if f3_hi and i >= f3_hi else 0.2) for i, d in enumerate(DATES)},
            "nfci": {"2025-12-05": -0.5, "2025-12-12": -0.5, "2025-12-19": -0.5, "2025-12-26": -0.5,
                     "2026-01-02": -0.3 if nfci_rise else -0.5}}


def test_each_alert_and_the_overlap():
    s = la.states(_data(hb_drop_at=22, f3_hi=25), DATES, [50] * 30)
    assert s["risk"][21] is False and s["risk"][22] is True        # -10% vs 20 sessions before
    assert s["f3"][24] is False and s["f3"][25] is True
    assert not any(s["nfci"]) and not any(s["score"])
    assert s["both"][24] is False and s["both"][25] is True


def test_nfci_four_week_rise_and_score_cut():
    s = la.states(_data(nfci_rise=True), DATES, [29] + [31] * 29)
    assert s["nfci"][0] is False and s["nfci"][1] is True and s["score"][:2] == [True, False]


def test_empty_data_is_quiet():
    s = la.states({}, DATES, [None] * 30)
    assert not any(any(v) for v in s.values())


def test_seed_covers_five_years():
    data = json.loads((ROOT / la.SEED).read_text(encoding="utf-8"))
    for k in ("sphb", "splv", "f3", "nfci"):
        assert min(data[k]) <= "2021-11-10" and max(data[k]) >= "2026-11-06"
