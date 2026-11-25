from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OfferOut(BaseModel):
    """Offer item returned by the offer search endpoint."""

    model_config = ConfigDict(from_attributes=True)

    keitaro_id: int
    name: str


class StreamOfferOut(BaseModel):
    """Offer row within a campaign stream, including draft and published states."""

    offer_keitaro_id: int
    offer_name: str
    draft_state: str
    draft_share: int
    published_state: str
    published_share: int
    is_pinned: bool


class StreamOut(BaseModel):
    """Stream representation with active offers sorted first and removed at the bottom."""

    id: int
    keitaro_id: int
    name: str
    position: int
    schema: str
    has_offers: bool
    is_dirty: bool
    total_active_share: int
    offers: list[StreamOfferOut]


class CampaignSummaryOut(BaseModel):
    """Campaign list item annotated with local synchronization flag."""

    keitaro_id: int
    name: str
    alias: str | None = None
    is_synced_locally: bool


class CampaignDetailOut(BaseModel):
    """Full campaign view including tracking links and ordered streams."""

    keitaro_id: int
    name: str
    alias: str | None = None
    tracking_url: str | None = None
    keitaro_admin_url: str
    domain_id: int | None = None
    group_id: int | None = None
    traffic_source_id: int | None = None
    last_fetched_at: datetime | None = None
    streams: list[StreamOut]


class CampaignCreateIn(BaseModel):
    """Payload to create a campaign with default Flow 1 (GEO) and Flow 2 (Offer)."""

    name: str = Field(min_length=1, max_length=255)
    geo: str = Field(min_length=2, max_length=2)
    offer_id: int = Field(gt=0)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Campaign name must not be empty")
        return cleaned

    @field_validator("geo")
    @classmethod
    def _validate_geo(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if len(cleaned) != 2 or not cleaned.isascii() or not cleaned.isalpha():
            raise ValueError("GEO must be a 2-letter ISO country code")
        return cleaned


class AddOfferIn(BaseModel):
    """Payload to add an offer to a stream draft."""

    offer_id: int = Field(gt=0)


class PinOfferIn(BaseModel):
    """Payload to pin or unpin an active offer in a stream."""

    is_pinned: bool
