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


def _agg(pos=.8, neg=.1, persist=.8, novelty=.8, embedded=.2, sell=.2, quality="strong"):
    return {
        "EG01_positive_business_change": {"probabilityMean": pos},
        "EG02_negative_business_change": {"probabilityMean": neg},
        "EG03_persistent_change": {"probabilityMean": persist},
        "EG04_information_novelty": {"probabilityMean": novelty},
        "EG05_expectations_already_embedded": {"probabilityMean": embedded},
        "EG07_sell_the_news_risk": {"probabilityMean": sell},
        "EG08_evidence_quality": {"majorityChoice": quality},
    }


def test_underappreciated_positive_label_requires_low_expectation_and_unpriced_evidence():
    assert derive_label(35, _agg()) == "UNDERAPPRECIATED_POSITIVE"


def test_positive_but_priced_when_expectations_high():
    assert derive_label(85, _agg(embedded=.75)) == "POSITIVE_BUT_PRICED"


def test_weak_evidence_never_promoted():
    assert derive_label(20, _agg(quality="weak")) == "INSUFFICIENT_EVIDENCE"
