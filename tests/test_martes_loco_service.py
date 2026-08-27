from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import KfcMartesLocoSnapshot
from app.martes_loco_service import get_martes_loco_dashboard, refresh_martes_loco_dashboard
from app.windsor import WindsorError


class FakeSettings:
    app_timezone = "America/Guayaquil"
    cache_ttl_seconds = 900
    windsor_api_key = "fake-key"
    windsor_base_url = "https://connectors.windsor.ai"
    http_timeout_seconds = 60
    http_retries = 3


class FakeWindsorClient:
    base_url = "https://connectors.windsor.ai"

    def __init__(self, settings):
        self.settings = settings

    def fetch_connector(self, connector, fields, date_from, date_to):
        if connector == "facebook":
            return [
                {
                    "date": "2026-04-21",
                    "account_id": "7266308733410766",
                    "campaign": "ECU_2026_ABRIL_KFC_META_DOMICILIO APP_MARTES V3_ADQUISICION",
                    "reach": "50653",
                    "spend": "86.02",
                    "conversions_subscribe_mobile_app": "145",
                    "conversions_start_trial_mobile_app": "98",
                    "actions_omni_purchase": "244",
                    "action_values_omni_purchase": "3843.83",
                }
            ]
        raise WindsorError(f"unexpected connector {connector}")


class FailingWindsorClient:
    base_url = "https://connectors.windsor.ai"

    def __init__(self, settings):
        self.settings = settings

    def fetch_connector(self, connector, fields, date_from, date_to):
        raise WindsorError('HTTP 400 body={"error":"bad field"}')


def _make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_refresh_martes_loco_dashboard_saves_snapshot(monkeypatch) -> None:
    db = _make_db()
    monkeypatch.setattr("app.martes_loco_service.WindsorClient", FakeWindsorClient)

    payload = refresh_martes_loco_dashboard(
        db,
        FakeSettings(),
        from_date=date(2026, 4, 21),
        to_date=date(2026, 4, 21),
    )

    snapshot = db.query(KfcMartesLocoSnapshot).one()
    assert snapshot.payload_json["dashboardId"] == "kfc-martes-loco"
    assert payload["dashboardId"] == "kfc-martes-loco"
    assert payload["rows"] == [["2026-04-21", "A", 50653, 86.02, 145, 98, 244, 3843.83]]
    assert "sourceError" not in payload


def test_get_martes_loco_dashboard_falls_back_to_stale_snapshot_on_windsor_error(
    monkeypatch,
) -> None:
    db = _make_db()
    db.add(
        KfcMartesLocoSnapshot(
            from_date=date(2026, 4, 21),
            to_date=date(2026, 4, 21),
            source_updated_at=datetime.now(timezone.utc),
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
                "shareToken": None,
                "publicToken": None,
            },
        )
    )
    db.commit()
    monkeypatch.setattr("app.martes_loco_service.WindsorClient", FailingWindsorClient)

    payload = get_martes_loco_dashboard(
        db,
        FakeSettings(),
        from_date=date(2026, 4, 21),
        to_date=date(2026, 4, 21),
        force_refresh=True,
    )

    assert payload["isStale"] is True
    assert payload["source"] == "snapshot"
    assert payload["sourceError"] == "windsor_unavailable"
    assert payload["rows"] == [["2026-04-21", "A", 50653, 86.02, 145, 98, 244, 3843.83]]
