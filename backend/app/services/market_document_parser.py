"""Deterministic CSV fixture parser. Parsed fixtures are never publishable."""
from dataclasses import dataclass
from hashlib import sha256
from datetime import date
from decimal import Decimal, InvalidOperation
import csv, io

@dataclass(frozen=True)
class ParseResult:
    parser_id:str; parser_version:str; checksum:str; status:str; candidates:list[dict]; errors:list[str]; publishable:bool=False

REQUIRED={"material_form","grade","region","price_per_unit","currency","unit","price_basis","observed_on"}
def parse_fixture_csv(content:bytes, *, parser_version="fixture-csv-v1")->ParseResult:
    checksum=sha256(content).hexdigest()
    try: rows=list(csv.DictReader(io.StringIO(content.decode("utf-8"))))
    except UnicodeDecodeError: return ParseResult("fixture-csv",parser_version,checksum,"REJECTED",[],["invalid utf-8"])
    if not rows or not REQUIRED.issubset(rows[0]): return ParseResult("fixture-csv",parser_version,checksum,"REJECTED",[],["unsupported layout or missing required columns"])
    out=[]; errors=[]; seen=set()
    for n,row in enumerate(rows,2):
      try:
       if not row["grade"].strip() or row["grade"].strip().upper() in {"UNKNOWN","AMBIGUOUS"}: raise ValueError("ambiguous grade")
       if row["unit"].strip().upper() not in {"MT","KG"}: raise ValueError("unsupported unit")
       if Decimal(row["price_per_unit"])<=0: raise ValueError("invalid price")
       date.fromisoformat(row["observed_on"])
       key=tuple(row[k].strip() for k in sorted(REQUIRED))
       if key in seen: raise ValueError("duplicate row")
       seen.add(key); out.append(row)
      except (ValueError,InvalidOperation,KeyError) as e: errors.append(f"row {n}: {e}")
    return ParseResult("fixture-csv",parser_version,checksum,"VALID" if not errors else "QUARANTINED",out,errors)
