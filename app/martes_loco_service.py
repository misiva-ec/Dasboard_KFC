from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import KfcMartesLocoShare, KfcMartesLocoSnapshot, utcnow
from app.martes_loco import (
    MARTES_LOCO_META_FIELDS,
    MARTES_LOCO_START_DATE,
    MartesLocoRawRows,
    build_martes_loco_payload,
    sanitize_public_martes_loco_payload,
)
from app.security import AuthUser
from app.windsor import WindsorClient, WindsorError


logger = logging.getLogger(__name__)


class MartesLocoDashboardUnavailable(RuntimeError):
    pass


def today_in_martes_loco_timezone(settings: Settings) -> date:
    return datetime.now(ZoneInfo(settings.app_timezone)).date()


def normalize_martes_loco_range(
    from_date: Optional[date],
    to_date: Optional[date],
    settings: Settings,
) -> tuple[date, date]:
    start = from_date or MARTES_LOCO_START_DATE
    end = to_date or today_in_martes_loco_timezone(settings)
    if start < MARTES_LOCO_START_DATE:
        start = MARTES_LOCO_START_DATE
    if end < start:
        raise ValueError("to must be greater than or equal to from")
    return start, end


def get_martes_loco_dashboard(
    db: Session,
    settings: Settings,
    *,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    force_refresh: bool = False,
    public_token: Optional[str] = None,
) -> dict:
    start, end = normalize_martes_loco_range(from_date, to_date, settings)
    snapshot = latest_martes_loco_snapshot(db, start, end)

    if snapshot and not force_refresh and _is_fresh(snapshot, settings):
        payload = dict(snapshot.payload_json)
        return _prepare_martes_loco_payload(db, payload, public_token=public_token)

    try:
        payload = refresh_martes_loco_dashboard(db, settings, from_date=start, to_date=end)
        return _prepare_martes_loco_payload(db, payload, public_token=public_token)
    except WindsorError as exc:
        if snapshot:
            payload = dict(snapshot.payload_json)
            payload["isStale"] = True
            payload["stale"] = True
            payload["source"] = "snapshot"
            payload["sourceError"] = "windsor_unavailable"
            return _prepare_martes_loco_payload(db, payload, public_token=public_token)
        raise MartesLocoDashboardUnavailable(
            "No cached martes-loco dashboard is available"
        ) from exc


def refresh_martes_loco_dashboard(
    db: Session,
    settings: Settings,
    *,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> dict:
    start, end = normalize_martes_loco_range(from_date, to_date, settings)
    client = WindsorClient(settings)

    raw_meta = _fetch_connector_or_raise(
        client,
        "facebook",
        MARTES_LOCO_META_FIELDS,
        start,
        end,
    )

    source_updated_at = utcnow()
    share = get_active_martes_loco_share(db)
    payload = build_martes_loco_payload(
        rows=MartesLocoRawRows(meta=raw_meta),
        from_date=start,
        to_date=end,
        updated_at=source_updated_at,
        share_token=share.share_token if share else None,
    )
    db.add(
        KfcMartesLocoSnapshot(
            from_date=start,
            to_date=end,
            payload_json=payload,
            source_updated_at=source_updated_at,
        )
    )
    db.commit()
    return payload


def latest_martes_loco_snapshot(
    db: Session,
    from_date: date,
    to_date: date,
) -> Optional[KfcMartesLocoSnapshot]:
    return (
        db.query(KfcMartesLocoSnapshot)
        .filter(
            KfcMartesLocoSnapshot.from_date == from_date,
            KfcMartesLocoSnapshot.to_date == to_date,
        )
        .order_by(KfcMartesLocoSnapshot.created_at.desc())
        .first()
    )


def get_active_martes_loco_share(db: Session) -> Optional[KfcMartesLocoShare]:
    return (
        db.query(KfcMartesLocoShare)
        .filter(KfcMartesLocoShare.revoked_at.is_(None))
        .order_by(KfcMartesLocoShare.shared_at.desc())
        .first()
    )


def create_martes_loco_share_token(db: Session, user: AuthUser) -> KfcMartesLocoShare:
    existing = get_active_martes_loco_share(db)
    if existing:
        return existing

    share = KfcMartesLocoShare(
        share_token=secrets.token_urlsafe(32),
        shared_at=utcnow(),
        created_by_oid=user.oid,
        created_by_email=user.email,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return share


def revoke_martes_loco_share_token(db: Session) -> None:
    active = db.query(KfcMartesLocoShare).filter(KfcMartesLocoShare.revoked_at.is_(None)).all()
    now = utcnow()
    for share in active:
        share.revoked_at = now
    db.commit()


def get_martes_loco_share_by_token(db: Session, token: str) -> Optional[KfcMartesLocoShare]:
    return (
        db.query(KfcMartesLocoShare)
        .filter(
            KfcMartesLocoShare.share_token == token,
            KfcMartesLocoShare.revoked_at.is_(None),
        )
        .one_or_none()
    )


def _fetch_connector_or_raise(
    client: WindsorClient,
    connector: str,
    fields: list[str],
    start: date,
    end: date,
) -> list[dict]:
    url = f"{client.base_url}/{connector}"
    logger.info(
        "Fetching Windsor connector=%s url=%s fields=%s date_from=%s date_to=%s",
        connector,
        url,
        ",".join(fields),
        start.isoformat(),
        end.isoformat(),
    )
    try:
        rows = client.fetch_connector(connector, fields, start, end)
    except WindsorError as exc:
        logger.error(
            "Windsor connector=%s failed url=%s fields=%s date_from=%s date_to=%s error=%s",
            connector,
            url,
            ",".join(fields),
            start.isoformat(),
            end.isoformat(),
            exc,
        )
        raise WindsorError(f"{connector} failed: {exc}") from exc

    logger.info(
        "Windsor connector=%s ok rows=%s url=%s fields=%s date_from=%s date_to=%s",
        connector,
        len(rows),
        url,
        ",".join(fields),
        start.isoformat(),
        end.isoformat(),
    )
    return rows


def _prepare_martes_loco_payload(
    db: Session,
    payload: dict,
    *,
    public_token: Optional[str],
) -> dict:
    response = dict(payload)
    if public_token:
        return sanitize_public_martes_loco_payload(response, public_token)

    share = get_active_martes_loco_share(db)
    response["shareToken"] = share.share_token if share else None
    response["publicToken"] = None
    return response


def _is_fresh(snapshot: KfcMartesLocoSnapshot, settings: Settings) -> bool:
    updated_at = snapshot.source_updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return updated_at >= utcnow() - timedelta(seconds=settings.cache_ttl_seconds)
