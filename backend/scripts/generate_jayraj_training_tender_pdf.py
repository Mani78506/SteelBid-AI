"""Generate a clearly labelled, upload-ready SteelBid training tender PDF."""
from __future__ import annotations

from pathlib import Path


OUT = Path(__file__).resolve().parents[1] / "demo-assets" / "jayraj_structural_steel_training_tender.pdf"

PAGES = [
    [
        "JAYRAJ STEEL PRIVATE LIMITED — TRAINING WORKSPACE",
        "SIMULATED TENDER DOCUMENT — TRAINING ONLY — NOT FOR EXTERNAL SUBMISSION",
        "Tender reference: DEMO-JRS-STRUCT-2026-001",
        "Title: Structural Steel Supply for Industrial Warehouse Training Package",
        "Issue date: 16 November 2026    |    Response due: 30 November 2026",
        "Customer: [TRAINING] Industrial Warehouse Customer",
        "Location: Simulated training location, Hyderabad",
        "",
        "1. PURPOSE",
        "This fictional document is supplied solely for SteelBid workflow training.",
        "It does not represent an invitation from a government body, customer, or portal.",
        "No external submission, commercial commitment, or price reliance is permitted.",
        "",
        "2. REQUIRED PROCESS",
        "Upload this PDF, extract the BOQ, review every extracted line, map compatible",
        "materials, approve the BOQ, generate the BOM, and review stock shortages.",
        "All later procurement, costing, quotation and submission records remain simulated.",
    ],
    [
        "JAYRAJ STEEL PRIVATE LIMITED — TRAINING WORKSPACE",
        "SIMULATED BOQ — DEMO-JRS-STRUCT-2026-001",
        "",
        "3. BILL OF QUANTITIES",
        "Line | Material description                                      | Grade  | Qty     | Unit",
        "ST-01| ISMB 300 structural beam, IS 2062                      | E250   | 24.000  | MT",
        "ST-02| ISMC 200 structural channel, IS 2062                   | E250   | 12.000  | MT",
        "ST-03| ISA 75 x 75 x 6 structural angle, IS 2062              | E250   | 8.000   | MT",
        "ST-04| Mild steel plate, 10 mm, IS 2062                       | E250   | 16.000  | MT",
        "ST-05| GI sheet, Z120 coating, IS 277                         | Z120   | 4200.00 | SQM",
        "ST-06| TMT reinforcement bar, 12 mm, IS 1786                  | Fe 500D| 10.000  | MT",
        "ST-07| TMT reinforcement bar, 16 mm, IS 1786                  | Fe 550D| 6.000   | MT",
        "",
        "Unit rule: MT and SQM are separate requirements and must never be combined.",
        "Quality rule: only compatible, quality-OK, unreserved stock may be allocated.",
        "",
        "4. TRAINING COMMERCIAL RULES",
        "Supplier offers, rates, freight, overhead, margin and tax must be persisted",
        "as simulated training inputs with provenance. Draft RFQs are not transmitted.",
        "A separate authorized training identity is required for commercial approval.",
    ],
    [
        "JAYRAJ STEEL PRIVATE LIMITED — TRAINING WORKSPACE",
        "SIMULATED TENDER DOCUMENT — WORKFLOW AND EVIDENCE",
        "",
        "5. ACCEPTANCE CRITERIA",
        "- Preserve the original material description, grade, dimensions, quantity and unit.",
        "- Record extraction evidence and require human review before BOM generation.",
        "- Keep eligible, reserved, quality-held, allocated and available stock separate.",
        "- Exclude expired or incompatible supplier offers from selection.",
        "- Mark all quotation and submission activity as simulated training activity.",
        "",
        "6. DOCUMENT CONTROL",
        "Classification: SIMULATED TRAINING DATA",
        "Source: SteelBid internal demonstration fixture",
        "Reuse: Permitted only inside the SteelBid training workspace",
        "External portal reference: None",
        "",
        "END OF SIMULATED TRAINING TENDER",
    ],
]


def esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
    page_ids: list[int] = []
    for lines in PAGES:
        page_ids.append(len(objects) + 1)
        objects.extend([b"", b""])
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
    font_id = len(objects) + 1
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, lines in enumerate(PAGES):
        page_id, content_id = page_ids[index], page_ids[index] + 1
        body = ["BT", "/F1 10 Tf", "48 790 Td", "14 TL"]
        for line_no, line in enumerate(lines):
            if line_no == 0:
                body.extend(["/F1 15 Tf", f"({esc(line)}) Tj", "/F1 10 Tf", "T*"])
            elif line.startswith("SIMULATED"):
                body.extend(["/F1 9 Tf", f"({esc(line)}) Tj", "/F1 10 Tf", "T*"])
            else:
                body.extend([f"({esc(line)}) Tj", "T*"])
        body.append("ET")
        stream = "\n".join(body).encode("latin-1", "replace")
        objects[page_id - 1] = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode()
        objects[content_id - 1] = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    OUT.write_bytes(result)
    print(OUT)


if __name__ == "__main__": main()
