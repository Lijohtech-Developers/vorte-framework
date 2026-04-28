"""
Vorte Pagination
================
Cursor-based and offset pagination for SQLAlchemy async queries.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, Sequence, Type, TypeVar

from sqlalchemy import Column, desc, asc, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from vorte.modules.database.model import VorteModel

T = TypeVar("T", bound=VorteModel)


# ---------------------------------------------------------------------------
# Offset pagination result
# ---------------------------------------------------------------------------

@dataclass
class OffsetPage(Generic[T]):
    """Offset-based pagination result."""

    items: List[T]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [item.to_dict() if hasattr(item, "to_dict") else item for item in self.items],
            "total": self.total,
            "page": self.page,
            "per_page": self.per_page,
            "total_pages": self.total_pages,
            "has_next": self.has_next,
            "has_prev": self.has_prev,
        }


# ---------------------------------------------------------------------------
# Cursor pagination result
# ---------------------------------------------------------------------------

@dataclass
class CursorPage(Generic[T]):
    """Cursor-based pagination result.

    Provides opaque ``next_cursor`` / ``prev_cursor`` tokens that encode the
    sort position, avoiding the inefficiency of large ``OFFSET`` values.
    """

    items: List[T]
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None
    has_next: bool = False
    has_prev: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [item.to_dict() if hasattr(item, "to_dict") else item for item in self.items],
            "next_cursor": self.next_cursor,
            "prev_cursor": self.prev_cursor,
            "has_next": self.has_next,
            "has_prev": self.has_prev,
        }


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------

def _encode_cursor(values: Dict[str, Any]) -> str:
    """Encode cursor values into an opaque base64 string."""
    payload = json.dumps(values, sort_keys=True, default=str)
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> Dict[str, Any]:
    """Decode an opaque cursor string back into its values."""
    # Restore padding
    padding = 4 - len(cursor) % 4
    if padding != 4:
        cursor += "=" * padding
    payload = base64.urlsafe_b64decode(cursor.encode()).decode()
    return json.loads(payload)


# ---------------------------------------------------------------------------
# Offset paginator
# ---------------------------------------------------------------------------

class OffsetPaginator:
    """Stateless offset-based pagination helper.

    Usage::

        page = await OffsetPaginator.paginate(
            session, User, page=2, per_page=20,
        )
    """

    @staticmethod
    async def paginate(
        session: AsyncSession,
        model: Type[T],
        *,
        page: int = 1,
        per_page: int = 20,
        stmt: Optional[Any] = None,
        order_by: Optional[Any] = None,
    ) -> OffsetPage[T]:
        """
        Execute an offset-paginated query.

        Args:
            session: The async session.
            model: The SQLAlchemy model class.
            page: 1-based page number.
            per_page: Items per page.
            stmt: Optional base select statement (defaults to ``select(model)``).
            order_by: Optional order-by clause.

        Returns:
            An :class:`OffsetPage` with results and metadata.
        """
        if page < 1:
            page = 1
        if per_page < 1:
            per_page = 20
        if per_page > 100:
            per_page = 100

        base = stmt or select(model)
        if order_by is not None:
            base = base.order_by(order_by)

        # Count total
        from sqlalchemy import func as sa_func
        count_stmt = select(sa_func.count()).select_from(base.subquery())
        result = await session.execute(count_stmt)
        total = result.scalar() or 0

        # Fetch page
        offset = (page - 1) * per_page
        page_stmt = base.offset(offset).limit(per_page)
        result = await session.execute(page_stmt)
        items = list(result.scalars().all())

        total_pages = max(1, (total + per_page - 1) // per_page)

        return OffsetPage(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )


# ---------------------------------------------------------------------------
# Cursor paginator
# ---------------------------------------------------------------------------

class CursorPaginator:
    """Stateless cursor-based pagination helper.

    By default uses the model's ``id`` (UUID) column as the cursor column.
    Supports multi-column sorting and both ascending / descending order.

    Usage::

        page = await CursorPaginator.paginate(
            session, User, cursor=request.args.get("cursor"), limit=20,
        )
    """

    DEFAULT_LIMIT = 20
    MAX_LIMIT = 100

    @staticmethod
    async def paginate(
        session: AsyncSession,
        model: Type[T],
        *,
        cursor: Optional[str] = None,
        limit: int = DEFAULT_LIMIT,
        cursor_column: Optional[str] = None,
        direction: str = "next",
        order_desc: bool = True,
        stmt: Optional[Any] = None,
        filters: Optional[Any] = None,
    ) -> CursorPage[T]:
        """
        Execute a cursor-paginated query.

        Args:
            session: The async session.
            model: The SQLAlchemy model class.
            cursor: Opaque cursor token from a previous page.
            limit: Maximum items to return.
            cursor_column: Column name to use for cursoring (default: ``id``).
            direction: ``"next"`` or ``"prev"``.
            order_desc: If *True*, sort descending (newest first).
            stmt: Optional base select (defaults to ``select(model)``).
            filters: Optional WHERE clause already attached to *stmt*.

        Returns:
            A :class:`CursorPage` with results and cursor tokens.
        """
        if limit < 1:
            limit = CursorPaginator.DEFAULT_LIMIT
        if limit > CursorPaginator.MAX_LIMIT:
            limit = CursorPaginator.MAX_LIMIT

        # Resolve cursor column
        col_name = cursor_column or "id"
        cursor_col = getattr(model, col_name)

        base = stmt or select(model)
        if filters is not None:
            base = base.where(filters)

        # Determine sort direction
        if order_desc:
            base_order = desc(cursor_col)
        else:
            base_order = asc(cursor_col)

        # Apply cursor filtering
        decoded: Optional[Dict[str, Any]] = None
        if cursor:
            try:
                decoded = _decode_cursor(cursor)
            except Exception:
                decoded = None

        if decoded and col_name in decoded:
            cursor_value = decoded[col_name]
            if order_desc:
                if direction == "next":
                    base = base.where(cursor_col < cursor_value)
                else:
                    base = base.where(cursor_col > cursor_value)
            else:
                if direction == "next":
                    base = base.where(cursor_col > cursor_value)
                else:
                    base = base.where(cursor_col < cursor_value)

        # Apply ordering
        base = base.order_by(base_order)

        # Fetch one extra to determine has_next / has_prev
        result = await session.execute(base.limit(limit + 1))
        rows = list(result.scalars().all())

        has_extra = len(rows) > limit
        items = rows[:limit]

        # Build cursors
        next_cursor: Optional[str] = None
        prev_cursor: Optional[str] = None

        if items:
            last_item = items[-1]
            last_val = getattr(last_item, col_name, None)
            if isinstance(last_val, datetime):
                last_val = last_val.isoformat()
            next_cursor = _encode_cursor({col_name: last_val})

            first_item = items[0]
            first_val = getattr(first_item, col_name, None)
            if isinstance(first_val, datetime):
                first_val = first_val.isoformat()
            prev_cursor = _encode_cursor({col_name: first_val})

        if order_desc:
            has_next = has_extra
            has_prev = cursor is not None and direction != "prev" and bool(items)
        else:
            has_next = has_extra
            has_prev = cursor is not None and direction != "prev" and bool(items)

        return CursorPage(
            items=items,
            next_cursor=next_cursor if has_next else None,
            prev_cursor=prev_cursor if has_prev else None,
            has_next=has_next,
            has_prev=has_prev,
        )
