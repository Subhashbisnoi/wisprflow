"""Offset pagination shared by every list endpoint (D-059)."""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class PageParams:
    page: int = 1
    page_size: int = 25

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(25, ge=1, le=MAX_PAGE_SIZE, description="Rows per page"),
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


@dataclass
class Page[T]:
    items: Sequence[T]
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        return math.ceil(self.total / self.page_size) if self.total else 0

    def map[U](self, fn: Callable[[T], U]) -> "Page[U]":
        return Page([fn(i) for i in self.items], self.page, self.page_size, self.total)


class PageOut[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int
    total_pages: int

    @classmethod
    def from_page(cls, page: Page[Any]) -> "PageOut[T]":
        return cls(
            items=list(page.items),
            page=page.page,
            page_size=page.page_size,
            total=page.total,
            total_pages=page.total_pages,
        )


def paginate[T](session: Session, stmt: Select[T], params: PageParams) -> Page[T]:
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = session.scalars(stmt.limit(params.page_size).offset(params.offset)).all()
    return Page(items=items, page=params.page, page_size=params.page_size, total=total)
