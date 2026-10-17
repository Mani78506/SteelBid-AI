"""Pagination + sorting helpers used by all list endpoints."""
from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, asc, desc, func, select

T = TypeVar("T")
MAX_PAGE_SIZE = 100


class PageParams:
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
        sort: str | None = Query(None),
    ):
        self.page = page
        self.page_size = page_size
        self.sort = sort


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


def apply_sort(stmt: Select, sort: str | None, sortable: dict[str, Any], default: Any) -> Select:
    if not sort:
        return stmt.order_by(default)
    key = sort.lstrip("-")
    col = sortable.get(key, default)
    return stmt.order_by(desc(col) if sort.startswith("-") else asc(col))


def paginate(db, stmt: Select, params: PageParams) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.offset((params.page - 1) * params.page_size).limit(params.page_size)).all()
    return list(rows), total


def dec(value) -> str | None:
    """Serialize Decimal safely to string."""
    return None if value is None else str(value)
