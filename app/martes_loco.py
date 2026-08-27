from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Optional, Union


MARTES_LOCO_DASHBOARD_ID = "kfc-martes-loco"
MARTES_LOCO_TITLE = "Martes Loco · KFC Ecuador"
MARTES_LOCO_BRAND = "KFC"
MARTES_LOCO_SOURCE = "windsor"
MARTES_LOCO_START_DATE = date(2026, 4, 7)

# Domicilio Martes Loco — L/C - Misiva - KFC- PERFORMANCE_INT FOOD_APP_
MARTES_LOCO_APP_ACCOUNT_ID = "7266308733410766"
# Martes Loco Express — L/C - Misiva - KFC- PERFORMANCE_INT FOOD_PYR_
MARTES_LOCO_PYR_ACCOUNT_ID = "1170894797052218"

# Maps a normalized Windsor account_id to the short account key used throughout
# the payload ("A" = Domicilio/APP, "P" = Express/PYR), matching the reference
# dashboard's RAW rows (date, acct, reach, spend, subs, trials, purch, value).
MARTES_LOCO_ACCOUNTS = {
    MARTES_LOCO_APP_ACCOUNT_ID: "A",
    MARTES_LOCO_PYR_ACCOUNT_ID: "P",
}

MARTES_LOCO_ACCOUNT_META = {
    "A": {
        "accountId": MARTES_LOCO_APP_ACCOUNT_ID,
        "accountName": "L/C - Misiva - KFC- PERFORMANCE_INT FOOD_APP_",
        "label": "Domicilio Martes Loco",
        "tag": "Cuenta APP",
    },
    "P": {
        "accountId": MARTES_LOCO_PYR_ACCOUNT_ID,
        "accountName": "L/C - Misiva - KFC- PERFORMANCE_INT FOOD_PYR_",
        "label": "Martes Loco Express",
        "tag": "Cuenta PYR",
    },
}

# "campaign contains MARTES" — each campaign exists in two versions (abril y
# agosto); rows from both are summed per date+account, same as Windsor's
# filters: [["campaign", "contains", "MARTES"]].
MARTES_LOCO_CAMPAIGN_TOKEN = "MARTES"

MARTES_LOCO_META_FIELDS = [
    "date",
    "account_id",
    "account_name",
    "campaign",
    "reach",
    "spend",
    "conversions_subscribe_mobile_app",
    "conversions_start_trial_mobile_app",
    "actions_omni_purchase",
    "action_values_omni_purchase",
    "purchase_roas_omni_purchase",
]

_ZERO = Decimal("0")
_TOKEN_RE = re.compile(r"[^A-Z0-9]+")


@dataclass(frozen=True)
class MartesLocoRawRows:
    meta: list[dict[str, Any]]


def build_martes_loco_payload(
    *,
    rows: MartesLocoRawRows,
    from_date: date,
    to_date: date,
    updated_at: datetime,
    share_token: Optional[str] = None,
    public_token: Optional[str] = None,
    is_stale: bool = False,
    source_error: Optional[str] = None,
    source: str = MARTES_LOCO_SOURCE,
) -> dict[str, Any]:
    daily_rows = _aggregate_rows(rows.meta, from_date, to_date)

    payload: dict[str, Any] = {
        "dashboardId": MARTES_LOCO_DASHBOARD_ID,
        "title": MARTES_LOCO_TITLE,
        "brand": MARTES_LOCO_BRAND,
        "isMock": False,
        "source": source,
        "updatedAt": _isoformat_z_ms(updated_at),
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        # [date, acct, reach, spend, subs, trials, purch, value] per day+account —
        # mirrors the RAW array the reference dashboard hardcodes.
        "rows": daily_rows,
        "accounts": MARTES_LOCO_ACCOUNT_META,
        "rules": {
            "connector": "windsor.ai → facebook (Meta Ads)",
            "campaignFilter": 'campaign contains "MARTES"',
            "accounts": {
                "A": MARTES_LOCO_APP_ACCOUNT_ID,
                "P": MARTES_LOCO_PYR_ACCOUNT_ID,
            },
            "period": f"{from_date.isoformat()} → {to_date.isoformat()}",
            "extractedAt": updated_at.astimezone(timezone.utc).date().isoformat(),
        },
        "shareToken": share_token,
        "publicToken": public_token,
    }
    if is_stale:
        payload["isStale"] = True
        payload["stale"] = True
    if source_error:
        payload["sourceError"] = source_error
    return payload


def sanitize_public_martes_loco_payload(payload: dict[str, Any], token: str) -> dict[str, Any]:
    allowed = {
        "dashboardId",
        "title",
        "brand",
        "isMock",
        "source",
        "updatedAt",
        "from",
        "to",
        "rows",
        "accounts",
        "rules",
        "publicToken",
        "isStale",
        "stale",
    }
    response = {key: value for key, value in payload.items() if key in allowed}
    response["publicToken"] = token
    return response


def _aggregate_rows(
    rows: list[dict[str, Any]],
    from_date: date,
    to_date: date,
) -> list[list[Any]]:
    buckets: dict[tuple[date, str], dict[str, Decimal]] = {}

    for row in rows:
        day = _safe_parse_date(_value(row, "date"))
        if day is None or day < from_date or day > to_date:
            continue

        account_id = _normalized_account_id(_account_id(row))
        acct = MARTES_LOCO_ACCOUNTS.get(account_id)
        if not acct:
            continue

        campaign = _string(row, "campaign")
        if MARTES_LOCO_CAMPAIGN_TOKEN not in _normalized_text(campaign):
            continue

        bucket = buckets.setdefault(
            (day, acct),
            {
                "reach": _ZERO,
                "spend": _ZERO,
                "subs": _ZERO,
                "trials": _ZERO,
                "purch": _ZERO,
                "value": _ZERO,
            },
        )
        bucket["reach"] += _decimal(row, "reach")
        bucket["spend"] += _decimal(row, "spend")
        bucket["subs"] += _decimal(row, "conversions_subscribe_mobile_app")
        bucket["trials"] += _decimal(row, "conversions_start_trial_mobile_app")
        bucket["purch"] += _decimal(row, "actions_omni_purchase")
        bucket["value"] += _decimal(row, "action_values_omni_purchase")

    ordered_keys = sorted(buckets.keys(), key=lambda key: (key[0].isoformat(), key[1]))
    result: list[list[Any]] = []
    for day, acct in ordered_keys:
        values = buckets[(day, acct)]
        result.append(
            [
                day.isoformat(),
                acct,
                _count(values["reach"]),
                _money(values["spend"]),
                _count(values["subs"]),
                _count(values["trials"]),
                _count(values["purch"]),
                _money(values["value"]),
            ]
        )
    return result


def _isoformat_z_ms(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _count(value: Decimal) -> Union[int, float]:
    integral = value.to_integral_value(rounding=ROUND_HALF_UP)
    if value == integral:
        return int(integral)
    return float(value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def _decimal(row: dict[str, Any], *keys: str) -> Decimal:
    value = _value(row, *keys)
    if value is None or value == "":
        return _ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    text = str(value).strip().replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric value: {value!r}") from exc


def _safe_parse_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _string(row: dict[str, Any], *keys: str) -> str:
    value = _value(row, *keys)
    return "" if value is None else str(value).strip()


def _account_id(row: dict[str, Any]) -> str:
    return _string(row, "account_id", "account", "accountid")


def _normalized_account_id(account_id: str) -> str:
    return account_id.replace("-", "").replace(" ", "").strip()


def _normalized_text(value: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return _TOKEN_RE.sub(" ", ascii_text.upper()).strip()
