import pytest
from sqlalchemy.orm import Session

from app.models import Campaign, Stream
from app.services.campaigns import (
    create_campaign_with_flows,
    fetch_campaign_streams,
    list_campaigns,
    search_offers,
)
from app.services.exceptions import ConflictError, ExternalServiceError, ValidationError
from app.services.streams import (
    add_offer,
    bring_back_offer,
    cancel_stream_draft,
    push_stream_to_kt,
    remove_offer,
    toggle_pin,
)
from app.services.weights import compute_stream_dirty
from tests.conftest import FakeKeitaroClient


def _offer_stream(campaign: Campaign) -> Stream:
    for stream in campaign.streams:
        if stream.has_offers:
            return stream
    raise AssertionError("Expected at least one offer stream")


def test_create_campaign_with_flows_and_list(
    db_session: Session,
    fake_kt: FakeKeitaroClient,
) -> None:
    campaign = create_campaign_with_flows(
        db_session,
        fake_kt,  # type: ignore[arg-type]
        name="CL Hair Test",
        geo="cl",
        offer_id=18001,
    )

    assert campaign.domain_id == 1813
    assert campaign.group_id == 10332
    assert campaign.traffic_source_id == 836
    assert campaign.tracking_url == f"https://kt-emulator.test/cmp-{campaign.keitaro_id}"
    assert len(campaign.streams) == 2

    flow1, flow2 = sorted(campaign.streams, key=lambda s: s.position)
    assert flow1.has_offers is False
    assert flow1.schema == "redirect"
    assert flow1.raw_payload["action_payload"] == "https://google.com"
    assert flow1.raw_payload["filters"] == [
        {"name": "country", "mode": "accept", "payload": ["CL"]}
    ]
    assert flow1.stream_offers == []

    assert flow2.has_offers is True
    assert flow2.schema == "landings"
    assert len(flow2.stream_offers) == 1
    assert flow2.stream_offers[0].offer_keitaro_id == 18001
    assert flow2.stream_offers[0].draft_share == 100
    assert compute_stream_dirty(flow2.stream_offers) is False

    campaigns_list = list_campaigns(db_session, fake_kt)  # type: ignore[arg-type]
    assert len(campaigns_list) == 1
    assert campaigns_list[0]["is_synced"] is True
    assert campaigns_list[0]["admin_url"].endswith(f"/#!/campaign.editor/{campaign.keitaro_id}")


def test_create_campaign_validation_and_stream_failure(
    db_session: Session,
    fake_kt: FakeKeitaroClient,
) -> None:
    with pytest.raises(ValidationError):
        create_campaign_with_flows(
            db_session,
            fake_kt,  # type: ignore[arg-type]
            name="Bad Geo",
            geo="USA",
            offer_id=18001,
        )

    with pytest.raises(ValidationError):
        create_campaign_with_flows(
            db_session,
            fake_kt,  # type: ignore[arg-type]
            name="Bad Offer",
            geo="US",
            offer_id=999999,
        )

    fake_kt.fail_on_stream_create = True
    with pytest.raises(ExternalServiceError, match="stream creation failed"):
        create_campaign_with_flows(
            db_session,
            fake_kt,  # type: ignore[arg-type]
            name="Broken Streams",
            geo="DE",
            offer_id=18001,
        )


def test_lifecycle_fetch_add_cancel(db_session: Session, fake_kt: FakeKeitaroClient) -> None:
    campaign = create_campaign_with_flows(
        db_session,
        fake_kt,  # type: ignore[arg-type]
        name="Cancel Flow",
        geo="CL",
        offer_id=18001,
    )
    stream = _offer_stream(campaign)

    stream = add_offer(db_session, fake_kt, stream.id, 18002)  # type: ignore[arg-type]
    assert compute_stream_dirty(stream.stream_offers) is True
    assert sorted((o.offer_keitaro_id, o.draft_share) for o in stream.stream_offers) == [
        (18001, 50),
        (18002, 50),
    ]

    with pytest.raises(ConflictError):
        add_offer(db_session, fake_kt, stream.id, 18002)  # type: ignore[arg-type]

    stream = cancel_stream_draft(db_session, stream.id)
    assert compute_stream_dirty(stream.stream_offers) is False
    assert [(o.offer_keitaro_id, o.draft_share) for o in stream.stream_offers] == [(18001, 100)]


