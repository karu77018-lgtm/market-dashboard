from scripts.run_expectation_gap_shadow import (
    build_expectation_load,
    classify_form4_row,
    derive_label,
    percentile_map,
)


def test_percentile_map_orders_values():
    p = percentile_map({"A": 1.0, "B": 2.0, "C": 3.0})
    assert p["A"] == 0
    assert p["B"] == 50
    assert p["C"] == 100


def test_expectation_load_is_cross_sectional_and_bounded():
    det = {
        "LOW": {"px": 20, "off": None, "rs21": 70, "rs": 75, "rs189": 80, "d21": 2, "d52": -20, "v50": 3, "rv": 0.8},
        "HIGH": {"px": 20, "off": None, "rs21": 99, "rs": 98, "rs189": 95, "d21": 30, "d52": -1, "v50": 25, "rv": 2.5},
        "OFF": {"px": 20, "off": "liquidity", "rs21": 99, "rs": 99, "rs189": 99, "d21": 50, "d52": 0, "v50": 40, "rv": 4},
    }
    rows = build_expectation_load(det)
    assert "OFF" not in rows
    assert 0 <= rows["LOW"]["expectation_load_pctile"] <= 100
    assert rows["HIGH"]["expectation_load_pctile"] > rows["LOW"]["expectation_load_pctile"]


def test_form4_scheduled_sale_not_discretionary():
    row = {
        "transaction_code": "S",
        "transaction_acquired_disposed": "D",
        "transaction_price_per_share": 100,
        "aff_10b5_one": True,
        "security_type": "non_derivative",
        "security_title": "Common Stock",
    }
    assert classify_form4_row(row) == "scheduled_sale_10b5_1"


def test_form4_tax_withholding_not_discretionary():
    assert classify_form4_row({"transaction_code": "F"}) == "tax_withholding"


def test_form4_open_market_purchase_is_positive_category():
    row = {
        "transaction_code": "P",
        "transaction_acquired_disposed": "A",
        "transaction_price_per_share": 50,
        "security_type": "non_derivative",
        "security_title": "Common Stock",
    }
    assert classify_form4_row(row) == "open_market_purchase"


def _agg(material=.8, persist=.8, novelty=.8, surprise="positive_surprise", quality="strong"):
    return {
        "JEV01_material_business_change": {"probabilityMean": material},
        "JEV02_persistent_change": {"probabilityMean": persist},
        "JEV03_information_novelty": {"probabilityMean": novelty},
        "JEV04_surprise_vs_prior_expectations": {
            "majorityChoice": surprise,
            "choiceDistribution": {
                "positive_surprise": 0.75 if surprise == "positive_surprise" else 0.10,
                "negative_surprise": 0.75 if surprise == "negative_surprise" else 0.10,
                "broadly_expected": 0.75 if surprise == "broadly_expected" else 0.10,
                "unclear": 0.75 if surprise == "unclear" else 0.05,
            },
        },
        "JEV05_evidence_quality": {"majorityChoice": quality},
    }


def test_positive_semantic_change_requires_material_persistent_novel_surprise():
    assert derive_label(35, _agg()) == "POSITIVE_SEMANTIC_CHANGE"


def test_negative_semantic_change_is_separate_from_market_expectation_load():
    assert derive_label(85, _agg(surprise="negative_surprise")) == "NEGATIVE_SEMANTIC_CHANGE"


def test_broadly_expected_is_not_promoted():
    assert derive_label(20, _agg(surprise="broadly_expected")) in {"BROADLY_EXPECTED", "EXPECTED_OR_MINOR"}


def test_weak_evidence_never_promoted():
    assert derive_label(20, _agg(quality="weak")) == "INSUFFICIENT_EVIDENCE"
