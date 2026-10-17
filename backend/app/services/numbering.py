"""Org-scoped document numbering: PREFIX-YYYY-#### (per-org sequence, race-safe)."""
from datetime import datetime, timezone

from sqlalchemy import func, select


def next_number(db, model, org_id, number_col_name: str = "number", prefix: str = "DOC") -> str:
    year = datetime.now(timezone.utc).year
    like = f"{prefix}-{year}-%"
    col = getattr(model, number_col_name)
    count = db.scalar(
        select(func.count()).select_from(model).where(
            model.organization_id == org_id, col.like(like))) or 0
    return f"{prefix}-{year}-{count + 1:04d}"
