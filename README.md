# KFC Dashboards Backend

FastAPI service for MKP One KFC dashboards. It proxies Windsor.ai from the server, stores snapshots, builds the dashboard payloads, and exposes authenticated and public-token views.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

By default the code can run with SQLite if `DATABASE_URL` is omitted. The included Docker setup runs the API with MariaDB.

## Run with Docker

```bash
docker compose up --build
```

The API will be available at:

```text
http://localhost:8030
```

The generated `.env` is configured for local/dev mode with `AUTH_DISABLED=true` and no Azure variables.

## Endpoints

- `GET /health`
- `GET /api/kfc-app-installs/dashboard?from=2025-12-29&to=2026-07-07`
- `POST /api/kfc-app-installs/refresh`
- `POST /api/kfc-app-installs/share`
- `DELETE /api/kfc-app-installs/share`
- `GET /api/public/kfc-app-installs/{shareToken}?from=2025-12-29&to=2026-07-07`
- `GET /api/kfc-mundial/dashboard?from=2026-06-11&to=2026-07-11`
- `POST /api/kfc-mundial/share`
- `DELETE /api/kfc-mundial/share`
- `GET /api/public/kfc-mundial/{shareToken}?from=2026-06-11&to=2026-07-11`
- `GET /api/kfc-martes-loco/dashboard?from=2026-04-07&to=2026-08-04`
- `POST /api/kfc-martes-loco/share`
- `DELETE /api/kfc-martes-loco/share`
- `GET /api/public/kfc-martes-loco/{shareToken}?from=2026-04-07&to=2026-08-04`
- `GET /api/kfc-onion-mundial/dashboard?from=2026-05-13&to=2026-08-25`
- `POST /api/kfc-onion-mundial/share`
- `DELETE /api/kfc-onion-mundial/share`
- `GET /api/public/kfc-onion-mundial/{shareToken}?from=2026-05-13&to=2026-08-25`

Private endpoints require `Authorization: Bearer <MSAL idToken>` and a role of `Planners` or `admin`.

## Windsor fields

The installs dashboard uses these fields:

- Meta Ads: `actions_mobile_app_install`
- TikTok Ads: `app_install`
- Google Ads: `biddable_app_install_conversions`

Google Ads intentionally never reads `conversions`.

The Mundial dashboard reads Meta Ads, Google Ads, and GA4 via Windsor.ai. Google Ads installs come from `biddable_app_install_conversions`; purchases and revenue come from GA4, except for the internal sheet override dates required by the dashboard contract.

The Martes Loco dashboard reads Meta Ads only (connector `facebook`), for the two accounts below, keeping only campaigns whose name contains `MARTES` (each campaign exists in an abril and an agosto version; both are summed per date+account):

- `7266308733410766` — Domicilio Martes Loco (`account key "A"`)
- `1170894797052218` — Martes Loco Express (`account key "P"`)

Fields fetched: `date, account_id, account_name, campaign, reach, spend, conversions_subscribe_mobile_app, conversions_start_trial_mobile_app, actions_omni_purchase, action_values_omni_purchase, purchase_roas_omni_purchase`. Cost-per-result, cost-per-purchase and ROAS are derived server-side (`spend ÷ result`, `spend ÷ purchases`, `value ÷ spend`) rather than trusted from the raw `purchase_roas_omni_purchase` field. The dashboard payload exposes a flat `rows` array shaped `[date, acct, reach, spend, subs, trials, purch, value]` per day+account, matching the reference dashboard's hardcoded `RAW` table.

The Windsor client also exposes `fetch_fields()` and `fetch_options()` helpers so field names can be checked with the configured API key.

The Onion vs Mundial dashboard reads Meta Ads from the APP and PYR KFC accounts. It classifies rows by campaign/ad-set tokens into Paraguas, Retención Domicilio and Retención Express, then compares Onion against Mundial by flight day. Snapshots and public sharing use their own database tables and follow the same behavior as the other KFC dashboards.

## Tests

```bash
pytest
```
