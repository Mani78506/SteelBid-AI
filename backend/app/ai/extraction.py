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
from decimal import Decimal, InvalidOperation

import pdfplumber

from app.calc.finance import q_qty

FORM_PATTERNS = [
    ("PLATE", r"\b(plates?|ms plate|chequered plate)\b"),
    ("BEAM", r"\b(i\s?beams?|is-\s?mb|universal beams?|ub\b| beams?)\b"),
    ("CHANNEL", r"\bchannels?\b"),
    ("ANGLE", r"\bangles?\b"),
    ("PIPE", r"\bpipes?\b"),
    ("RHS", r"\b(rhs|rectangular hollow)\b"),
    ("SHS", r"\b(shs|square hollow)\b"),
    ("COIL", r"\b(hr coils?|cr coils?|coils?)\b"),
    ("SHEET", r"\b(gp sheets?|sheets?)\b"),
    ("REBAR", r"\b(tmt|rebars?|reinforcement bars?)\b"),
    ("CHEQUERED", r"\bchequered\b"),
    ("ROUND_BAR", r"\b(round bars?|bright bars?|rounds)\b"),
]
GRADE_PATTERN = re.compile(r"\b(E\d{3}[A-Z]{0,3}|IS\s?\d{3,5}|FE\s?\d{3}[A-Z]{0,2}|ASTM\s?A\d+|S\s?\d{3}[A-Z]{0,3})\b", re.I)
QTY_PATTERN = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(MT|KG|TON(?:NE)?S?|NOS?|PCS)\b", re.I)
DIM_PATTERN = re.compile(r"(\d+(?:\.\d+)?\s?(?:mm|x\s?\d+(?:\.\d+)?\s?mm)+)", re.I)
UNIT_NORMALIZE = {"TON": "MT", "TONS": "MT", "TONNE": "MT", "TONNES": "MT",
                  "NO": "NOS", "NOS": "NOS", "PC": "NOS", "PCS": "NOS",
                  "MT": "MT", "KG": "KG"}


def extract_text_pages(pdf_path: str) -> list[tuple[int, str]]:
    """Return [(page_number, text)]. pdfplumber primary, PyMuPDF fallback."""
    pages: list[tuple[int, str]] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                pages.append((i, page.extract_text() or ""))
        if any(t.strip() for _, t in pages):
            return pages
    except Exception:
        pages = []
    import fitz  # PyMuPDF fallback
    doc = fitz.open(pdf_path)
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
        unit = UNIT_NORMALIZE.get(qty_match.group(2).upper().rstrip("S").rstrip("E"), "MT")
        if qty <= 0 or qty > Decimal("1000000"):
            continue  # implausible — likely a table artifact
        form = None
        for f, pat in FORM_PATTERNS:
            if re.search(pat, line, re.I):
                form = f
                break
        grade_match = GRADE_PATTERN.search(line)
        dims = DIM_PATTERN.findall(line)
        candidates.append({
            "raw_description": line[:500],
            "form": form,
            "grade": grade_match.group(1).upper().replace(" ", "") if grade_match else None,
            "specification": {"dimensions": dims} if dims else {},
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
