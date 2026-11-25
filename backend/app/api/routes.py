from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.keitaro.client import KeitaroClient
from app.models import Campaign, Stream, StreamOffer
from app.schemas import (
    AddOfferIn,
    CampaignCreateIn,
    CampaignDetailOut,
    CampaignSummaryOut,
    OfferOut,
    PinOfferIn,
    StreamOfferOut,
    StreamOut,
)
from app.services.campaigns import (
    create_campaign_with_flows,
    fetch_campaign_streams,
    list_campaigns,
    search_offers,
)
from app.services.streams import (
    add_offer,
    bring_back_offer,
    cancel_stream_draft,
    push_stream_to_kt,
    remove_offer,
    toggle_pin,
)
from app.services.weights import compute_stream_dirty

router = APIRouter(prefix="/api")


def get_keitaro_client(request: Request) -> KeitaroClient:
    """Provide a shared keep-alive KeitaroClient from FastAPI app state."""
    client: KeitaroClient | None = getattr(request.app.state, "keitaro_client", None)
    if client is None:
        client = KeitaroClient()
        request.app.state.keitaro_client = client
    return client


def _to_stream_out(stream: Stream) -> StreamOut:
    ordered = sorted(
        stream.stream_offers,
        key=lambda o: (o.created_at, o.id),
    )
    active_rows = [o for o in ordered if o.draft_state == "active"]
    removed_rows = [o for o in ordered if o.draft_state != "active"]
    sorted_rows = [*active_rows, *removed_rows]

    return StreamOut(
        id=stream.id,
        keitaro_id=stream.keitaro_id,
        name=stream.name,
        position=stream.position,
        schema=stream.schema,
        has_offers=stream.has_offers,
        is_dirty=compute_stream_dirty(ordered),
        total_active_share=sum(o.draft_share for o in active_rows),
        offers=[
            StreamOfferOut(
                offer_keitaro_id=o.offer_keitaro_id,
                offer_name=o.offer.name if o.offer else f"Offer #{o.offer_keitaro_id}",
                draft_state=o.draft_state,
                draft_share=o.draft_share,
                published_state=o.published_state,
                published_share=o.published_share,
                is_pinned=o.is_pinned,
            )
            for o in sorted_rows
        ],
    )


def _to_campaign_detail_out(campaign: Campaign, kt: KeitaroClient) -> CampaignDetailOut:
    ordered_streams = sorted(campaign.streams, key=lambda s: (s.position, s.id))
    return CampaignDetailOut(
        keitaro_id=campaign.keitaro_id,
        name=campaign.name,
        alias=campaign.alias,
        tracking_url=campaign.tracking_url,
        keitaro_admin_url=kt.build_admin_campaign_url(campaign.keitaro_id),
        domain_id=campaign.domain_id,
        group_id=campaign.group_id,
        traffic_source_id=campaign.traffic_source_id,
        last_fetched_at=campaign.last_fetched_at,
        streams=[_to_stream_out(stream) for stream in ordered_streams],
    )


