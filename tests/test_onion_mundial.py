from datetime import date, datetime, timezone
from app.onion_mundial import OnionMundialRawRows, build_onion_mundial_payload

def row(day, account, campaign, adset=""):
    return {"date": day, "account_id": account, "campaign": campaign, "adset_name": adset,
        "spend": "10", "actions_omni_purchase": "2", "action_values_omni_purchase": "30",
        "conversions_start_trial_total": "1", "conversions_subscribe_total": "1"}

def test_classifies_the_six_flight_series():
    app = "7266308733410766"
    pyr = "1170894797052218"
    paraguas = "PARAGUAS AON/DIPPING/MUNDIAL/ONION/ESPACIO AGREGADORES"
    mundial = "MUNDIAL APP_RETENCION AON"
    raw = [
        row("2026-08-07", app, "PARAGUAS_ONION/ESPACIO AGREGADORES", "AGOSTO_ONION_ADQUISICION"),
        row("2026-05-13", app, paraguas, "MAYO_MUNDIAL_ADQUISICION"),
        row("2026-07-24", app, "DOMICILIO APP_ONION RINGS", "JULIO_ONION_RETENCION"),
        row("2026-05-14", app, mundial, "MAYO_DOMICILIO_RETENCION"),
        row("2026-07-25", pyr, "EXPRESS_ONION", "JULIO_ONION_RETENCION"),
        row("2026-05-14", app, mundial, "MAYO_EXPRESS_RETENCION"),
    ]
    payload = build_onion_mundial_payload(rows=OnionMundialRawRows(raw), from_date=date(2026,5,13), to_date=date(2026,8,25), updated_at=datetime.now(timezone.utc))
    assert len(payload["groups"]["paraguasOnion"]) == 19
    assert all(len(payload["groups"][key]) == 33 for key in (
        "domicilioOnion", "domicilioMundial", "expressOnion", "expressMundial"))
    assert payload["groups"]["paraguasOnion"][0] == ["2026-08-07", 10.0, 2, 30.0, 1, 1]
    assert payload["groups"]["expressOnion"][0] == ["2026-07-24", None, None, None, None, None]
    assert payload["groups"]["expressOnion"][1] == ["2026-07-25", 10.0, 2, 30.0, 1, 1]

def test_ignores_unknown_accounts_and_campaigns():
    raw = [row("2026-08-07", "0", "PARAGUAS ONION"), row("2026-08-07", "7266308733410766", "OTRA")]
    payload = build_onion_mundial_payload(rows=OnionMundialRawRows(raw), from_date=date(2026,5,13), to_date=date(2026,8,25), updated_at=datetime.now(timezone.utc))
    assert all(all(day[1:] == [None, None, None, None, None] for day in rows)
        for rows in payload["groups"].values())


def test_ignores_rows_outside_the_defined_flight():
    raw = [row("2026-08-26", "1170894797052218", "EXPRESS_ONION", "JULIO_ONION_RETENCION")]
    payload = build_onion_mundial_payload(rows=OnionMundialRawRows(raw),
        from_date=date(2026, 5, 13), to_date=date(2026, 8, 27),
        updated_at=datetime.now(timezone.utc))
    assert sum((day[4] or 0) for day in payload["groups"]["expressOnion"]) == 0
