from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import KfcMartesLocoShare, KfcMartesLocoSnapshot


def test_martes_loco_public_endpoint_returns_public_token_not_share_token() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    now = datetime.now(timezone.utc)
    db = TestingSessionLocal()
    db.add(
        KfcMartesLocoShare(
            share_token="martes-loco-public-token",
            shared_at=now,
            created_by_oid="private-oid",
            created_by_email="private@example.com",
        )
    )
    db.add(
        KfcMartesLocoSnapshot(
            from_date=date(2026, 4, 21),
            to_date=date(2026, 4, 21),
            source_updated_at=now,
            payload_json={
                "dashboardId": "kfc-martes-loco",
                "title": "Martes Loco · KFC Ecuador",
                "brand": "KFC",
                "isMock": False,
                "source": "windsor",
                "updatedAt": "2026-08-05T12:00:00.000Z",
                "from": "2026-04-21",
                "to": "2026-04-21",
                "rows": [["2026-04-21", "A", 50653, 86.02, 145, 98, 244, 3843.83]],
                "accounts": {},
                "rules": {},
                "shareToken": "martes-loco-public-token",
                "publicToken": None,
                "sourceError": "private detail",
                "rawRows": [{"api_key": "secret"}],
            },
        )
    )
    db.commit()
    db.close()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).get(
            "/api/public/kfc-martes-loco/martes-loco-public-token",
            params={"from": "2026-04-21", "to": "2026-04-21"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["dashboardId"] == "kfc-martes-loco"
    assert payload["publicToken"] == "martes-loco-public-token"
    assert "shareToken" not in payload
    assert "sourceError" not in payload
    assert "rawRows" not in payload


def test_martes_loco_public_endpoint_404s_for_unknown_token() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).get("/api/public/kfc-martes-loco/does-not-exist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
