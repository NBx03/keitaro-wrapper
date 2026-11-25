import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.keitaro.client import KeitaroClient, KeitaroError, KeitaroNotFoundError
from app.keitaro.mapper import (
    build_create_campaign_payload,
    build_flow1_redirect_payload,
    build_flow2_offers_payload,
    build_tracking_url,
)
from app.models import Campaign, Offer, Stream, StreamOffer
from app.services.exceptions import ExternalServiceError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _resolve_default_id(
    configured_id: int | None,
    items: list[dict[str, Any]],
    preferred_name: str = "FORTESTS",
) -> int | None:
    if configured_id is not None:
        return configured_id

    for item in items:
        if item.get("name") == preferred_name:
            return int(item["id"])

    for item in items:
        if item.get("state") == "active" or item.get("status") == "active":
            return int(item["id"])

    if items:
        return int(items[0]["id"])
    return None


def _upsert_offers(db: Session, remote_offers: list[dict[str, Any]]) -> None:
    now = _utcnow()
    existing_by_id = {offer.keitaro_id: offer for offer in db.scalars(select(Offer)).all()}
    for item in remote_offers:
        keitaro_id = int(item["id"])
        name = str(item.get("name") or f"Offer #{keitaro_id}")
        group_id = item.get("group_id")
        existing = existing_by_id.get(keitaro_id)
        if existing is not None:
            existing.name = name
            existing.group_id = group_id
            existing.updated_at = now
        else:
            db.add(
                Offer(
                    keitaro_id=keitaro_id,
                    name=name,
                    group_id=group_id,
                    updated_at=now,
                )
            )


def sync_offers_if_needed(db: Session, kt: KeitaroClient, force: bool = False) -> None:
    """Refresh local Offer cache from Keitaro when forced, empty, or TTL-expired."""
    if not force:
        latest_updated = _as_utc(db.scalar(select(func.max(Offer.updated_at))))
        ttl = timedelta(seconds=settings.OFFERS_CACHE_TTL_SECONDS)
        if latest_updated is not None and (_utcnow() - latest_updated) < ttl:
            return

    try:
        remote_offers = kt.list_offers()
    except KeitaroError as exc:
        raise ExternalServiceError(f"Failed to fetch offers from Keitaro: {exc}") from exc

    _upsert_offers(db, remote_offers)
    db.commit()


def ensure_offers_exist(db: Session, kt: KeitaroClient, offer_ids: set[int]) -> None:
    """Ensure every offer ID exists in the local offers table."""
    if not offer_ids:
        return

    existing_ids = set(
        db.scalars(select(Offer.keitaro_id).where(Offer.keitaro_id.in_(offer_ids))).all()
    )
    missing_ids = offer_ids - existing_ids
    if not missing_ids:
        return

    sync_offers_if_needed(db, kt, force=True)
    existing_ids = set(
        db.scalars(select(Offer.keitaro_id).where(Offer.keitaro_id.in_(offer_ids))).all()
    )
    still_missing = offer_ids - existing_ids
    if not still_missing:
        return

    now = _utcnow()
    for oid in sorted(still_missing):
        try:
            remote_offer = kt.get_offer(oid)
            db.add(
                Offer(
                    keitaro_id=int(remote_offer["id"]),
                    name=str(remote_offer.get("name") or f"Offer #{oid}"),
                    group_id=remote_offer.get("group_id"),
                    updated_at=now,
                )
            )
        except KeitaroNotFoundError:
            db.add(Offer(keitaro_id=oid, name=f"Offer #{oid}", group_id=None, updated_at=now))
        except KeitaroError as exc:
            raise ExternalServiceError(f"Failed to fetch offer {oid} from Keitaro: {exc}") from exc
    db.commit()


def search_offers(
    db: Session,
    kt: KeitaroClient,
    query: str = "",
    limit: int = 20,
    refresh: bool = False,
) -> list[Offer]:
    """Case-insensitive offer search by ID or name substring."""
    sync_offers_if_needed(db, kt, force=refresh)
    stmt = select(Offer)
    clean_query = query.strip()
    if clean_query:
        pattern = f"%{clean_query}%"
        stmt = stmt.where(
            or_(
                Offer.name.ilike(pattern),
                cast(Offer.keitaro_id, String).ilike(pattern),
            )
        )
    stmt = stmt.order_by(Offer.keitaro_id.asc()).limit(limit)
    return list(db.scalars(stmt).all())