def test_lifecycle_remove_push_bring_back_push(
    db_session: Session,
    fake_kt: FakeKeitaroClient,
) -> None:
    campaign = create_campaign_with_flows(
        db_session,
        fake_kt,  # type: ignore[arg-type]
        name="Remove Bring Back",
        geo="BR",
        offer_id=18001,
    )
    stream = _offer_stream(campaign)

    stream = add_offer(db_session, fake_kt, stream.id, 18002)  # type: ignore[arg-type]
    stream = push_stream_to_kt(db_session, fake_kt, stream.id)  # type: ignore[arg-type]
    assert compute_stream_dirty(stream.stream_offers) is False

    stream = remove_offer(db_session, stream.id, 18002)
    assert compute_stream_dirty(stream.stream_offers) is True
    by_id = {o.offer_keitaro_id: o for o in stream.stream_offers}
    assert by_id[18001].draft_share == 100
    assert by_id[18002].draft_state == "removed"
    assert by_id[18002].draft_share == 0

    stream = push_stream_to_kt(db_session, fake_kt, stream.id)  # type: ignore[arg-type]
    assert compute_stream_dirty(stream.stream_offers) is False
    assert fake_kt.streams[stream.keitaro_id]["offers"] == [
        {"offer_id": 18001, "share": 100, "state": "active"}
    ]
    by_id = {o.offer_keitaro_id: o for o in stream.stream_offers}
    assert by_id[18002].published_state == "removed"
    assert by_id[18002].draft_state == "removed"

    stream = bring_back_offer(db_session, stream.id, 18002)
    assert compute_stream_dirty(stream.stream_offers) is True
    by_id = {o.offer_keitaro_id: o for o in stream.stream_offers}
    assert by_id[18001].draft_share == 50
    assert by_id[18002].draft_state == "active"
    assert by_id[18002].draft_share == 50

    stream = push_stream_to_kt(db_session, fake_kt, stream.id)  # type: ignore[arg-type]
    assert compute_stream_dirty(stream.stream_offers) is False
    assert len(fake_kt.streams[stream.keitaro_id]["offers"]) == 2


def test_pin_does_not_dirty_and_preserves_share(
    db_session: Session,
    fake_kt: FakeKeitaroClient,
) -> None:
    campaign = create_campaign_with_flows(
        db_session,
        fake_kt,  # type: ignore[arg-type]
        name="Pin Test",
        geo="MX",
        offer_id=18001,
    )
    stream = _offer_stream(campaign)
    for oid in (18002, 18003, 18004):
        stream = add_offer(db_session, fake_kt, stream.id, oid)  # type: ignore[arg-type]
    stream = push_stream_to_kt(db_session, fake_kt, stream.id)  # type: ignore[arg-type]

    # All 4 at 25%; pin 18001 at 25% -> still clean
    stream = toggle_pin(db_session, stream.id, 18001, True)
    assert compute_stream_dirty(stream.stream_offers) is False

    # Remove 18004 -> 18001 stays 25%, remaining 75% splits 38/37 across 18002 & 18003
    stream = remove_offer(db_session, stream.id, 18004)
    by_id = {o.offer_keitaro_id: o for o in stream.stream_offers}
    assert by_id[18001].draft_share == 25
    assert by_id[18002].draft_share == 38
    assert by_id[18003].draft_share == 37

    # Bring back 18004 -> 18001 stays 25%, remaining 75% splits 25/25/25 across 3 unpinned
    stream = bring_back_offer(db_session, stream.id, 18004)
    by_id = {o.offer_keitaro_id: o for o in stream.stream_offers}
    assert by_id[18001].draft_share == 25
    assert by_id[18002].draft_share == 25
    assert by_id[18003].draft_share == 25
    assert by_id[18004].draft_share == 25


