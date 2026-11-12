# Shiplystic Lead Engine — Runbook

How to run, operate and extend what was built from [SHIPLYSTIC_LEAD_ENGINE_PLAN.md](SHIPLYSTIC_LEAD_ENGINE_PLAN.md).
Build log: [BUILD_PROGRESS.md](BUILD_PROGRESS.md) · Measured inputs: [PHASE0_SPIKE_REPORT.md](PHASE0_SPIKE_REPORT.md)

## 1. What runs where

```
 Python workers (app/pipeline, scripts/)      ASP.NET Core 10 API (web/Api)        React + Vite UI (web/client)
 discover -> qualify -> resolve -> accept     auth, leads, calling, admin,          built into web/Api/wwwroot,
 daily batch, outcome sync, ranking,  <---->  pipeline, outreach, settings  <----> served by the API on :5080
 paid sources (off by default)                starts Python jobs from a whitelist
                     \                              /
                      +----- MS SQL (SQL Server Express, DB MicraftLeads) ----+
```

The Python FastAPI app (`app/main.py`, Jinja pages) still works against MS SQL and can be retired once the team uses the new UI.

## 2. First-time setup (one PC or server)

1. **SQL Server Express** with Windows login. Create the database and turn on row versioning (needed for parallel workers):
   ```
   sqlcmd -S .\SQLEXPRESS -E -Q "CREATE DATABASE MicraftLeads; ALTER DATABASE MicraftLeads SET READ_COMMITTED_SNAPSHOT ON;"
   ```
2. **Python**: `pip install -r requirements.txt -r requirements-scrape.txt`. In `.env` set
   `DATABASE_URL=mssql+pyodbc://@localhost\SQLEXPRESS/MicraftLeads?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes`
   (see `.env.example` for every key).
3. **Tables and data**: `python scripts/run_pipeline.py init`, then copy the old Postgres data once (read-only on the source):
   `PG_SOURCE_URL=<old postgres url> python scripts/migrate_pg_to_mssql.py`
4. **API + UI**: edit `web/Api/appsettings.json` (connection string, `Python:Exe`, `Python:WorkDir`), then
   ```
   cd web/client && npm install && npm run build
   cd ../Api && dotnet run
   ```
   Open http://localhost:5080. Users and passwords are the existing ones (bcrypt hashes are reused).
5. **Always-on worker**: register `run_pipeline_worker.bat` in Windows Task Scheduler, trigger "At log on", "Start in" = project folder.

## 3. Daily schedule (scripts/pipeline_worker.py)

| Time | Job |
|---|---|
| 05:15 | Discovery from every enabled source |
| 06:40–22:40 hourly | Process backlog: qualify → resolve contacts → accept |
| 07:30 | Build today's batch of 50, assign round-robin to active sales reps, alert if short |
| 07:45 | Queue WhatsApp intros for Tier A (queued only; a person sends them from the Outreach page) |
| hourly :05 | Apply call outcomes: wrong number / do-not-call go to the suppression list; leads rescored |
| Sun 21:10 | Rank sources from call outcomes; weak sources get smaller discovery quotas |

Manual equivalents: `python scripts/run_pipeline.py daily | discover --source X | process | batch | status | rank | sync-outcomes | spend`.

## 3b. Calling (for callers)

Open **Start calling** (`/call`). It shows one lead at a time: due follow-ups first, then new leads by score, then
no-answer retries (3 hours after the last try, up to 4 tries). Tap the green number to dial, tap what happened (keys 1–0),
tap a reason, and press **Save & next lead** (Ctrl+Enter). When a caller's own list is empty, the next unassigned lead is
claimed for them automatically; the claim is atomic, so two callers never get the same lead. A double-tapped save is
logged once. If the network drops, the entry stays on screen until it is saved.

## 4. What a lead must have to be delivered

Indian store, physical goods, a 10-digit Indian mobile found on the store's own pages (or Places / a paid source) with
the URL it came from, the number not shared with any other store, not suppressed, not a known wrong number, not a
duplicate. Tier A = uses or reviewed a competitor shipping tool and has 10–5,000 products; B = growing; C = the rest.

## 5. Sources

| Source | Status on 2026-11-11 (local run) |
|---|---|
| `shopify_app_reviews` | Best: 278 Indian stores found, 221 accepted. Finite pool; new reviews arrive slowly. |
| `tranco_in` | 148 stores per 2,500 domains probed, 130 accepted. ~11,500 `.in` domains in total. |
| `tranco_com` | 0 Indian stores in the top 1,500 `.com`; deeper ranks untested. |
| `new_domains` | 2 accepted of 159 processed; filler only. |
| `commoncrawl` | Index returned HTTP 504 all night; fails soft and retries daily. |
| `amazon_sellers` (S6) | Amazon serves a bot-challenge page; the source stops at once and never bypasses it. |
| `serper_search`, `storeleads` | Paid, off until a key and a cap are set. Store Leads endpoint follows its docs but is untested without a key. |

Free supply estimate: about 6 days of accepted leads are ready now (303), plus ~11,000 unprobed Tranco `.in` domains.
Expect the free pool to run low within weeks; that is when the paid phase (plan section 8) starts.

## 6. Turning on paid sources

In Settings (or `.env`): set `PAID_TOTAL_CAP_INR` and the provider cap, e.g. `PAID_SERPER_CAP_INR=4000`, plus its API key.
Every paid call is checked against the ledger first and refused once a cap would be exceeded (`python scripts/run_pipeline.py spend`).
Bought owner mobiles (EasyLeadz etc.) are imported as CSV: `python scripts/run_pipeline.py import-contacts --file x.csv --provider easyleadz --cost 40`.
Places beyond the free 4,000 calls/month stays off unless `PAID_GOOGLE_PLACES_CAP_INR` > 0.

## 7. Tests

```
python -m pytest tests                          # 27 tests, pipeline logic + stages on fake pages
cd web/Api.Tests && dotnet test                 # 11 integration tests against MicraftLeads_Test
cd web/client && npm run lint && npm run build
```
The .NET tests need the `MicraftLeads_Test` database with the schema created by the Python models:
`DATABASE_URL=<...MicraftLeads_Test...> python -c "from app.pipeline.runner import ensure_tables; ensure_tables()"`.

## 8. Known gaps (not built or not verified)

- Not deployed anywhere; everything ran on the owner's PC against a local copy of the data. Production Postgres was only read.
- Live-number check (HLR) not built: no provider chosen.
- WhatsApp intros are queued, never sent by the system; alerts are log-only until `PIPELINE_ALERTS_ENABLED=true`.
- Multi-tenant: new tables carry `tenant_id`, but the old tables, auth and UI are single-tenant (Phase 4 plan item).
- Data-protection features (opt-out endpoint, retention purge) not built; the suppression list covers do-not-call.
- Settings "test WhatsApp/email" buttons from the old app were not ported (they send real messages).
- No call has been made from these leads yet, so connect and interest rates are unknown.
