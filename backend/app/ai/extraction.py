"""Tender/inquiry document extraction.

Uploaded documents are UNTRUSTED input: text is extracted (pdfplumber → PyMuPDF
fallback), normalized, and parsed with strict rules. Candidate BOQ lines become
`boq_items` (source=AI, review_status=PENDING) plus `extraction_evidence` rows with
page references. Nothing is auto-confirmed; a human must review every value.
Prompt-injection defence: document text is never executed as instructions — extraction
is rule-based against a fixed grammar, and any instruction-like text is ignored
(treated as description content only).
"""
import re
from pathlib import Path
from decimal import Decimal, InvalidOperation

import pdfplumber

from app.calc.finance import q_qty

FORM_PATTERNS = [
    ("PLATE", r"\b(plates?|ms plate|chequered plate)\b"),
    ("BEAM", r"\b(i\s?beams?|is[-\s]?mb\s?\d*|universal beams?|ub\b| beams?)\b"),
    ("CHANNEL", r"\b(is[-\s]?mc\s?\d*|channels?)\b"),
    ("ANGLE", r"\b(isa\s?\d|angles?)\b"),
    ("PIPE", r"\bpipes?\b"),
    ("RHS", r"\b(rhs|rectangular hollow)\b"),
    ("SHS", r"\b(shs|square hollow)\b"),
    ("COIL", r"\b(hr coils?|cr coils?|coils?)\b"),
    ("SHEET", r"\b(gi sheets?|gp sheets?|sheets?)\b"),
    ("REBAR", r"\b(tmt|rebars?|reinforcement bars?)\b"),
    ("CHEQUERED", r"\bchequered\b"),
    ("ROUND_BAR", r"\b(round bars?|bright bars?|rounds)\b"),
]
GRADE_PATTERN = re.compile(r"\b(E\d{3}[A-Z]{0,3}|FE\s?\d{3}[A-Z]{0,2}|ASTM\s?A\d+|S\s?\d{3}[A-Z]{0,3})\b", re.I)
STANDARD_PATTERN = re.compile(r"\bIS\s?\d{3,5}\b", re.I)
QTY_PATTERN = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(MT|KG|TON(?:NE)?S?|NOS?|PCS|SQ\.?\s*M(?:TR)?|SQM|M2)\b", re.I)
DIM_PATTERN = re.compile(r"(\d+(?:\.\d+)?\s?(?:mm|x\s?\d+(?:\.\d+)?\s?mm)+)", re.I)
UNIT_NORMALIZE = {"TON": "MT", "TONS": "MT", "TONNE": "MT", "TONNES": "MT",
                  "NO": "NOS", "NOS": "NOS", "PC": "NOS", "PCS": "NOS",
                  "MT": "MT", "KG": "KG", "SQM": "SQM", "SQ M": "SQM", "SQ.M": "SQM", "M2": "SQM"}


def extract_text_pages(document_path: str) -> list[tuple[int, str]]:
    """Return numbered text sections from a supported tender document.

    PDF page numbers and XLSX worksheet numbers deliberately share the same
    return shape.  The caller persists the resulting reference as provenance;
    it never treats an extracted value as approved.
    """
    suffix = Path(document_path).suffix.lower()
    if suffix == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(document_path, read_only=True, data_only=True)
        pages: list[tuple[int, str]] = []
        for index, worksheet in enumerate(workbook.worksheets, start=1):
            rows = []
            for row in worksheet.iter_rows(values_only=True):
                values = [str(value).strip() for value in row if value is not None and str(value).strip()]
                if values:
                    rows.append(" | ".join(values))
            pages.append((index, f"Worksheet: {worksheet.title}\n" + "\n".join(rows)))
        return pages
    if suffix != ".pdf":
        raise ValueError("Only PDF and XLSX tender documents can be extracted")

    """PDF: pdfplumber primary, PyMuPDF fallback."""
    pages: list[tuple[int, str]] = []
    try:
        with pdfplumber.open(document_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                pages.append((i, page.extract_text() or ""))
        if any(t.strip() for _, t in pages):
            return pages
    except Exception:
        pages = []
    import fitz  # PyMuPDF fallback
    doc = fitz.open(document_path)
    return [(i + 1, doc[i].get_text() or "") for i in range(doc.page_count)]


def parse_boq_lines(text: str) -> list[dict]:
    """Rule-based BOQ candidate extraction from one page of text."""
    candidates = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) < 12:
            continue
        qty_match = QTY_PATTERN.search(line)
        if not qty_match:
            continue
        try:
            qty = Decimal(qty_match.group(1).replace(",", ""))
        except InvalidOperation:
            continue
        raw_unit = re.sub(r"\s+", " ", qty_match.group(2).upper()).replace("SQ. ", "SQ ")
        unit = UNIT_NORMALIZE.get(raw_unit, UNIT_NORMALIZE.get(raw_unit.rstrip("S").rstrip("E"), "MT"))
        if qty <= 0 or qty > Decimal("1000000"):
            continue  # implausible — likely a table artifact
        form = None
        for f, pat in FORM_PATTERNS:
            if re.search(pat, line, re.I):
                form = f
                break
        grade_match = GRADE_PATTERN.search(line)
        standard_match = STANDARD_PATTERN.search(line)
        dims = DIM_PATTERN.findall(line)
        candidates.append({
            "raw_description": line[:500],
            "form": form,
            "grade": grade_match.group(1).upper().replace(" ", "") if grade_match else None,
            "specification": {k: v for k, v in {"dimensions": dims or None, "standard": standard_match.group(0).upper().replace(" ", " ") if standard_match else None}.items() if v is not None},
            "quantity": str(q_qty(qty)),
            "unit": unit,
            "confidence": "0.65" if form and grade_match else "0.45",
        })
    return candidates


def detect_injection_warnings(text: str) -> list[str]:
    """Flag instruction-like content inside documents (prompt-injection hygiene)."""
    warnings = []
    for pat in (r"ignore (all|previous) instructions", r"system prompt", r"you are an? ai",
                r"disregard (the )?(above|previous)"):
        if re.search(pat, text, re.I):
            warnings.append("Document contains instruction-like text that was ignored.")
            break
    return warnings
