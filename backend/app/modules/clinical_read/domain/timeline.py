from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from app.modules.clinical_read.domain.cursor import ChartCursor
from app.modules.clinical_read.domain.enums import TimelineSourceType


def comes_after_cursor(
    occurred_at: datetime,
    source_type: str,
    source_id: UUID,
    cursor: ChartCursor,
) -> bool:
    if occurred_at < cursor.occurred_at:
        return True
    if occurred_at > cursor.occurred_at:
        return False
    if source_type > cursor.source_type:
        return True
    if source_type < cursor.source_type:
        return False
    return source_id < cursor.source_id


def sort_timeline_rows[T](
    rows: Sequence[tuple[datetime, TimelineSourceType, UUID, T]],
) -> list[tuple[datetime, TimelineSourceType, UUID, T]]:
    return sorted(rows, key=lambda item: (-item[0].timestamp(), item[1].value, -item[2].int))


def paginate_timeline[T](
    rows: Sequence[tuple[datetime, TimelineSourceType, UUID, T]],
    *,
    limit: int,
    cursor: ChartCursor | None,
) -> tuple[list[T], bool, ChartCursor | None]:
    eligible = [
        row
        for row in rows
        if cursor is None or comes_after_cursor(row[0], row[1].value, row[2], cursor)
    ]
    ordered = sort_timeline_rows(eligible)
    page = ordered[:limit]
    has_more = len(ordered) > limit
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = ChartCursor(
            occurred_at=last[0],
            source_type=last[1].value,
            source_id=last[2],
        )
    return [item[3] for item in page], has_more, next_cursor
