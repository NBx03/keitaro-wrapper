from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.db import Base


class FakeKeitaroClient:
    """In-memory stateful fake of Keitaro Admin API for service tests."""

    def __init__(self) -> None:
        self.admin_url = "https://keitaro-for-tests.etolegko.com/admin"
        self.domains: list[dict[str, Any]] = [
            {"id": 1813, "name": "kt-emulator.test", "is_ssl": True, "state": "active"}
        ]
        self.groups: list[dict[str, Any]] = [
            {"id": 10332, "name": "FORTESTS", "position": 0, "type": "campaigns"}
        ]
        self.traffic_sources: list[dict[str, Any]] = [
            {"id": 836, "name": "FORTESTS", "state": "active"}
        ]
        self.offers: dict[int, dict[str, Any]] = {
            18001: {"id": 18001, "name": "18001 Detoxin [CL]", "group_id": 7101, "state": "active"},
            18002: {"id": 18002, "name": "18002 Flexum [CL]", "group_id": 7101, "state": "active"},
            18003: {"id": 18003, "name": "18003 Cardio [BR]", "group_id": 7102, "state": "active"},
            18004: {"id": 18004, "name": "18004 Opti [MX]", "group_id": 7102, "state": "active"},
            18005: {"id": 18005, "name": "18005 Alpha [DE]", "group_id": 7103, "state": "active"},
        }
        self.campaigns: dict[int, dict[str, Any]] = {}
        self.streams: dict[int, dict[str, Any]] = {}
        self._next_campaign_id = 100
        self._next_stream_id = 500
        self.fail_on_stream_create = False
        self.updated_stream_payloads: list[tuple[int, dict[str, Any]]] = []

    def build_admin_campaign_url(self, keitaro_id: int) -> str:
        return f"{self.admin_url}/#!/campaign.editor/{keitaro_id}"

    def list_domains(self) -> list[dict[str, Any]]:
        return list(self.domains)

    def list_groups(self, group_type: str = "campaigns") -> list[dict[str, Any]]:
        return [g for g in self.groups if g.get("type") == group_type]

    def list_traffic_sources(self) -> list[dict[str, Any]]:
        return list(self.traffic_sources)

    def list_offers(self) -> list[dict[str, Any]]:
        return list(self.offers.values())

    def get_offer(self, offer_id: int) -> dict[str, Any]:
        if offer_id not in self.offers:
            from app.keitaro.client import KeitaroNotFoundError

            raise KeitaroNotFoundError(f"Offer {offer_id} not found", status_code=404)
        return dict(self.offers[offer_id])

    def list_campaigns(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        items = list(reversed(list(self.campaigns.values())))
        return items[offset : offset + limit]

    def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        if campaign_id not in self.campaigns:
            from app.keitaro.client import KeitaroNotFoundError

            raise KeitaroNotFoundError(f"Campaign {campaign_id} not found", status_code=404)
        return dict(self.campaigns[campaign_id])

    def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._next_campaign_id += 1
        cid = self._next_campaign_id
        campaign = {
            "id": cid,
            "name": payload["name"],
            "alias": payload.get("alias") or f"cmp-{cid}",
            "type": payload.get("type", "position"),
            "state": payload.get("state", "active"),
            "domain_id": payload.get("domain_id"),
            "group_id": payload.get("group_id"),
            "traffic_source_id": payload.get("traffic_source_id"),
        }
        self.campaigns[cid] = campaign
        return dict(campaign)

    def list_streams(self, campaign_id: int) -> list[dict[str, Any]]:
        streams = [s for s in self.streams.values() if s["campaign_id"] == campaign_id]
        return sorted(streams, key=lambda s: s.get("position", 0))

    def create_stream(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.fail_on_stream_create:
            from app.keitaro.client import KeitaroBadRequestError

            raise KeitaroBadRequestError("Simulated stream error", status_code=422)
        self._next_stream_id += 1
        sid = self._next_stream_id
        stream = {"id": sid, **payload}
        self.streams[sid] = stream
        return dict(stream)

    def update_stream(self, stream_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if stream_id not in self.streams:
            from app.keitaro.client import KeitaroNotFoundError

            raise KeitaroNotFoundError(f"Stream {stream_id} not found", status_code=404)
        self.updated_stream_payloads.append((stream_id, dict(payload)))
        updated = {**self.streams[stream_id], **payload, "id": stream_id}
        self.streams[stream_id] = updated
        return dict(updated)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn: Any, _rec: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def fake_kt() -> FakeKeitaroClient:
    return FakeKeitaroClient()
