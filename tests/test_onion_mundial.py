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
    # El flight ya no tiene largo fijo: cada serie corre desde su propio arranque hasta
    # `to_date` (aca, el mismo para las seis). Onion y Mundial arrancan en fechas distintas
    # -Mundial semanas antes que Onion-, asi que a igual `to_date` acumulan distinto numero
    # de dias: no es un error, es "dia de flight" contado desde el propio inicio de cada una.
    assert len(payload["groups"]["paraguasOnion"]) == 19
    assert len(payload["groups"]["paraguasMundial"]) == 105
    assert len(payload["groups"]["domicilioOnion"]) == 33
    assert len(payload["groups"]["domicilioMundial"]) == 104
    assert len(payload["groups"]["expressOnion"]) == 33
    assert len(payload["groups"]["expressMundial"]) == 104
    assert payload["groups"]["paraguasOnion"][0] == ["2026-08-07", 10.0, 2, 30.0, 1, 1]
    assert payload["groups"]["expressOnion"][0] == ["2026-07-24", None, None, None, None, None]
    assert payload["groups"]["expressOnion"][1] == ["2026-07-25", 10.0, 2, 30.0, 1, None]

def test_ignores_unknown_accounts_and_campaigns():
    raw = [row("2026-08-07", "0", "PARAGUAS ONION"), row("2026-08-07", "7266308733410766", "OTRA")]
    payload = build_onion_mundial_payload(rows=OnionMundialRawRows(raw), from_date=date(2026,5,13), to_date=date(2026,8,25), updated_at=datetime.now(timezone.utc))
    assert payload["groups"]["paraguasOnion"][0][1:] == [None, None, None, None, None]
    assert payload["groups"]["paraguasMundial"][0][1:] == [None, None, None, None, None]


def test_sigue_sumando_dias_despues_del_viejo_cierre_de_19_o_33_dias():
    """El flight ya no tiene fecha de cierre fija: mientras el ad set siga corriendo con el
    mismo nombre y pidamos un `to_date` mas alla del viejo largo (19/33 dias), esos dias nuevos
    deben contarse -antes se descartaban silenciosamente por 'terminado el flight'."""
    raw = [row("2026-08-26", "1170894797052218", "EXPRESS_ONION", "JULIO_ONION_RETENCION")]
    payload = build_onion_mundial_payload(rows=OnionMundialRawRows(raw),
        from_date=date(2026, 5, 13), to_date=date(2026, 8, 27),
        updated_at=datetime.now(timezone.utc))
    by_day = {day[0]: day for day in payload["groups"]["expressOnion"]}
    # El 25 sigue siendo el cierre aprobado del HTML (no lo pisa Windsor).
    assert by_day["2026-08-25"][4] == 46
    # El 26 ya no se descarta: es un dia nuevo del mismo flight, con datos frescos de Windsor.
    assert by_day["2026-08-26"][1:] == [10.0, 2, 30.0, 1, None]
    # El flight ahora llega hasta el `to_date` pedido (27), no se corta en el dia 33.
    assert payload["groups"]["expressOnion"][-1][0] == "2026-08-27"


def test_ignora_filas_de_antes_de_que_arranque_la_serie():
    """El unico limite que queda es el arranque propio de cada serie: una fila fechada antes de
    que ese ad set empezara a correr no debe contar como parte del flight (cada serie arranca un
    mes distinto, ver _classify)."""
    from app.onion_mundial import _is_flight_day
    assert _is_flight_day("expressOnion", date(2026, 7, 1)) is False
    assert _is_flight_day("expressOnion", date(2026, 7, 24)) is True
    assert _is_flight_day("expressOnion", date(2026, 12, 31)) is True  # sin techo


def test_preserves_the_approved_html_closing_rows():
    payload = build_onion_mundial_payload(rows=OnionMundialRawRows([]),
        from_date=date(2026, 5, 13), to_date=date(2026, 8, 25),
        updated_at=datetime.now(timezone.utc))
    assert payload["groups"]["paraguasOnion"][-1] == ["2026-08-25", 5.43, 3, 53.06, 1, 2]
    assert payload["groups"]["domicilioOnion"][-1] == ["2026-08-25", 57.8, 165, 2416.6, None, 99]
    assert payload["groups"]["expressOnion"][-1] == ["2026-08-25", 54.06, 83, 1114.43, 46, None]