def list_campaigns(db: Session, kt: KeitaroClient) -> list[dict[str, Any]]:
    """List campaigns from Keitaro annotated with local synchronization status."""
    try:
        remote_campaigns = kt.list_campaigns(limit=100, offset=0)
    except KeitaroError as exc:
        raise ExternalServiceError(f"Failed to fetch campaigns from Keitaro: {exc}") from exc

    local_campaigns = {c.keitaro_id: c for c in db.scalars(select(Campaign)).all()}
    result: list[dict[str, Any]] = []
    for item in remote_campaigns:
        kt_id = int(item["id"])
        local = local_campaigns.get(kt_id)
        result.append(
            {
                "keitaro_id": kt_id,
                "local_id": local.id if local else None,
                "name": str(item.get("name") or f"Campaign #{kt_id}"),
                "alias": item.get("alias"),
                "domain_id": item.get("domain_id"),
                "group_id": item.get("group_id"),
                "traffic_source_id": item.get("traffic_source_id"),
                "state": item.get("state", "active"),
                "tracking_url": local.tracking_url if local else item.get("tracking_url"),
                "is_synced": local is not None and local.last_fetched_at is not None,
                "last_fetched_at": local.last_fetched_at if local else None,
                "admin_url": kt.build_admin_campaign_url(kt_id),
            }
        )
    return result


def create_campaign_with_flows(
    db: Session,
    kt: KeitaroClient,
    *,
    name: str,
    geo: str,
    offer_id: int,
) -> Campaign:
    """Create a Keitaro campaign with Flow 1 (geo->Google) and Flow 2 (offer 100%)."""
    clean_name = name.strip()
    if not clean_name:
        raise ValidationError("Campaign name must not be empty")

    clean_geo = geo.strip().upper()
    if len(clean_geo) != 2 or not clean_geo.isascii() or not clean_geo.isalpha():
        raise ValidationError("GEO must be a 2-letter ISO country code (e.g. CL, US, DE)")

    sync_offers_if_needed(db, kt)
    offer = db.get(Offer, offer_id)
    if offer is None:
        try:
            remote_offer = kt.get_offer(offer_id)
        except KeitaroNotFoundError as exc:
            raise ValidationError(f"Offer {offer_id} does not exist in Keitaro") from exc
        except KeitaroError as exc:
            raise ExternalServiceError(f"Failed to verify offer {offer_id}: {exc}") from exc
        _upsert_offers(db, [remote_offer])
        db.commit()

    try:
        domains = kt.list_domains()
        groups = kt.list_groups("campaigns")
        sources = kt.list_traffic_sources()
    except KeitaroError as exc:
        raise ExternalServiceError(f"Failed to load Keitaro catalog defaults: {exc}") from exc

    domain_id = _resolve_default_id(settings.KEITARO_DEFAULT_DOMAIN_ID, domains)
    group_id = _resolve_default_id(settings.KEITARO_DEFAULT_GROUP_ID, groups)
    source_id = _resolve_default_id(settings.KEITARO_DEFAULT_SOURCE_ID, sources)

    campaign_payload = build_create_campaign_payload(
        name=clean_name,
        domain_id=domain_id,
        group_id=group_id,
        traffic_source_id=source_id,
    )
    try:
        created_campaign = kt.create_campaign(campaign_payload)
    except KeitaroError as exc:
        raise ExternalServiceError(f"Failed to create campaign in Keitaro: {exc}") from exc

    kt_campaign_id = int(created_campaign["id"])
    logger.info(
        "Created Keitaro campaign #%s (name=%r, geo=%s, offer_id=%s)",
        kt_campaign_id,
        clean_name,
        clean_geo,
        offer_id,
    )

    try:
        kt.create_stream(build_flow1_redirect_payload(kt_campaign_id, clean_geo))
        kt.create_stream(build_flow2_offers_payload(kt_campaign_id, offer_id))
    except KeitaroError as exc:
        logger.exception(
            "Campaign %s was created in Keitaro, but creating default streams failed",
            kt_campaign_id,
        )
        raise ExternalServiceError(
            f"Campaign #{kt_campaign_id} created in Keitaro, but stream creation failed: {exc}"
        ) from exc

    domains_by_id = {int(d["id"]): d for d in domains}
    return fetch_campaign_streams(
        db,
        kt,
        kt_campaign_id,
        domains_by_id=domains_by_id,
    )


