from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Optional

ONION_MUNDIAL_DASHBOARD_ID = "kfc-onion-mundial"
ONION_MUNDIAL_START_DATE = date(2026, 5, 13)
META_APP_ACCOUNT_ID = "7266308733410766"
META_PYR_ACCOUNT_ID = "1170894797052218"
ONION_MUNDIAL_META_FIELDS = [
    "date", "account_id", "campaign", "adset_name", "spend",
    "actions_omni_purchase", "action_values_omni_purchase",
    "conversions_start_trial_total", "conversions_subscribe_total",
    "conversions_start_trial_mobile_app", "conversions_subscribe_mobile_app",
]

_ZERO = Decimal("0")

# Las seis series del reporte tienen flights distintos. Windsor conserva las
# campañas después de terminar el flight, por eso no basta con buscar las
# palabras ONION/MUNDIAL: hacerlo mezcla meses, adquisición y retención.
_FLIGHTS = {
    "paraguasOnion": (date(2026, 8, 7), 19),
    "paraguasMundial": (date(2026, 5, 13), 19),
    "domicilioOnion": (date(2026, 7, 24), 33),
    "domicilioMundial": (date(2026, 5, 14), 33),
    "expressOnion": (date(2026, 7, 24), 33),
    "expressMundial": (date(2026, 5, 14), 33),
}


@dataclass(frozen=True)
class OnionMundialRawRows:
    meta: list[dict[str, Any]]


def build_onion_mundial_payload(*, rows: OnionMundialRawRows, from_date: date,
    to_date: date, updated_at: datetime, share_token: Optional[str] = None,
    public_token: Optional[str] = None, is_stale: bool = False,
    source_error: Optional[str] = None, source: str = "windsor") -> dict[str, Any]:
    groups: dict[str, list[list[Any]]] = {key: [] for key in (
        "paraguasOnion", "paraguasMundial", "domicilioOnion",
        "domicilioMundial", "expressOnion", "expressMundial")}
    buckets: dict[tuple[str, date], dict[str, Decimal]] = {}
    for row in rows.meta:
        day = _parse_date(row.get("date"))
        if day is None or day < from_date or day > to_date:
            continue
        group = _classify(row)
        if not group or not _is_flight_day(group, day):
            continue
        bucket = buckets.setdefault((group, day), {k: _ZERO for k in ("spend", "purchases", "value", "trial", "subs")})
        bucket["spend"] += _decimal(row, "spend")
        bucket["purchases"] += _decimal(row, "actions_omni_purchase")
        bucket["value"] += _decimal(row, "action_values_omni_purchase")
        bucket["trial"] += _decimal(row, "conversions_start_trial_total", "conversions_start_trial_mobile_app")
        bucket["subs"] += _decimal(row, "conversions_subscribe_total", "conversions_subscribe_mobile_app")
    for group, (start, length) in _FLIGHTS.items():
        for offset in range(length):
            day = date.fromordinal(start.toordinal() + offset)
            if day < from_date or day > to_date:
                continue
            values = buckets.get((group, day))
            if values is None:
                groups[group].append([day.isoformat(), None, None, None, None, None])
            else:
                groups[group].append([day.isoformat(), _money(values["spend"]), _count(values["purchases"]),
                    _money(values["value"]), _count(values["trial"]), _count(values["subs"])])
    payload: dict[str, Any] = {
        "dashboardId": ONION_MUNDIAL_DASHBOARD_ID, "title": "Onion vs Mundial",
        "brand": "KFC", "isMock": False, "source": source,
        "updatedAt": _iso_z(updated_at), "from": from_date.isoformat(), "to": to_date.isoformat(),
        "groups": groups,
        "rules": {"connector": "windsor.ai → facebook (Meta Ads)",
            "accounts": [META_APP_ACCOUNT_ID, META_PYR_ACCOUNT_ID],
            "comparison": "Día de flight", "currency": "USD",
            "filterVersion": "exact-flights-v1"},
        "shareToken": share_token, "publicToken": public_token,
    }
    if is_stale: payload.update({"isStale": True, "stale": True})
    if source_error: payload["sourceError"] = source_error
    return payload


def sanitize_public_onion_mundial_payload(payload: dict[str, Any], token: str) -> dict[str, Any]:
    allowed = {"dashboardId", "title", "brand", "isMock", "source", "updatedAt", "from", "to", "groups", "rules", "publicToken", "isStale", "stale"}
    result = {key: value for key, value in payload.items() if key in allowed}
    result["publicToken"] = token
    return result


def _classify(row: dict[str, Any]) -> Optional[str]:
    account = str(row.get("account_id") or "").replace("-", "").replace(" ", "")
    if account not in {META_APP_ACCOUNT_ID, META_PYR_ACCOUNT_ID}: return None
    campaign = _norm(str(row.get("campaign") or ""))
    adset = _norm(str(row.get("adset_name") or ""))

    if account == META_APP_ACCOUNT_ID:
        if "PARAGUAS ONION ESPACIO AGREGADORES" in campaign and "AGOSTO" in adset and "ONION ADQUISICION" in adset:
            return "paraguasOnion"
        if "PARAGUAS AON DIPPING MUNDIAL ONION ESPACIO AGREGADORES" in campaign and "MAYO" in adset and "MUNDIAL ADQUISICION" in adset:
            return "paraguasMundial"
        if "DOMICILIO APP ONION RINGS" in campaign and "JULIO" in adset and "ONION RETENCION" in adset:
            return "domicilioOnion"
        if "MUNDIAL APP RETENCION AON" in campaign and "MAYO" in adset and "DOMICILIO RETENCION" in adset:
            return "domicilioMundial"
        if "MUNDIAL APP RETENCION AON" in campaign and "MAYO" in adset and "EXPRESS RETENCION" in adset:
            return "expressMundial"
    if account == META_PYR_ACCOUNT_ID and "EXPRESS ONION" in campaign and "JULIO" in adset and "ONION RETENCION" in adset:
        return "expressOnion"
    return None


def _is_flight_day(group: str, day: date) -> bool:
    start, length = _FLIGHTS[group]
    return start <= day < date.fromordinal(start.toordinal() + length)


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.upper()).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", " ", value).strip()


def _decimal(row: dict[str, Any], *keys: str) -> Decimal:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            try: return Decimal(str(value).replace(",", ""))
            except InvalidOperation: pass
    return _ZERO


def _parse_date(value: Any) -> Optional[date]:
    try: return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError): return None


def _money(value: Decimal) -> float: return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
def _count(value: Decimal) -> int: return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
def _iso_z(value: datetime) -> str:
    if value.tzinfo is None: value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
