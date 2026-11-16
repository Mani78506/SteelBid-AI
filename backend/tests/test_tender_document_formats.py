from decimal import Decimal

from openpyxl import Workbook

from app.ai.extraction import extract_text_pages, parse_boq_lines


def test_xlsx_tender_extracts_worksheet_text_with_boq_candidates(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Steel BOQ"
    sheet.append(["Item", "Description", "Quantity"])
    sheet.append(["ST-01", "MS Plate E250 IS 2062 10 mm", "16 MT"])
    document = tmp_path / "warehouse-tender.xlsx"
    workbook.save(document)

    pages = extract_text_pages(str(document))

    assert pages[0][0] == 1
    assert "Worksheet: Steel BOQ" in pages[0][1]
    rows = parse_boq_lines(pages[0][1])
    assert len(rows) == 1
    assert rows[0]["form"] == "PLATE"
    assert rows[0]["grade"] == "E250"
    assert Decimal(rows[0]["quantity"]) == Decimal("16")
    assert rows[0]["unit"] == "MT"


def test_extraction_rejects_unsupported_source_format(tmp_path):
    document = tmp_path / "not-a-tender.csv"
    document.write_text("description,quantity\nplate,16 MT\n", encoding="utf-8")

    try:
        extract_text_pages(str(document))
    except ValueError as exc:
        assert "PDF and XLSX" in str(exc)
    else:
        raise AssertionError("unsupported tender document was accepted")
