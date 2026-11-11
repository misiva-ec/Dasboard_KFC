"""Dashboard Tropiburger: acceso privado y enlaces públicos revocables."""
import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.config import get_settings
from app.database import Base, get_db
from app.models import utcnow
from app.rate_limit import InMemoryRateLimiter, request_ip
from app.security import AuthUser, require_dashboard_role
from app.tropiburger_refresh import load_data, start_refresh, status as refresh_status

router = APIRouter(tags=['tropiburger'])
DATA_FILE = Path(__file__).parent / 'data' / 'tropiburger.json'
settings = get_settings()
rate_limiter = InMemoryRateLimiter(settings.public_rate_limit_requests, settings.public_rate_limit_window_seconds)

class TropiburgerShare(Base):
    __tablename__ = 'tropiburger_share'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    share_token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    shared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_oid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_by_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)

def active_share(db: Session):
    return db.query(TropiburgerShare).filter(TropiburgerShare.revoked_at.is_(None)).order_by(TropiburgerShare.shared_at.desc()).first()

@router.get('/api/tropiburger/dashboard')
def tropiburger_dashboard(_: AuthUser = Depends(require_dashboard_role), db: Session = Depends(get_db)):
    payload = load_data(db)
    share = active_share(db)
    return {**payload, **refresh_status(), 'shareToken': share.share_token if share else None}

@router.post('/api/tropiburger/refresh', status_code=202)
def refresh_dashboard(_: AuthUser = Depends(require_dashboard_role)):
    return {'started': start_refresh(settings), **refresh_status()}

@router.post('/api/tropiburger/share')
def create_share(user: AuthUser = Depends(require_dashboard_role), db: Session = Depends(get_db)):
    share = active_share(db)
    if not share:
        share = TropiburgerShare(share_token=secrets.token_urlsafe(32), shared_at=utcnow(), created_by_oid=user.oid, created_by_email=user.email)
        db.add(share)
        db.commit()
        db.refresh(share)
    return {'shareToken': share.share_token}

@router.delete('/api/tropiburger/share', status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(_: AuthUser = Depends(require_dashboard_role), db: Session = Depends(get_db)):
    for share in db.query(TropiburgerShare).filter(TropiburgerShare.revoked_at.is_(None)).all():
        share.revoked_at = utcnow()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get('/api/public/tropiburger/{share_token}')
def public_dashboard(share_token: str, request: Request, db: Session = Depends(get_db)):
    rate_limiter.check(request_ip(request))
    share = db.query(TropiburgerShare).filter(TropiburgerShare.share_token == share_token, TropiburgerShare.revoked_at.is_(None)).first()
    if not share:
        raise HTTPException(status_code=404, detail='Not found')
    return load_data(db)