def test_external_deletion_in_kt_fetch_preserves_remote_shares(
    db_session: Session,
    fake_kt: FakeKeitaroClient,
) -> None:
    campaign = create_campaign_with_flows(
        db_session,
        fake_kt,  # type: ignore[arg-type]
        name="External Delete",
        geo="DE",
        offer_id=18001,
    )
    stream = _offer_stream(campaign)
    for oid in (18002, 18003, 18004):
        stream = add_offer(db_session, fake_kt, stream.id, oid)  # type: ignore[arg-type]
    stream = push_stream_to_kt(db_session, fake_kt, stream.id)  # type: ignore[arg-type]

    # Simulate external edit in Keitaro leaving only 18001 (25%) and 18002 (25%)
    fake_kt.streams[stream.keitaro_id]["offers"] = [
        {"offer_id": 18001, "share": 25, "state": "active"},
        {"offer_id": 18002, "share": 25, "state": "active"},
    ]

    campaign = fetch_campaign_streams(db_session, fake_kt, campaign.keitaro_id)  # type: ignore[arg-type]
    stream = _offer_stream(campaign)
    assert compute_stream_dirty(stream.stream_offers) is False
    by_id = {o.offer_keitaro_id: o for o in stream.stream_offers}

    assert by_id[18001].published_share == 25
    assert by_id[18001].draft_share == 25
    assert by_id[18002].published_share == 25
    assert by_id[18002].draft_share == 25
    assert by_id[18003].published_state == "removed"
    assert by_id[18003].draft_share == 0
    assert by_id[18004].published_state == "removed"
    assert by_id[18004].draft_share == 0

    # Pin 18001 at 25% and Bring Back 18003 -> 18001=25, 18002=38, 18003=37
    stream = toggle_pin(db_session, stream.id, 18001, True)
    stream = bring_back_offer(db_session, stream.id, 18003)
    by_id = {o.offer_keitaro_id: o for o in stream.stream_offers}
    assert by_id[18001].draft_share == 25
    assert by_id[18002].draft_share == 38
    assert by_id[18003].draft_share == 37


def test_empty_landings_stream_keeps_has_offers_and_push_validation(
    db_session: Session,
    fake_kt: FakeKeitaroClient,
) -> None:
    campaign = create_campaign_with_flows(
        db_session,
        fake_kt,  # type: ignore[arg-type]
        name="Empty Landings",
        geo="CL",
        offer_id=18001,
    )
    stream = _offer_stream(campaign)

    # Externally empty offers in Keitaro while keeping schema="landings"
    fake_kt.streams[stream.keitaro_id]["offers"] = []
    campaign = fetch_campaign_streams(db_session, fake_kt, campaign.keitaro_id)  # type: ignore[arg-type]
    stream = _offer_stream(campaign)
    assert stream.has_offers is True
    assert stream.stream_offers[0].published_state == "removed"

    # Pushing 0 active offers raises ValidationError (422)
    with pytest.raises(ValidationError, match="At least one active offer"):
        push_stream_to_kt(db_session, fake_kt, stream.id)  # type: ignore[arg-type]

    # Bring back -> 100%, then add 18002 while pinning 18001 at 100% -> 18002 gets 0% -> 422 on push
    stream = bring_back_offer(db_session, stream.id, 18001)
    stream = toggle_pin(db_session, stream.id, 18001, True)
    stream = add_offer(db_session, fake_kt, stream.id, 18002)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="between 1% and 100%"):
        push_stream_to_kt(db_session, fake_kt, stream.id)  # type: ignore[arg-type]


def test_search_offers_case_insensitive_and_by_id(
    db_session: Session,
    fake_kt: FakeKeitaroClient,
) -> None:
    by_name = search_offers(db_session, fake_kt, query="detoxin")  # type: ignore[arg-type]
    assert [o.keitaro_id for o in by_name] == [18001]

    by_id = search_offers(db_session, fake_kt, query="18003")  # type: ignore[arg-type]
    assert [o.keitaro_id for o in by_id] == [18003]
