"""Endpoints del Reporte KFC · Autorápido y Helados.

Privados (Bearer de Entra ID + rol `kfchiden`, NO el rol Planners/admin del resto de dashboards KFC):
    GET    /api/kfc-reporte/dashboard
    POST   /api/kfc-reporte/share
    DELETE /api/kfc-reporte/share

Público (solo token, sin sesión):
    GET    /api/public/kfc-reporte/{share_token}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.kfc_reporte import (
    KfcReporteUnavailable,
    create_kfc_reporte_share_token,
    get_kfc_reporte_dashboard,
    get_kfc_reporte_share_by_token,
    isoformat_z,
    revoke_kfc_reporte_share_token,
)
from app.rate_limit import InMemoryRateLimiter, request_ip
from app.security import AuthUser, require_kfc_reporte_role

router = APIRouter(tags=["kfc-reporte"])

_settings = get_settings()
rate_limiter = InMemoryRateLimiter(
    _settings.public_rate_limit_requests,
    _settings.public_rate_limit_window_seconds,
)


@router.get("/api/kfc-reporte/dashboard")
def kfc_reporte_dashboard(
    _: AuthUser = Depends(require_kfc_reporte_role),
    db: Session = Depends(get_db),
):
    try:
        return get_kfc_reporte_dashboard(db)
    except KfcReporteUnavailable:
        return _unavailable()


@router.post("/api/kfc-reporte/share")
def kfc_reporte_share(
    user: AuthUser = Depends(require_kfc_reporte_role),
    db: Session = Depends(get_db),
) -> dict:
    row = create_kfc_reporte_share_token(db, user)
    return {"shareToken": row.share_token, "sharedAt": isoformat_z(row.shared_at)}


@router.delete("/api/kfc-reporte/share", status_code=status.HTTP_204_NO_CONTENT)
def kfc_reporte_revoke_share(
    _: AuthUser = Depends(require_kfc_reporte_role),
    db: Session = Depends(get_db),
) -> Response:
    revoke_kfc_reporte_share_token(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/public/kfc-reporte/{share_token}")
def kfc_reporte_public_dashboard(
    share_token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    rate_limiter.check(request_ip(request))
    if not get_kfc_reporte_share_by_token(db, share_token):
        # 404 y no 403: un token revocado no debe confirmar que existió.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        return get_kfc_reporte_dashboard(db, public_token=share_token)
    except KfcReporteUnavailable:
        return _unavailable()


def _unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error": "El reporte no está disponible en este momento. Intenta de nuevo en unos minutos."},
    )
