from decimal import Decimal

from app.ai.extraction import parse_boq_lines


def test_training_tender_steel_rows_are_extracted_with_units_and_specs():
    text = """ST-01 ISMB 300 beams, IS 2062 E250, 24 MT
ST-02 ISMC 200 channels, IS 2062 E250, 12 MT
ST-03 ISA 75x75x6 angles, IS 2062 E250, 8 MT
ST-04 MS Plate 10 mm, IS 2062 E250, 16 MT
ST-05 GI Sheet Z120, IS 277, 4200 SQM
ST-06 TMT Fe 500D, 12 mm, 10 MT
ST-07 TMT Fe 550D, 16 mm, 6 MT"""
    rows = parse_boq_lines(text)
    assert len(rows) == 7
    assert [(r["form"], Decimal(r["quantity"]), r["unit"]) for r in rows] == [
        ("BEAM", Decimal("24"), "MT"), ("CHANNEL", Decimal("12"), "MT"),
        ("ANGLE", Decimal("8"), "MT"), ("PLATE", Decimal("16"), "MT"),
        ("SHEET", Decimal("4200"), "SQM"), ("REBAR", Decimal("10"), "MT"),
        ("REBAR", Decimal("6"), "MT"),
    ]
    assert rows[0]["grade"] == "E250" and rows[0]["specification"]["standard"] == "IS 2062"
    assert rows[4]["specification"]["standard"] == "IS 277"
    assert rows[5]["grade"] == "FE500D" and rows[6]["grade"] == "FE550D"
