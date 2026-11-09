"""Reporte KFC · Autorápido y Helados: rol propio (kfchiden), datos del reporte y enlace público."""
from __future__ import annotations

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.kfc_reporte as reporte
from app.database import Base, get_db
from app.main import app
from app.security import AuthUser, get_current_user

AUTH = {"Authorization": "Bearer cualquiera"}


def _usuario(*roles: str) -> AuthUser:
    return AuthUser(oid="oid-1", email="kfc@misiva.test", roles=set(roles), claims={})


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def get_test_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_current_user] = lambda: _usuario("kfchiden")
    yield TestClient(app)
    app.dependency_overrides.clear()


def _como(*roles: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: _usuario(*roles)


# --------------------------------------------------------------------------
# acceso
# --------------------------------------------------------------------------
def test_sin_sesion_los_endpoints_privados_son_401() -> None:
    c = TestClient(app)
    assert c.get("/api/kfc-reporte/dashboard").status_code == 401
    assert c.post("/api/kfc-reporte/share").status_code == 401
    assert c.delete("/api/kfc-reporte/share").status_code == 401


@pytest.mark.parametrize("roles", [("Planners",), ("admin",), ("dasboardkfc",), ()])
def test_solo_kfchiden_entra_ni_planners_ni_admin(client, roles) -> None:
    _como(*roles)
    assert client.get("/api/kfc-reporte/dashboard", headers=AUTH).status_code == 403
    assert client.post("/api/kfc-reporte/share", headers=AUTH).status_code == 403
    assert client.delete("/api/kfc-reporte/share", headers=AUTH).status_code == 403


def test_kfchiden_entra_sin_importar_mayusculas_y_con_otros_roles(client) -> None:
    _como("KFCHiden", "Planners")
    assert client.get("/api/kfc-reporte/dashboard", headers=AUTH).status_code == 200


def test_el_rol_se_puede_cambiar_por_configuracion(client, monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("KFC_REPORTE_ROLES", "kfchiden,admin")
    get_settings.cache_clear()
    try:
        _como("admin")
        assert client.get("/api/kfc-reporte/dashboard", headers=AUTH).status_code == 200
    finally:
        monkeypatch.delenv("KFC_REPORTE_ROLES")
        get_settings.cache_clear()


# --------------------------------------------------------------------------
# datos
# --------------------------------------------------------------------------
def test_dashboard_sirve_los_datos_del_reporte(client) -> None:
    body = client.get("/api/kfc-reporte/dashboard", headers=AUTH).json()
    assert body["dashboardId"] == "kfc-reporte" and body["source"] == "reporte"
    assert datetime.fromisoformat(body["updatedAt"].replace("Z", "+00:00"))
    campanas, alcance = body["datasets"]["campanas"], body["datasets"]["alcance_ajustado"]
    assert len(campanas) == 71 and len(alcance) == 26
    assert {r["brand"] for r in campanas} == {"auto", "helados"}
    assert {r["platform"] for r in campanas} == {"Meta", "TikTok", "DV360", "Google Ads"}
    assert {r["week"] for r in campanas} == {"S40", "S41", "S42", "S43", "S44", "S45"}
    assert body["shareToken"] is None and body["publicToken"] is None


def test_los_totales_del_reporte_cuadran_con_el_original(client) -> None:
    # Inversión total de cada línea en el reporte-kfc.html entregado (1 oct → 8 nov 2026): el archivo de datos
    # tiene que seguir dando estas cifras mientras nadie cargue semanas nuevas a propósito.
    campanas = client.get("/api/kfc-reporte/dashboard", headers=AUTH).json()["datasets"]["campanas"]
    gasto = {b: round(sum(float(r["spend"]) for r in campanas if r["brand"] == b), 2) for b in ("auto", "helados")}
    assert gasto == {"auto": 13786.01, "helados": 21328.88}


def test_cada_fila_de_alcance_ajustado_tiene_su_fila_de_campana(client) -> None:
    ds = client.get("/api/kfc-reporte/dashboard", headers=AUTH).json()["datasets"]
    existentes = {(r["brand"], r["platform"], r["week"]) for r in ds["campanas"]}
    assert all((r["brand"], r["platform"], r["week"]) in existentes for r in ds["alcance_ajustado"])


def test_archivo_de_datos_invalido_responde_503(client, tmp_path) -> None:
    malo = tmp_path / "kfc_reporte.json"
    malo.write_text(json.dumps({"updatedAt": "2026-11-09T00:00:00Z", "datasets": {"campanas": []}}), encoding="utf-8")
    with pytest.raises(reporte.KfcReporteUnavailable):
        reporte.load_report(malo)
    with pytest.raises(reporte.KfcReporteUnavailable):
        reporte.load_report(tmp_path / "no-existe.json")


def test_si_el_archivo_falla_el_endpoint_contesta_503_con_mensaje(client, monkeypatch) -> None:
    def roto(*_a, **_k):
        raise reporte.KfcReporteUnavailable("sin archivo")

    monkeypatch.setattr(reporte, "load_report", roto)
    r = client.get("/api/kfc-reporte/dashboard", headers=AUTH)
    assert r.status_code == 503 and "error" in r.json()
    assert "sin archivo" not in r.text  # el detalle interno no sale al navegador


# --------------------------------------------------------------------------
# enlace público
# --------------------------------------------------------------------------
def test_enlace_publico_funciona_sin_sesion_y_oculta_lo_interno(client) -> None:
    token = client.post("/api/kfc-reporte/share", headers=AUTH).json()["shareToken"]
    app.dependency_overrides.pop(get_current_user)  # el cliente no tiene sesión
    r = client.get("/api/public/kfc-reporte/" + token)
    assert r.status_code == 200
    body = r.json()
    assert body["publicToken"] == token and "shareToken" not in body
    assert len(body["datasets"]["campanas"]) == 71


def test_compartir_dos_veces_reusa_el_mismo_token_y_el_privado_lo_trae(client) -> None:
    a = client.post("/api/kfc-reporte/share", headers=AUTH).json()["shareToken"]
    b = client.post("/api/kfc-reporte/share", headers=AUTH).json()["shareToken"]
    assert a == b
    assert client.get("/api/kfc-reporte/dashboard", headers=AUTH).json()["shareToken"] == a


def test_enlace_revocado_o_inventado_es_404(client) -> None:
    token = client.post("/api/kfc-reporte/share", headers=AUTH).json()["shareToken"]
    assert client.delete("/api/kfc-reporte/share", headers=AUTH).status_code == 204
    assert client.get("/api/public/kfc-reporte/" + token).status_code == 404
    assert client.get("/api/public/kfc-reporte/inventado").status_code == 404
    # Un token de OTRO dashboard KFC no abre este reporte.
    assert client.get("/api/public/kfc-mundial/" + token).status_code == 404
