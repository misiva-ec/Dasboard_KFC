"""Reporte KFC · Autorápido y Helados: datos del reporte y enlace público.

El reporte (inversión, impresiones, clics y alcance semanal por plataforma, en Autorápido y Helados) se
armó fuera de Windsor, con ajustes de alcance hechos a mano (Meta por campañas juntas, Google Ads de
Helados = impresiones ÷ 2). Por eso NO se consulta a Windsor desde aquí: los datos viven en
`app/data/kfc_reporte.json` y el backend los sirve tal cual, con el rol `kfchiden` o con el token del
enlace del cliente. Para cargar una semana nueva se reemplaza ese archivo (el front ve el cambio solo,
por `updatedAt`).

Los cálculos del reporte (shares, cobertura multimedios, universos) corren en el front, no aquí.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models import KfcReporteShare, utcnow
from app.security import AuthUser

DATA_FILE = Path(__file__).parent / "data" / "kfc_reporte.json"

DASHBOARD_ID = "kfc-reporte"
REQUIRED_DATASETS = ("campanas", "alcance_ajustado")


class KfcReporteUnavailable(RuntimeError):
    """El archivo de datos no está o no tiene la forma que espera el reporte."""


def isoformat_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_report(path: Path = DATA_FILE) -> dict:
    """Lee el archivo en cada petición (pesa ~20 KB): reemplazarlo no obliga a reiniciar el servicio."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise KfcReporteUnavailable(f"No se pudo leer {path.name}: {exc}") from exc

    datasets = raw.get("datasets") if isinstance(raw, dict) else None
    if not isinstance(datasets, dict) or not all(isinstance(datasets.get(k), list) for k in REQUIRED_DATASETS):
        raise KfcReporteUnavailable(f"{path.name} debe traer datasets.{' y datasets.'.join(REQUIRED_DATASETS)} como listas.")
    if not isinstance(raw.get("updatedAt"), str):
        raise KfcReporteUnavailable(f"{path.name} debe traer updatedAt.")
    return raw


def get_kfc_reporte_dashboard(db: Session, *, public_token: Optional[str] = None) -> dict:
    report = load_report()
    payload = {
        "dashboardId": DASHBOARD_ID,
        "title": report.get("title") or "Reporte KFC · Autorápido y Helados",
        "brand": "KFC",
        "source": "reporte",
        "updatedAt": report["updatedAt"],
        "datasets": report["datasets"],
    }
    if public_token:
        # La vista del cliente no ve el token del enlace privado (`shareToken`), solo el suyo.
        payload["publicToken"] = public_token
        return payload

    share = get_active_share(db)
    payload["shareToken"] = share.share_token if share else None
    payload["publicToken"] = None
    return payload


# --------------------------------------------------------------------------
# enlace público
# --------------------------------------------------------------------------
def get_active_share(db: Session) -> Optional[KfcReporteShare]:
    return (
        db.query(KfcReporteShare)
        .filter(KfcReporteShare.revoked_at.is_(None))
        .order_by(KfcReporteShare.shared_at.desc())
        .first()
    )


def create_kfc_reporte_share_token(db: Session, user: AuthUser) -> KfcReporteShare:
    existing = get_active_share(db)
    if existing:
        return existing

    share = KfcReporteShare(
        share_token=secrets.token_urlsafe(32),
        shared_at=utcnow(),
        created_by_oid=user.oid,
        created_by_email=user.email,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return share


def revoke_kfc_reporte_share_token(db: Session) -> None:
    now = utcnow()
    for share in db.query(KfcReporteShare).filter(KfcReporteShare.revoked_at.is_(None)).all():
        share.revoked_at = now
    db.commit()


def get_kfc_reporte_share_by_token(db: Session, token: str) -> Optional[KfcReporteShare]:
    return (
        db.query(KfcReporteShare)
        .filter(KfcReporteShare.share_token == token, KfcReporteShare.revoked_at.is_(None))
        .one_or_none()
    )
