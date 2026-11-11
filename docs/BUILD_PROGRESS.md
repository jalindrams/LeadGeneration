# Overnight Build Progress

Worktree: `E:\Development\MicraftLeadGeneration\.claude\worktrees\shiplystic-lead-generation-plan-a6442f`
Python: `E:\Development\MicraftLeadGeneration\venv\Scripts\python.exe` (run from the worktree root)
Plan: [SHIPLYSTIC_LEAD_ENGINE_PLAN.md](SHIPLYSTIC_LEAD_ENGINE_PLAN.md) · Measured inputs: [PHASE0_SPIKE_REPORT.md](PHASE0_SPIKE_REPORT.md)

## Owner decisions (2026-11-11, before sleeping)
- Database: local SQL Server Express only (`.\SQLEXPRESS`, DB `MicraftLeads`, Windows auth). Production Postgres is read-only source (`PG_SOURCE_URL`).
- Marketplace S6: build, low volume.
- Git: commit per phase on this branch; do not push.
- Phase 4: full replacement of all 16 pages (ASP.NET Core 10 Web API + React/Vite).
- Never: purchases, outbound messages, enabling paid providers.

## Status
| Step | State | Notes |
|---|---|---|
| Phase 0 spikes | done | report written |
| 1a MS SQL support | in progress | models made SQL Server-compatible (Uuid, Unicode, filtered unique index); `.env` points at local SQL Server; Places counter shared with main checkout via `PLACES_USAGE_FILE`; DB created; connection verified. Next: write + run `scripts/migrate_pg_to_mssql.py` |
| 1b store pipeline tables, scheduler, qualifier | pending | |
| 1c sources, resolver, verifier, scorer, daily batch | pending | |
| 2 outcomes, source ranking, alerts, S5/S6 | pending | |
| 3 spend ledger + paid providers (disabled) | pending | |
| 4 ASP.NET Core 10 API | pending | |
| 4 React + Vite UI (all pages) | pending | |
| Final verification + report | pending | |