@router.get("/health")
def healthcheck(db: Session = Depends(get_db)) -> dict[str, str]:  # noqa: B008
    """Verify service and database connectivity."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/offers", response_model=list[OfferOut])
def get_offers(
    q: str = "",
    limit: int = Query(default=20, ge=1, le=200),
    refresh: bool = False,
    db: Session = Depends(get_db),  # noqa: B008
    kt: KeitaroClient = Depends(get_keitaro_client),  # noqa: B008
) -> list[OfferOut]:
    """Search offers in local cache (syncing from Keitaro when needed)."""
    offers = search_offers(db, kt, query=q, limit=limit, refresh=refresh)
    return [OfferOut.model_validate(offer) for offer in offers]


@router.get("/campaigns", response_model=list[CampaignSummaryOut])
def get_campaigns(
    db: Session = Depends(get_db),  # noqa: B008
    kt: KeitaroClient = Depends(get_keitaro_client),  # noqa: B008
) -> list[CampaignSummaryOut]:
    """List campaigns from Keitaro with local sync indicators."""
    items = list_campaigns(db, kt)
    return [
        CampaignSummaryOut(
            keitaro_id=item["keitaro_id"],
            name=item["name"],
            alias=item["alias"],
            is_synced_locally=bool(item["is_synced"]),
        )
        for item in items
    ]


@router.post(
    "/campaigns",
    response_model=CampaignDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def post_campaign(
    body: CampaignCreateIn,
    db: Session = Depends(get_db),  # noqa: B008
    kt: KeitaroClient = Depends(get_keitaro_client),  # noqa: B008
) -> CampaignDetailOut:
    """Create a campaign with Flow 1 (GEO redirect) and Flow 2 (100% offer)."""
    campaign = create_campaign_with_flows(
        db,
        kt,
        name=body.name,
        geo=body.geo,
        offer_id=body.offer_id,
    )
    return _to_campaign_detail_out(campaign, kt)


@router.get("/campaigns/{keitaro_id}", response_model=CampaignDetailOut)
def get_campaign_detail(
    keitaro_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    kt: KeitaroClient = Depends(get_keitaro_client),  # noqa: B008
) -> CampaignDetailOut:
    """Get campaign details, auto-fetching from Keitaro on first access."""
    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.keitaro_id == keitaro_id)
        .options(
            selectinload(Campaign.streams)
            .selectinload(Stream.stream_offers)
            .selectinload(StreamOffer.offer)
        )
    )
    if campaign is None or campaign.last_fetched_at is None:
        campaign = fetch_campaign_streams(db, kt, keitaro_id)
    return _to_campaign_detail_out(campaign, kt)


@router.post("/campaigns/{keitaro_id}/fetch", response_model=CampaignDetailOut)
def fetch_campaign(
    keitaro_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    kt: KeitaroClient = Depends(get_keitaro_client),  # noqa: B008
) -> CampaignDetailOut:
    """Synchronize campaign streams and offers from Keitaro."""
    campaign = fetch_campaign_streams(db, kt, keitaro_id)
    return _to_campaign_detail_out(campaign, kt)


@router.post("/streams/{stream_id}/offers", response_model=StreamOut)
def post_stream_offer(
    stream_id: int,
    body: AddOfferIn,
    db: Session = Depends(get_db),  # noqa: B008
    kt: KeitaroClient = Depends(get_keitaro_client),  # noqa: B008
) -> StreamOut:
    """Add an offer to the stream draft and rebalance unpinned weights."""
    stream = add_offer(db, kt, stream_id, body.offer_id)
    return _to_stream_out(stream)


@router.post(
    "/streams/{stream_id}/offers/{offer_keitaro_id}/remove",
    response_model=StreamOut,
)
def post_remove_stream_offer(
    stream_id: int,
    offer_keitaro_id: int,
    db: Session = Depends(get_db),  # noqa: B008
) -> StreamOut:
    """Remove an offer from the stream draft and rebalance remaining shares."""
    stream = remove_offer(db, stream_id, offer_keitaro_id)
    return _to_stream_out(stream)


@router.post(
    "/streams/{stream_id}/offers/{offer_keitaro_id}/bring-back",
    response_model=StreamOut,
)
def post_bring_back_stream_offer(
    stream_id: int,
    offer_keitaro_id: int,
    db: Session = Depends(get_db),  # noqa: B008
) -> StreamOut:
    """Restore a removed offer in the stream draft and rebalance shares."""
    stream = bring_back_offer(db, stream_id, offer_keitaro_id)
    return _to_stream_out(stream)


@router.patch(
    "/streams/{stream_id}/offers/{offer_keitaro_id}/pin",
    response_model=StreamOut,
)
def patch_pin_stream_offer(
    stream_id: int,
    offer_keitaro_id: int,
    body: PinOfferIn,
    db: Session = Depends(get_db),  # noqa: B008
) -> StreamOut:
    """Pin or unpin an active offer without recalculating weights."""
    stream = toggle_pin(db, stream_id, offer_keitaro_id, body.is_pinned)
    return _to_stream_out(stream)


@router.post("/streams/{stream_id}/push", response_model=StreamOut)
def post_push_stream(
    stream_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    kt: KeitaroClient = Depends(get_keitaro_client),  # noqa: B008
) -> StreamOut:
    """Validate and push active stream offers to Keitaro."""
    stream = push_stream_to_kt(db, kt, stream_id)
    return _to_stream_out(stream)


@router.post("/streams/{stream_id}/cancel", response_model=StreamOut)
def post_cancel_stream(
    stream_id: int,
    db: Session = Depends(get_db),  # noqa: B008
) -> StreamOut:
    """Discard unpublished stream draft edits."""
    stream = cancel_stream_draft(db, stream_id)
    return _to_stream_out(stream)
