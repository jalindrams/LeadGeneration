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
| 1a MS SQL support | done | all 39 GET routes + writes verified on MS SQL; 8,323 leads copied; RCSI enabled on DB (needed for parallel workers) |
| 1b store pipeline tables, scheduler, qualifier | done | app/pipeline/*, scripts/run_pipeline.py, scripts/pipeline_worker.py, run_pipeline_worker.bat |
| 1c sources, resolver, verifier, scorer, daily batch | done | live run: tranco_in 148 stores -> 130 accepted; first batch 50/50 delivered (21 A, 29 B); 14 tests pass. commoncrawl still HTTP 504; tranco_com 0/1500 top .com; new_domains 2/159 |
| 2 outcomes, source ranking, alerts, S5/S6 | done | outcome codes + sync to suppression, ranking with auto quota multipliers, caller opener line, WhatsApp intro QUEUE (never sends), alerts log-only unless PIPELINE_ALERTS_ENABLED. S6 built but Amazon serves a bot-challenge page (not bypassed) |
| 3 spend ledger + paid providers (disabled) | pending | |
| 4 ASP.NET Core 10 API | pending | |
| 4 React + Vite UI (all pages) | pending | |
| Final verification + report | pending | |
