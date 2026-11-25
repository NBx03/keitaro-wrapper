import copy
from collections.abc import Sequence
from typing import Any, Protocol


class ActiveOfferSpec(Protocol):
    """Minimal attributes required to serialize an active stream offer."""

    offer_keitaro_id: int
    draft_share: int


def build_create_campaign_payload(
    *,
    name: str,
    domain_id: int | None = None,
    group_id: int | None = None,
    traffic_source_id: int | None = None,
) -> dict[str, Any]:
    """Build the POST /campaigns payload with position-based stream rotation."""
    payload: dict[str, Any] = {
        "name": name,
        "type": "position",
        "state": "active",
    }
    if domain_id is not None:
        payload["domain_id"] = domain_id
    if group_id is not None:
        payload["group_id"] = group_id
    if traffic_source_id is not None:
        payload["traffic_source_id"] = traffic_source_id
    return payload


def build_flow1_redirect_payload(campaign_keitaro_id: int, geo: str) -> dict[str, Any]:
    """Build POST /streams payload for Flow 1 (ISO country filter -> Google redirect)."""
    country_code = geo.strip().upper()
    return {
        "campaign_id": campaign_keitaro_id,
        "name": f"Geo {country_code}",
        "type": "regular",
        "position": 1,
        "schema": "redirect",
        "action_type": "http",
        "action_payload": "https://google.com",
        "filters": [
            {
                "name": "country",
                "mode": "accept",
                "payload": [country_code],
            }
        ],
    }


def build_flow2_offers_payload(campaign_keitaro_id: int, offer_id: int) -> dict[str, Any]:
    """Build POST /streams payload for Flow 2 (default stream with a 100% offer)."""
    return {
        "campaign_id": campaign_keitaro_id,
        "name": "Offers",
        "type": "default",
        "position": 2,
        "schema": "landings",
        "offers": [
            {
                "offer_id": offer_id,
                "share": 100,
                "state": "active",
            }
        ],
    }


def build_update_stream_offers_payload(
    raw_payload: dict[str, Any],
    active_offers: Sequence[ActiveOfferSpec],
) -> dict[str, Any]:
    """Build PUT /streams/{id} payload preserving raw settings and replacing offers."""
    payload = copy.deepcopy(raw_payload)
    for readonly_key in ("id", "created_at", "updated_at"):
        payload.pop(readonly_key, None)

    payload["offers"] = [
        {
            "offer_id": item.offer_keitaro_id,
            "share": item.draft_share,
            "state": "active",
        }
        for item in active_offers
    ]
    return payload


def build_tracking_url(
    campaign_data: dict[str, Any],
    domains_by_id: dict[int, dict[str, Any]] | None = None,
) -> str | None:
    """Resolve the public campaign tracking URL from campaign data and domain catalog."""
    direct_url = campaign_data.get("tracking_url")
    if isinstance(direct_url, str) and direct_url:
        return direct_url

    alias = campaign_data.get("alias")
    domain_id = campaign_data.get("domain_id")
    if not alias or domain_id is None or not domains_by_id:
        return None

    domain = domains_by_id.get(int(domain_id))
    if not domain or not domain.get("name"):
        return None

    scheme = "https" if domain.get("is_ssl", True) else "http"
    return f"{scheme}://{domain['name']}/{alias}"