def fetch_campaign_streams(
    db: Session,
    kt: KeitaroClient,
    campaign_keitaro_id: int,
    *,
    domains_by_id: dict[int, dict[str, Any]] | None = None,
) -> Campaign:
    """Sync campaign metadata, streams, and offers from Keitaro into local DB."""
    try:
        remote_campaign = kt.get_campaign(campaign_keitaro_id)
        remote_streams = kt.list_streams(campaign_keitaro_id)
    except KeitaroNotFoundError as exc:
        raise NotFoundError(f"Campaign #{campaign_keitaro_id} not found in Keitaro") from exc
    except KeitaroError as exc:
        raise ExternalServiceError(
            f"Failed to fetch campaign #{campaign_keitaro_id} from Keitaro: {exc}"
        ) from exc

    if domains_by_id is None and remote_campaign.get("domain_id") is not None:
        try:
            domains_by_id = {int(d["id"]): d for d in kt.list_domains()}
        except KeitaroError:
            domains_by_id = None

    offer_ids: set[int] = set()
    for stream_data in remote_streams:
        if stream_data.get("schema") == "landings":
            for offer_item in stream_data.get("offers") or []:
                if offer_item.get("offer_id") is not None:
                    offer_ids.add(int(offer_item["offer_id"]))
    ensure_offers_exist(db, kt, offer_ids)

    now = _utcnow()
    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.keitaro_id == campaign_keitaro_id)
        .options(selectinload(Campaign.streams).selectinload(Stream.stream_offers))
    )
    tracking_url = build_tracking_url(remote_campaign, domains_by_id)
    if campaign is None:
        campaign = Campaign(
            keitaro_id=campaign_keitaro_id,
            name=str(remote_campaign.get("name") or f"Campaign #{campaign_keitaro_id}"),
            alias=remote_campaign.get("alias"),
            tracking_url=tracking_url,
            domain_id=remote_campaign.get("domain_id"),
            group_id=remote_campaign.get("group_id"),
            traffic_source_id=remote_campaign.get("traffic_source_id"),
            last_fetched_at=now,
        )
        db.add(campaign)
        db.flush()
    else:
        campaign.name = str(remote_campaign.get("name") or campaign.name)
        campaign.alias = remote_campaign.get("alias")
        if tracking_url is not None:
            campaign.tracking_url = tracking_url
        campaign.domain_id = remote_campaign.get("domain_id")
        campaign.group_id = remote_campaign.get("group_id")
        campaign.traffic_source_id = remote_campaign.get("traffic_source_id")
        campaign.last_fetched_at = now

    existing_streams_by_kt = {s.keitaro_id: s for s in campaign.streams}
    remote_stream_ids = {int(s["id"]) for s in remote_streams}

    for kt_sid, local_stream in list(existing_streams_by_kt.items()):
        if kt_sid not in remote_stream_ids:
            db.delete(local_stream)

    for idx, stream_data in enumerate(remote_streams):
        kt_stream_id = int(stream_data["id"])
        schema = str(stream_data.get("schema") or "")
        has_offers = schema == "landings"
        raw_pos = stream_data.get("position")
        position = int(raw_pos) if raw_pos is not None else (idx + 1)

        stream = existing_streams_by_kt.get(kt_stream_id)
        if stream is None:
            stream = Stream(
                campaign_id=campaign.id,
                keitaro_id=kt_stream_id,
                name=str(stream_data.get("name") or f"Stream #{kt_stream_id}"),
                position=position,
                schema=schema,
                has_offers=has_offers,
                raw_payload=stream_data,
            )
            db.add(stream)
            db.flush()
        else:
            stream.name = str(stream_data.get("name") or stream.name)
            stream.position = position
            stream.schema = schema
            stream.has_offers = has_offers
            stream.raw_payload = stream_data

        _sync_stream_offers(db, stream, stream_data if has_offers else None)

    db.commit()
    logger.info(
        "Synced campaign #%s from Keitaro (%s streams)",
        campaign_keitaro_id,
        len(remote_streams),
    )
    return db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign.id)
        .options(
            selectinload(Campaign.streams)
            .selectinload(Stream.stream_offers)
            .selectinload(StreamOffer.offer)
        )
    )  # type: ignore[return-value]


def _sync_stream_offers(
    db: Session,
    stream: Stream,
    remote_stream_data: dict[str, Any] | None,
) -> None:
    existing_rows = list(
        db.scalars(select(StreamOffer).where(StreamOffer.stream_id == stream.id)).all()
    )
    if remote_stream_data is None:
        for row in existing_rows:
            db.delete(row)
        return

    existing_by_offer = {row.offer_keitaro_id: row for row in existing_rows}
    remote_offers_by_id: dict[int, int] = {}
    for offer_item in remote_stream_data.get("offers") or []:
        if offer_item.get("offer_id") is None:
            continue
        if offer_item.get("state", "active") != "active":
            continue
        oid = int(offer_item["offer_id"])
        remote_offers_by_id[oid] = int(offer_item.get("share", 0))

    for oid, remote_share in remote_offers_by_id.items():
        row = existing_by_offer.get(oid)
        if row is not None:
            if row.published_state != "active" or row.published_share != remote_share:
                row.is_pinned = False
            row.published_state = "active"
            row.draft_state = "active"
            row.published_share = remote_share
            row.draft_share = remote_share
        else:
            db.add(
                StreamOffer(
                    stream_id=stream.id,
                    offer_keitaro_id=oid,
                    published_state="active",
                    published_share=remote_share,
                    draft_state="active",
                    draft_share=remote_share,
                    is_pinned=False,
                )
            )

    for oid, row in existing_by_offer.items():
        if oid in remote_offers_by_id:
            continue
        if row.published_state == "none":
            db.delete(row)
        else:
            row.published_state = "removed"
            row.draft_state = "removed"
            row.published_share = 0
            row.draft_share = 0
            row.is_pinned = False
