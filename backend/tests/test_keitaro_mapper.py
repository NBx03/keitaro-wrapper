from dataclasses import dataclass

import httpx
import pytest

from app.keitaro.client import (
    KeitaroBadRequestError,
    KeitaroClient,
    KeitaroError,
    KeitaroNotFoundError,
)
from app.keitaro.mapper import (
    build_create_campaign_payload,
    build_flow1_redirect_payload,
    build_flow2_offers_payload,
    build_tracking_url,
    build_update_stream_offers_payload,
)


@dataclass
class DummyOfferSpec:
    offer_keitaro_id: int
    draft_share: int


def test_mapper_campaign_and_flows() -> None:
    campaign_payload = build_create_campaign_payload(
        name="Test Camp",
        domain_id=1813,
        group_id=10332,
        traffic_source_id=836,
    )
    assert campaign_payload == {
        "name": "Test Camp",
        "type": "position",
        "state": "active",
        "domain_id": 1813,
        "group_id": 10332,
        "traffic_source_id": 836,
    }

    flow1 = build_flow1_redirect_payload(42, "cl")
    assert flow1 == {
        "campaign_id": 42,
        "name": "Geo CL",
        "type": "regular",
        "position": 1,
        "schema": "redirect",
        "action_type": "http",
        "action_payload": "https://google.com",
        "filters": [{"name": "country", "mode": "accept", "payload": ["CL"]}],
    }

    flow2 = build_flow2_offers_payload(42, 18001)
    assert flow2 == {
        "campaign_id": 42,
        "name": "Offers",
        "type": "default",
        "position": 2,
        "schema": "landings",
        "offers": [{"offer_id": 18001, "share": 100, "state": "active"}],
    }


def test_mapper_update_stream_preserves_raw_filters() -> None:
    raw = {
        "id": 99,
        "campaign_id": 42,
        "name": "Offers",
        "type": "regular",
        "position": 2,
        "schema": "landings",
        "filter_or": True,
        "filters": [{"name": "country", "mode": "accept", "payload": ["DE"]}],
        "offers": [{"offer_id": 18001, "share": 100, "state": "active"}],
        "created_at": "2026-11-25 00:00:00",
    }
    updated = build_update_stream_offers_payload(
        raw,
        [DummyOfferSpec(18001, 50), DummyOfferSpec(18002, 50)],
    )
    assert "id" not in updated
    assert "created_at" not in updated
    assert updated["filters"] == [{"name": "country", "mode": "accept", "payload": ["DE"]}]
    assert updated["filter_or"] is True
    assert updated["offers"] == [
        {"offer_id": 18001, "share": 50, "state": "active"},
        {"offer_id": 18002, "share": 50, "state": "active"},
    ]


def test_build_tracking_url() -> None:
    domains = {1813: {"id": 1813, "name": "kt-emulator.test", "is_ssl": True}}
    assert (
        build_tracking_url({"alias": "abc123", "domain_id": 1813}, domains)
        == "https://kt-emulator.test/abc123"
    )
    assert (
        build_tracking_url({"tracking_url": "https://custom.test/x"}, domains)
        == "https://custom.test/x"
    )


def test_keitaro_client_headers_and_error_mapping() -> None:
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(dict(request.headers))
        if request.url.path.endswith("/domains"):
            return httpx.Response(200, json=[{"id": 1813, "name": "kt-emulator.test"}])
        if request.url.path.endswith("/campaigns/999"):
            return httpx.Response(404, json={"message": "Not found"})
        if request.url.path.endswith("/streams"):
            return httpx.Response(422, json={"error": "Invalid payload"})
        return httpx.Response(500, text="Server error")

    client = KeitaroClient(
        base_url="https://example.test/admin_api/v1",
        api_key="secret-key",
        admin_url="https://example.test/admin",
        transport=httpx.MockTransport(handler),
    )
    assert client.list_domains() == [{"id": 1813, "name": "kt-emulator.test"}]
    assert seen_headers["api-key"] == "secret-key"
    assert seen_headers["user-agent"] == "keitaro-wrapper/0.1"
    assert client.build_admin_campaign_url(12) == "https://example.test/admin/#!/campaign.editor/12"

    with pytest.raises(KeitaroNotFoundError):
        client.get_campaign(999)
    with pytest.raises(KeitaroBadRequestError):
        client.create_stream({"name": "bad"})
    with pytest.raises(KeitaroError):
        client.list_offers()
    client.close()
