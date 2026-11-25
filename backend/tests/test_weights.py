from dataclasses import dataclass

from app.services.weights import compute_stream_dirty, recalculate_shares


@dataclass
class DummyShareItem:
    draft_state: str
    draft_share: int
    is_pinned: bool


@dataclass
class DummyDirtyItem:
    published_state: str
    published_share: int
    draft_state: str
    draft_share: int


def test_recalculate_shares_four_unpinned() -> None:
    items = [DummyShareItem("active", 0, False) for _ in range(4)]
    recalculate_shares(items)
    assert [i.draft_share for i in items] == [25, 25, 25, 25]


def test_recalculate_shares_three_unpinned() -> None:
    items = [DummyShareItem("active", 0, False) for _ in range(3)]
    recalculate_shares(items)
    assert [i.draft_share for i in items] == [34, 33, 33]


def test_recalculate_shares_one_pinned_25_two_unpinned() -> None:
    items = [
        DummyShareItem("active", 25, True),
        DummyShareItem("active", 10, False),
        DummyShareItem("active", 10, False),
    ]
    recalculate_shares(items)
    assert [i.draft_share for i in items] == [25, 38, 37]


def test_recalculate_shares_all_pinned_unchanged() -> None:
    items = [
        DummyShareItem("active", 60, True),
        DummyShareItem("active", 40, True),
    ]
    recalculate_shares(items)
    assert [i.draft_share for i in items] == [60, 40]


def test_recalculate_shares_zero_active_and_ignores_removed() -> None:
    items = [
        DummyShareItem("removed", 0, False),
        DummyShareItem("removed", 0, True),
    ]
    recalculate_shares(items)
    assert [i.draft_share for i in items] == [0, 0]

    mixed = [
        DummyShareItem("removed", 0, False),
        DummyShareItem("active", 50, False),
        DummyShareItem("active", 50, False),
    ]
    recalculate_shares(mixed)
    assert [i.draft_share for i in mixed] == [0, 50, 50]


def test_recalculate_shares_pinned_sum_exceeds_or_equals_100() -> None:
    items = [
        DummyShareItem("active", 70, True),
        DummyShareItem("active", 40, True),
        DummyShareItem("active", 20, False),
    ]
    recalculate_shares(items)
    assert [i.draft_share for i in items] == [70, 40, 0]


def test_compute_stream_dirty() -> None:
    clean = [
        DummyDirtyItem("active", 50, "active", 50),
        DummyDirtyItem("removed", 0, "removed", 0),
    ]
    assert compute_stream_dirty(clean) is False

    state_changed = [
        DummyDirtyItem("none", 0, "active", 100),
    ]
    assert compute_stream_dirty(state_changed) is True

    removed_changed = [
        DummyDirtyItem("active", 50, "removed", 0),
    ]
    assert compute_stream_dirty(removed_changed) is True

    share_changed = [
        DummyDirtyItem("active", 50, "active", 34),
    ]
    assert compute_stream_dirty(share_changed) is True
