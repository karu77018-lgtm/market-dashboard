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


def test_counterparty_issuance_is_not_filer_dilution():
    text = (
        "On September 19, 2026, Navitas Semiconductor Corporation entered into a Stock Purchase "
        "Agreement with Magnachip Semiconductor Corporation, pursuant to which Magnachip agreed "
        "to issue and sell to the Company 1,461,988 shares of Magnachip's common stock at a "
        "purchase price of $3.42 per share, for an aggregate purchase price of $5,000,000."
    )
    x = parse_disclosure_terms(text, "private_placement", "2026-09-21")
    assert x["issuer_mismatch"] is True
    assert x["basic_new_shares"] is None
    assert x["offer_price"] is None
    assert x["explicit_financing_amount"] is None


def test_exercised_underwriter_option_counts_as_issued_shares():
    text = (
        "the Company entered into an underwriting agreement relating to the previously announced "
        "underwritten offering of 10,714,286 shares of the Company's common stock at a price to "
        "the public of $21.00 per share. In addition, the Company granted the Underwriters a "
        "30-day option to purchase up to 1,607,143 additional shares of Common Stock at the same "
        "public offering price per share, less underwriting discounts and commissions, which "
        "Option was fully exercised by the Underwriters on July 8, 2026."
    )
    x = parse_disclosure_terms(text, "public_offering", "2026-07-09")
    assert x["base_new_shares"] == 10_714_286
    assert x["exercised_option_shares"] == 1_607_143
    assert x["basic_new_shares"] == 12_321_429
    assert x["offer_price"] == 21.0


def test_offering_price_is_pattern():
    text = (
        "Alto Neuroscience, Inc. entered into an underwriting agreement with BofA Securities, Inc. "
        "to issue and sell 3,776,436 shares of common stock. The offering price is $26.48 per share. "
        "The Company estimates that the net proceeds from the Offering will be approximately $93.9 million."
    )
    x = parse_disclosure_terms(text, "public_offering", "2026-07-14")
    assert x["offer_price"] == 26.48


def test_predated_transaction_is_timing_ambiguous_until_publication_time_is_known():
    text = (
        "On August 10, 2026, Ryman Hospitality Properties, Inc. (the Company) entered into an "
        "underwriting agreement providing for the issuance and sale by the Company of 5,100,000 shares "
        "of the Company's common stock at a purchase price to the public of $117.00 per share."
    )
    x = parse_disclosure_terms(text, "public_offering", "2026-08-12")
    assert x["transaction_date_candidate"] == "2026-08-10"
    assert x["timing_ambiguous"] is True
