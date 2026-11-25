from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.keitaro.client import KeitaroClient, KeitaroError
from app.keitaro.mapper import build_update_stream_offers_payload
from app.models import Offer, Stream, StreamOffer
from app.services.campaigns import ensure_offers_exist
from app.services.exceptions import (
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from app.services.weights import recalculate_shares


def _get_stream_or_404(db: Session, stream_id: int) -> Stream:
    stream = db.scalar(
        select(Stream)
        .where(Stream.id == stream_id)
        .options(selectinload(Stream.stream_offers).selectinload(StreamOffer.offer))
    )
    if stream is None:
        raise NotFoundError(f"Stream #{stream_id} not found")
    return stream


def _ordered_stream_offers(db: Session, stream_id: int) -> list[StreamOffer]:
    return list(
        db.scalars(
            select(StreamOffer)
            .where(StreamOffer.stream_id == stream_id)
            .order_by(StreamOffer.created_at.asc(), StreamOffer.id.asc())
            .options(selectinload(StreamOffer.offer))
        ).all()
    )


def add_offer(db: Session, kt: KeitaroClient, stream_id: int, offer_id: int) -> Stream:
    """Add a new offer or restore a removed one in the stream draft and recalculate shares."""
    stream = _get_stream_or_404(db, stream_id)
    if not stream.has_offers:
        raise ValidationError(f"Stream '{stream.name}' does not support offers")

    ensure_offers_exist(db, kt, {offer_id})
    offer = db.get(Offer, offer_id)
    if offer is None:
        raise NotFoundError(f"Offer #{offer_id} not found")

    existing = db.scalar(
        select(StreamOffer).where(
            StreamOffer.stream_id == stream_id,
            StreamOffer.offer_keitaro_id == offer_id,
        )
    )
    if existing is not None:
        if existing.draft_state == "active":
            raise ConflictError(f"Offer #{offer_id} is already active in stream #{stream_id}")
        existing.draft_state = "active"
        existing.is_pinned = False
    else:
        db.add(
            StreamOffer(
                stream_id=stream_id,
                offer_keitaro_id=offer_id,
                published_state="none",
                published_share=0,
                draft_state="active",
                draft_share=0,
                is_pinned=False,
            )
        )
    db.flush()

    rows = _ordered_stream_offers(db, stream_id)
    recalculate_shares(rows)
    db.commit()
    return _get_stream_or_404(db, stream_id)


def remove_offer(db: Session, stream_id: int, offer_keitaro_id: int) -> Stream:
    """Remove an offer from the stream draft (deleting unpublished rows) and rebalance."""
    _get_stream_or_404(db, stream_id)
    row = db.scalar(
        select(StreamOffer).where(
            StreamOffer.stream_id == stream_id,
            StreamOffer.offer_keitaro_id == offer_keitaro_id,
        )
    )
    if row is None:
        raise NotFoundError(f"Offer #{offer_keitaro_id} not found in stream #{stream_id}")

    if row.published_state == "none":
        db.delete(row)
    else:
        row.draft_state = "removed"
        row.draft_share = 0
        row.is_pinned = False
    db.flush()

    rows = _ordered_stream_offers(db, stream_id)
    recalculate_shares(rows)
    db.commit()
    return _get_stream_or_404(db, stream_id)


def bring_back_offer(db: Session, stream_id: int, offer_keitaro_id: int) -> Stream:
    """Restore a removed offer back to active in the stream draft and recalculate shares."""
    _get_stream_or_404(db, stream_id)
    row = db.scalar(
        select(StreamOffer).where(
            StreamOffer.stream_id == stream_id,
            StreamOffer.offer_keitaro_id == offer_keitaro_id,
        )
    )
    if row is None:
        raise NotFoundError(f"Offer #{offer_keitaro_id} not found in stream #{stream_id}")
    if row.draft_state != "removed":
        raise ConflictError(f"Offer #{offer_keitaro_id} is not in removed state")

    row.draft_state = "active"
    row.is_pinned = False
    db.flush()

    rows = _ordered_stream_offers(db, stream_id)
    recalculate_shares(rows)
    db.commit()
    return _get_stream_or_404(db, stream_id)


def toggle_pin(
    db: Session,
    stream_id: int,
    offer_keitaro_id: int,
    is_pinned: bool,
) -> Stream:
    """Toggle pin state for an active offer without modifying shares or dirty state."""
    _get_stream_or_404(db, stream_id)
    row = db.scalar(
        select(StreamOffer).where(
            StreamOffer.stream_id == stream_id,
            StreamOffer.offer_keitaro_id == offer_keitaro_id,
        )
    )
    if row is None:
        raise NotFoundError(f"Offer #{offer_keitaro_id} not found in stream #{stream_id}")
    if row.draft_state != "active":
        raise ValidationError("Only active offers can be pinned")

    row.is_pinned = is_pinned
    db.commit()
    return _get_stream_or_404(db, stream_id)


def cancel_stream_draft(db: Session, stream_id: int) -> Stream:
    """Discard unpublished draft edits and revert stream offers to published state."""
    _get_stream_or_404(db, stream_id)
    rows = _ordered_stream_offers(db, stream_id)
    for row in rows:
        if row.published_state == "none":
            db.delete(row)
        else:
            row.draft_state = row.published_state
            row.draft_share = row.published_share
            if row.published_state == "removed":
                row.is_pinned = False
    db.commit()
    return _get_stream_or_404(db, stream_id)


def push_stream_to_kt(db: Session, kt: KeitaroClient, stream_id: int) -> Stream:
    """Validate draft weights, push active offers to Keitaro, and commit published state."""
    stream = _get_stream_or_404(db, stream_id)
    if not stream.has_offers:
        raise ValidationError(f"Stream '{stream.name}' does not support offers")

    rows = _ordered_stream_offers(db, stream_id)
    active_rows = [row for row in rows if row.draft_state == "active"]
    if not active_rows:
        raise ValidationError("At least one active offer is required before pushing to Keitaro")

    total_share = sum(row.draft_share for row in active_rows)
    if total_share != 100:
        raise ValidationError(
            f"Active offer shares must sum to 100% before pushing (got {total_share}%)"
        )
    if any(row.draft_share <= 0 or row.draft_share > 100 for row in active_rows):
        raise ValidationError("Every active offer share must be between 1% and 100%")

    payload = build_update_stream_offers_payload(stream.raw_payload, active_rows)
    try:
        updated_remote = kt.update_stream(stream.keitaro_id, payload)
    except KeitaroError as exc:
        raise ExternalServiceError(f"Failed to push stream to Keitaro: {exc}") from exc

    stream.raw_payload = updated_remote
    for row in rows:
        row.published_state = row.draft_state
        row.published_share = row.draft_share
    db.commit()
    return _get_stream_or_404(db, stream_id)
