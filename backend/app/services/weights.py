from collections.abc import Sequence
from typing import Protocol


class ShareItem(Protocol):
    """Protocol for stream-offer items participating in weight distribution."""

    draft_state: str
    draft_share: int
    is_pinned: bool


class DirtyCheckItem(Protocol):
    """Protocol for stream-offer items checked for unpublished draft changes."""

    published_state: str
    published_share: int
    draft_state: str
    draft_share: int


def recalculate_shares(items: Sequence[ShareItem]) -> None:
    """Redistribute remaining percentage evenly across unpinned active offers."""
    active = [item for item in items if item.draft_state == "active"]
    unpinned = [item for item in active if not item.is_pinned]
    if not unpinned:
        return

    pinned_sum = sum(item.draft_share for item in active if item.is_pinned)
    remaining = max(0, 100 - pinned_sum)
    base, rem = divmod(remaining, len(unpinned))
    for idx, item in enumerate(unpinned):
        item.draft_share = base + (1 if idx < rem else 0)


def compute_stream_dirty(stream_offers: Sequence[DirtyCheckItem]) -> bool:
    """Return True if any offer has unpublished state or active share changes."""
    return any(
        item.published_state != item.draft_state
        or (item.draft_state == "active" and item.published_share != item.draft_share)
        for item in stream_offers
    )
