from scripts.event_risk.build_dilution_magnitude import _bin, parse_disclosure_terms


def test_parse_vktx_public_offering():
    text = (
        'The Company entered into an underwriting agreement to issue and sell '
        '7,857,143 shares of the Company common stock at a public offering price '
        'of $35.00 per share. Net proceeds were approximately $297.0 million.'
    )
    x = parse_disclosure_terms(text, "public_offering")
    assert x["basic_new_shares"] == 7_857_143
    assert x["offer_price"] == 35.0
    assert x["explicit_financing_amount"] == 297_000_000
    assert x["explicit_financing_basis"] == "net_proceeds"
    assert x["secondary_only"] is False
    assert x["extraction_confidence"] == "high"


def test_parse_fwdi_registered_direct():
    text = (
        'The Company agreed to issue and sell in a registered direct offering an aggregate '
        'of 3,125,000 shares of the Company common stock. Each Share was offered and sold '
        'at an offering price of $8.00.'
    )
    x = parse_disclosure_terms(text, "public_offering")
    assert x["basic_new_shares"] == 3_125_000
    assert x["offer_price"] == 8.0
    assert x["extraction_confidence"] == "high"


def test_secondary_selling_shareholder_is_not_dilution():
    text = (
        'The Selling Shareholder agreed to sell 10,000,000 shares of Common Stock '
        'to the Underwriters at $9.25 per share, with an option for up to '
        '1,500,000 additional shares.'
    )
    x = parse_disclosure_terms(text, "public_offering")
    assert x["secondary_only"] is True
    assert x["basic_new_shares"] is None


def test_bins():
    assert _bin(1.99) == "<2%"
    assert _bin(2.0) == "2-5%"
    assert _bin(5.0) == "5-10%"
    assert _bin(10.0) == "10-20%"
    assert _bin(20.0) == "20%+"
