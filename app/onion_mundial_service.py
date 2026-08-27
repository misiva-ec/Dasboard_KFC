from __future__ import annotations
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.config import Settings
from app.models import KfcOnionMundialShare, KfcOnionMundialSnapshot
from app.onion_mundial import ONION_MUNDIAL_START_DATE, ONION_MUNDIAL_META_FIELDS, OnionMundialRawRows, build_onion_mundial_payload, sanitize_public_onion_mundial_payload
from app.security import AuthUser
from app.windsor import WindsorClient, WindsorError

class OnionMundialDashboardUnavailable(RuntimeError): pass

def today_in_onion_mundial_timezone(settings: Settings) -> date: return datetime.now(ZoneInfo(settings.app_timezone)).date()
def normalize_onion_mundial_range(from_date: Optional[date], to_date: Optional[date], settings: Settings) -> tuple[date,date]:
    start, end = from_date or ONION_MUNDIAL_START_DATE, to_date or today_in_onion_mundial_timezone(settings)
    if start > end: raise ValueError("from must be before or equal to to")
    return start, end

def get_onion_mundial_dashboard(db: Session, settings: Settings, *, from_date=None, to_date=None, force_refresh=False, public_token=None):
    start,end=normalize_onion_mundial_range(from_date,to_date,settings); snap=latest_onion_mundial_snapshot(db,start,end)
    if (snap and not force_refresh
        and snap.payload_json.get("rules", {}).get("filterVersion") == "approved-html-v2"
        and datetime.now(timezone.utc)-_utc(snap.source_updated_at) <= timedelta(seconds=settings.cache_ttl_seconds)):
        return _prepare(db,dict(snap.payload_json),public_token)
    try: return _prepare(db,refresh_onion_mundial_dashboard(db,settings,from_date=start,to_date=end),public_token)
    except WindsorError:
        if snap:
            payload=dict(snap.payload_json); payload.update({"isStale":True,"stale":True,"source":"snapshot","sourceError":"windsor_unavailable"}); return _prepare(db,payload,public_token)
        raise OnionMundialDashboardUnavailable("No cached onion-mundial dashboard is available")

def refresh_onion_mundial_dashboard(db: Session, settings: Settings, *, from_date=None, to_date=None):
    start,end=normalize_onion_mundial_range(from_date,to_date,settings)
    rows=WindsorClient(settings).fetch_connector("facebook",ONION_MUNDIAL_META_FIELDS,start,end)
    now=datetime.now(timezone.utc); share=get_active_onion_mundial_share(db)
    payload=build_onion_mundial_payload(rows=OnionMundialRawRows(rows),from_date=start,to_date=end,updated_at=now,share_token=share.share_token if share else None)
    db.add(KfcOnionMundialSnapshot(from_date=start,to_date=end,payload_json=payload,source_updated_at=now)); db.commit(); return payload

def latest_onion_mundial_snapshot(db,start,end): return db.query(KfcOnionMundialSnapshot).filter_by(from_date=start,to_date=end).order_by(KfcOnionMundialSnapshot.created_at.desc()).first()
def get_active_onion_mundial_share(db): return db.query(KfcOnionMundialShare).filter(KfcOnionMundialShare.revoked_at.is_(None)).order_by(KfcOnionMundialShare.shared_at.desc()).first()
def create_onion_mundial_share_token(db,user:AuthUser):
    row=get_active_onion_mundial_share(db)
    if row: return row
    row=KfcOnionMundialShare(share_token=secrets.token_urlsafe(32),shared_at=datetime.now(timezone.utc),created_by_oid=user.oid,created_by_email=user.email); db.add(row); db.commit(); db.refresh(row); return row
def revoke_onion_mundial_share_token(db):
    row=get_active_onion_mundial_share(db)
    if row: row.revoked_at=datetime.now(timezone.utc); db.commit()
def get_onion_mundial_share_by_token(db,token): return db.query(KfcOnionMundialShare).filter_by(share_token=token,revoked_at=None).first()
def _prepare(db,payload,public_token):
    if public_token: return sanitize_public_onion_mundial_payload(payload,public_token)
    share=get_active_onion_mundial_share(db); payload["shareToken"]=share.share_token if share else None; return payload
def _utc(value): return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
