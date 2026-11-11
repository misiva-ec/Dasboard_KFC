"""Refresca métricas diarias de Tropiburger sin modificar la foto histórica del ZIP."""
from __future__ import annotations

import json
import logging
import math
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, JSON
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.config import Settings
from app.database import Base
from app.windsor import WindsorClient, WindsorError

log = logging.getLogger(__name__)
SEED = Path(__file__).parent / 'data' / 'tropiburger.json'
BASE = date(2025, 1, 1)
PLATFORMS = {
    'META': ('facebook', '624569984856986', ['actions_link_click', 'video_thruplay_watched_actions_video_view', 'actions_onsite_conversion_messaging_conversation_started_7d']),
    'TIKTOK': ('tiktok', '7137826959748399106', ['clicks', 'focused_view_15s']),
    'DV360': ('dv360', '566048579', ['clicks', 'complete_views_video']),
    'GOOGLE': ('google_ads', '991-948-3303', ['clicks', 'video_trueview_views', 'conversions']),
}

class TropiburgerSnapshot(Base):
    __tablename__ = 'tropiburger_snapshots'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

_lock = threading.Lock()
_state = {'refreshing': False, 'error': None}

def status():
    with _lock:
        return dict(_state)

def latest(db: Session):
    return db.query(TropiburgerSnapshot).order_by(TropiburgerSnapshot.id.desc()).first()

def load_data(db: Session):
    snapshot = latest(db)
    if snapshot:
        return dict(snapshot.payload_json)
    return json.loads(SEED.read_text(encoding='utf-8'))

def start_refresh(settings: Settings):
    with _lock:
        if _state['refreshing']:
            return False
        _state.update(refreshing=True, error=None)
    threading.Thread(target=_run, args=(settings,), daemon=True, name='tropiburger-refresh').start()
    return True

def _run(settings):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        _, failures = refresh_data(db, settings)
        with _lock:
            _state['error'] = ('No se pudieron actualizar: ' + ', '.join(failures)) if failures else None
    except Exception:
        log.exception('Falló la actualización de Tropiburger')
        with _lock:
            _state['error'] = 'No se pudo actualizar Tropiburger. Se conservan los datos anteriores.'
    finally:
        db.close()
        with _lock:
            _state['refreshing'] = False

def _number(value):
    try:
        v = float(value or 0)
        if not math.isfinite(v):
            raise ValueError('non-finite')
        return v
    except (TypeError, ValueError):
        raise WindsorError('Dato numérico inválido')

def _normalize_account(value):
    return str(value or '').replace('-', '').strip()

def _fetch(client, platform, start, end):
    connector, account, fields = PLATFORMS[platform]
    rows = client.fetch_connector(connector, ['account_id', 'date', 'campaign', 'spend', 'impressions'] + fields,
                                  start, end, filters=[['account_id', 'eq', account]])
    result = []
    for row in rows:
        if _normalize_account(row.get('account_id')) != _normalize_account(account):
            raise WindsorError('La cuenta devuelta no coincide con la solicitada')
        try:
            day = date.fromisoformat(str(row.get('date', ''))[:10])
        except ValueError:
            raise WindsorError('La fecha devuelta no es válida')
        if not start <= day <= end:
            raise WindsorError('La fecha devuelta está fuera del periodo')
        name = re.sub(r'\s+', ' ', str(row.get('campaign') or '')).strip()
        if not name:
            raise WindsorError('La campaña devuelta no tiene nombre')
        result.append((day, name, row))
    return result

def refresh_data(db: Session, settings: Settings, client=None, today=None):
    client = client or WindsorClient(settings)
    today = today or datetime.now(ZoneInfo(settings.app_timezone)).date()
    start = max(date(2026, 1, 1), today - timedelta(days=30))
    previous = load_data(db)
    snap = previous['snap']
    camps = [list(c) for c in snap['camps']]
    original_rows = [list(row) for row in snap['rows']]
    rows = original_rows[:]
    camp_index = {(c[0], c[1]): i for i, c in enumerate(camps)}
    cuts = dict(previous.get('platformThrough') or {})
    for row in original_rows:
        medium = camps[row[0]][0]
        day = (BASE + timedelta(days=row[1])).isoformat()
        if medium in PLATFORMS and day > cuts.get(medium, ''):
            cuts[medium] = day
    failures = []
    updated = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {p: executor.submit(_fetch, client, p, start, today) for p in PLATFORMS}
    for platform in PLATFORMS:
        try:
            result = futures[platform].result()
            first = (start - BASE).days
            # Una respuesta vacía no debe borrar actividad que ya se había guardado.
            if not result and any(camps[r[0]][0] == platform and r[1] >= first for r in rows):
                raise WindsorError('Respuesta vacía para un periodo con actividad previa')
            aggregate = {}
            for day, name, raw in result:
                key = (platform, name)
                if key not in camp_index:
                    camp_index[key] = len(camps)
                    camps.append([platform, name, None])
                rowkey = (camp_index[key], (day - BASE).days)
                bucket = aggregate.setdefault(rowkey, [0, 0, 0, 0, 0])
                metric_fields = PLATFORMS[platform][2]
                cost = _number(raw.get('spend'))
                impressions = _number(raw.get('impressions'))
                clicks = _number(raw.get(metric_fields[0]))
                views = _number(raw.get(metric_fields[1]))
                conversations = _number(raw.get(metric_fields[2])) if len(metric_fields) > 2 else 0
                for i, value in enumerate((cost, impressions, clicks, views, conversations)):
                    bucket[i] += value
            if result:
                rows = [r for r in rows if not (camps[r[0]][0] == platform and r[1] >= first)]
                for (ci, di), values in aggregate.items():
                    rows.append([ci, di, int(round(values[0] * 100)), *[int(round(v)) for v in values[1:]]])
                cuts[platform] = max(day for day, _, _ in result).isoformat()
                updated.append(platform)
        except Exception as exc:
            log.warning('No se actualizó %s: %s', platform, type(exc).__name__)
            failures.append(platform)
    if not updated:
        raise WindsorError('Ninguna fuente devolvió datos actualizados')
    payload = dict(previous)
    payload.update(snap={**snap, 'camps': camps, 'rows': rows},
                   platformThrough=cuts,
                   updatedAt=datetime.now(timezone.utc).isoformat(),
                   historicalThrough='2026-11-09')
    db.add(TropiburgerSnapshot(payload_json=payload, created_at=datetime.now(timezone.utc)))
    db.commit()
    return payload, failures
