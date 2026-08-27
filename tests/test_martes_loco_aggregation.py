from __future__ import annotations

from datetime import date, datetime, timezone

from app.martes_loco import MartesLocoRawRows, build_martes_loco_payload


def meta_row(
    *,
    day: str,
    account_id: str,
    campaign: str,
    reach: str = "0",
    spend: str = "0",
    subs: str = "0",
    trials: str = "0",
    purch: str = "0",
    value: str = "0",
) -> dict:
    return {
        "date": day,
        "account_id": account_id,
        "account_name": "irrelevant",
        "campaign": campaign,
        "reach": reach,
        "spend": spend,
        "conversions_subscribe_mobile_app": subs,
        "conversions_start_trial_mobile_app": trials,
        "actions_omni_purchase": purch,
        "action_values_omni_purchase": value,
        "purchase_roas_omni_purchase": "999",
    }


def test_martes_loco_payload_sums_abril_and_agosto_campaigns_per_account() -> None:
    payload = build_martes_loco_payload(
        rows=MartesLocoRawRows(
            meta=[
                meta_row(
                    day="2026-04-21",
                    account_id="7266308733410766",
                    campaign="ECU_2026_ABRIL_KFC_META_DOMICILIO APP_MARTES V3_ADQUISICION",
                    reach="30000",
                    spend="50.00",
                    subs="100",
                    trials="70",
                    purch="150",
                    value="2000.00",
                ),
                meta_row(
                    day="2026-04-21",
                    account_id="7266308733410766",
                    campaign="ECU_2026_AGOSTO_KFC_META_DOMICILIO APP_MARTES_ADQUISICION",
                    reach="20653",
                    spend="36.02",
                    subs="45",
                    trials="28",
                    purch="94",
                    value="1843.83",
                ),
                meta_row(
                    day="2026-04-21",
                    account_id="1170894797052218",
                    campaign="ECU_2026_ABRIL_KFC_META_EXPRESS_MARTES LOCO_ADQUISICION",
                    reach="107399",
                    spend="388.00",
                    subs="175",
                    trials="262",
                    purch="442",
                    value="6258.73",
                ),
            ],
        ),
        from_date=date(2026, 4, 21),
        to_date=date(2026, 4, 21),
        updated_at=datetime(2026, 8, 5, 12, tzinfo=timezone.utc),
    )

    assert payload["dashboardId"] == "kfc-martes-loco"
    assert payload["isMock"] is False
    assert payload["source"] == "windsor"
    assert payload["from"] == "2026-04-21"
    assert payload["to"] == "2026-04-21"
    assert payload["rows"] == [
        ["2026-04-21", "A", 50653, 86.02, 145, 98, 244, 3843.83],
        ["2026-04-21", "P", 107399, 388.0, 175, 262, 442, 6258.73],
    ]
    assert payload["accounts"]["A"]["accountId"] == "7266308733410766"
    assert payload["accounts"]["P"]["accountId"] == "1170894797052218"


def test_martes_loco_ignores_non_matching_campaigns_accounts_and_out_of_range_days() -> None:
    payload = build_martes_loco_payload(
        rows=MartesLocoRawRows(
            meta=[
                # Wrong campaign (no "MARTES" token) — must be ignored.
                meta_row(
                    day="2026-04-21",
                    account_id="7266308733410766",
                    campaign="ECU_2026_ABRIL_KFC_META_DOMICILIO APP_OTRO_ADQUISICION",
                    spend="999",
                    purch="999",
                ),
                # Unknown account — must be ignored even if campaign matches.
                meta_row(
                    day="2026-04-21",
                    account_id="000000000000000",
                    campaign="ECU_2026_ABRIL_KFC_META_DOMICILIO APP_MARTES_ADQUISICION",
                    spend="999",
                    purch="999",
                ),
                # In range and matching — must be kept.
                meta_row(
                    day="2026-04-21",
                    account_id="7266308733410766",
                    campaign="ECU_2026_ABRIL_KFC_META_DOMICILIO APP_MARTES_ADQUISICION",
                    reach="100",
                    spend="10.00",
                    purch="2",
                    value="20.00",
                ),
                # Outside the requested range — must be ignored.
                meta_row(
                    day="2026-05-01",
                    account_id="7266308733410766",
                    campaign="ECU_2026_ABRIL_KFC_META_DOMICILIO APP_MARTES_ADQUISICION",
                    spend="999",
                    purch="999",
                ),
            ],
        ),
        from_date=date(2026, 4, 21),
        to_date=date(2026, 4, 21),
        updated_at=datetime(2026, 8, 5, 12, tzinfo=timezone.utc),
    )

    assert payload["rows"] == [["2026-04-21", "A", 100, 10.0, 0, 0, 2, 20.0]]


def test_sanitize_public_martes_loco_payload_strips_private_fields() -> None:
    from app.martes_loco import sanitize_public_martes_loco_payload

    payload = build_martes_loco_payload(
        rows=MartesLocoRawRows(meta=[]),
        from_date=date(2026, 4, 21),
        to_date=date(2026, 4, 21),
        updated_at=datetime(2026, 8, 5, 12, tzinfo=timezone.utc),
        share_token="internal-share-token",
        source_error="private windsor error detail",
    )

    sanitized = sanitize_public_martes_loco_payload(payload, "public-token")
    assert sanitized["publicToken"] == "public-token"
    assert "shareToken" not in sanitized
    assert "sourceError" not in sanitized
