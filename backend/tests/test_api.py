from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.routes import get_keitaro_client
from app.db import Base, get_db
from app.keitaro.client import KeitaroError
from app.main import app
from tests.conftest import FakeKeitaroClient


@pytest.fixture()
def api_client(fake_kt: FakeKeitaroClient) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn: Any, _rec: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_db() -> Generator[Session, None, None]:
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    def _override_kt() -> Generator[FakeKeitaroClient, None, None]:
        yield fake_kt

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_keitaro_client] = _override_kt
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_health_and_offers_endpoints(api_client: TestClient) -> None:
    health = api_client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    offers = api_client.get("/api/offers", params={"q": "detoxin"})
    assert offers.status_code == 200
    assert offers.json() == [{"keitaro_id": 18001, "name": "18001 Detoxin [CL]"}]


def test_campaign_crud_auto_fetch_and_404(
    api_client: TestClient,
    fake_kt: FakeKeitaroClient,
) -> None:
    assert api_client.get("/api/campaigns").json() == []
    assert api_client.get("/api/campaigns/9999").status_code == 404

    bad = api_client.post(
        "/api/campaigns",
        json={"name": "Bad", "geo": "USA", "offer_id": 18001},
    )
    assert bad.status_code == 422

    created = api_client.post(
        "/api/campaigns",
        json={"name": "API Campaign", "geo": "au", "offer_id": 18001},
    )
    assert created.status_code == 201
    detail = created.json()
    kt_id = detail["keitaro_id"]
    assert detail["tracking_url"] == f"https://kt-emulator.test/cmp-{kt_id}"
    assert detail["keitaro_admin_url"] == (
        f"https://keitaro-for-tests.etolegko.com/admin/#!/campaign.editor/{kt_id}"
    )
    assert len(detail["streams"]) == 2
    assert detail["streams"][0]["has_offers"] is False
    assert detail["streams"][1]["has_offers"] is True

    # Remote-only campaign auto-fetches on GET /api/campaigns/{id}
    remote_only = fake_kt.create_campaign({"name": "Remote Only"})
    fake_kt.create_stream(
        {
            "campaign_id": remote_only["id"],
            "name": "Offers",
            "type": "default",
            "position": 1,
            "schema": "landings",
            "offers": [{"offer_id": 18002, "share": 100, "state": "active"}],
        }
    )
    fetched = api_client.get(f"/api/campaigns/{remote_only['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["streams"][0]["offers"][0]["offer_keitaro_id"] == 18002

    listing = api_client.get("/api/campaigns").json()
    assert len(listing) == 2
    assert all(item["is_synced_locally"] is True for item in listing)


def test_stream_editor_http_workflow_and_error_codes(
    api_client: TestClient,
    fake_kt: FakeKeitaroClient,
) -> None:
    created = api_client.post(
        "/api/campaigns",
        json={"name": "Editor Test", "geo": "CL", "offer_id": 18001},
    ).json()
    stream_id = created["streams"][1]["id"]

    # Add 2nd and 3rd offers -> 34/33/33
    assert (
        api_client.post(f"/api/streams/{stream_id}/offers", json={"offer_id": 18002}).status_code
        == 200
    )
    res_add3 = api_client.post(f"/api/streams/{stream_id}/offers", json={"offer_id": 18003})
    assert res_add3.status_code == 200
    data = res_add3.json()
    assert data["is_dirty"] is True
    assert data["total_active_share"] == 100
    assert [o["draft_share"] for o in data["offers"]] == [34, 33, 33]

    # Duplicate active offer -> 409
    dup = api_client.post(f"/api/streams/{stream_id}/offers", json={"offer_id": 18003})
    assert dup.status_code == 409

    # Pin -> does not alter dirty state; push -> clean
    pinned = api_client.patch(
        f"/api/streams/{stream_id}/offers/18001/pin",
        json={"is_pinned": True},
    )
    assert pinned.status_code == 200
    assert pinned.json()["is_dirty"] is True

    pushed = api_client.post(f"/api/streams/{stream_id}/push")
    assert pushed.status_code == 200
    assert pushed.json()["is_dirty"] is False

    # Remove 18003 -> push -> 18003 appears at bottom with removed state and 0%
    api_client.post(f"/api/streams/{stream_id}/offers/18003/remove")
    pushed2 = api_client.post(f"/api/streams/{stream_id}/push")
    assert pushed2.status_code == 200
    offers = pushed2.json()["offers"]
    assert [o["offer_keitaro_id"] for o in offers] == [18001, 18002, 18003]
    assert offers[-1]["draft_state"] == "removed"
    assert offers[-1]["published_state"] == "removed"
    assert offers[-1]["draft_share"] == 0

    # Bring back then cancel -> returns cleanly to 18003=removed
    brought = api_client.post(f"/api/streams/{stream_id}/offers/18003/bring-back")
    assert brought.status_code == 200
    assert brought.json()["is_dirty"] is True
    canceled = api_client.post(f"/api/streams/{stream_id}/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["is_dirty"] is False
    assert canceled.json()["offers"][-1]["draft_state"] == "removed"

    # Re-adding removed offer via POST /offers restores it cleanly without 409
    readded = api_client.post(f"/api/streams/{stream_id}/offers", json={"offer_id": 18003})
    assert readded.status_code == 200
    assert readded.json()["is_dirty"] is True
    assert readded.json()["offers"][-1]["draft_state"] == "active"
    assert api_client.post(f"/api/streams/{stream_id}/cancel").status_code == 200

    # Upstream KeitaroError maps to 502
    def _boom(_sid: int, _payload: dict[str, Any]) -> dict[str, Any]:
        raise KeitaroError("Upstream down", status_code=503)

    api_client.post(f"/api/streams/{stream_id}/offers/18003/bring-back")
    fake_kt.update_stream = _boom  # type: ignore[method-assign]
    failed_push = api_client.post(f"/api/streams/{stream_id}/push")
    assert failed_push.status_code == 502
