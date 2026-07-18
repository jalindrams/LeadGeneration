# Micraft Growth Engine — The World-Class Plan
### How we beat Apollo / Lusha / ZoomInfo at our own game

> Written 2026-07-19. Working doc — revise as feedback data accumulates.

---

## 1. Why Apollo & co. lose in our market (their lacunae)

| # | Their weakness | Why it matters for us |
|---|---|---|
| L1 | **India SME coverage is terrible.** Apollo/ZoomInfo index LinkedIn-visible, email-first, English-web companies. A 40-person plastic molder in Bhosari MIDC has no LinkedIn page and no one at a desk reading email. | Our entire ICP is invisible to them. |
| L2 | **Email-first, phone-last.** Their core asset is email + LinkedIn. Indian SME owners close deals on **phone and WhatsApp**. | We are phone-first by design. |
| L3 | **Stale by design.** Their contacts are crawled quarterly at best. People change roles; numbers die. Industry benchmarks put B2B data decay at ~30%/year. | Every lead we ship is re-scraped fresh (<14 days) with freshness decay in scoring. |
| L4 | **No feedback loop.** When an Apollo number is wrong, Apollo never finds out. You pay again for the same bad row. | Every rep call updates our data. Wrong numbers are **blacklisted forever** (127 already). "Not interested" sinks −40. This compounds: our data gets better every single day the team calls. |
| L5 | **No authenticity proof.** They can't tell you if a company legally exists today. | We validate **GSTIN check-digits offline** (mod-36 algorithm) — a lead with a verified GSTIN is a real, registered business. Roadmap: live GST portal status check (active/cancelled). |
| L6 | **Generic ICP.** One database for everyone; you filter it yourself. | Our engine scores **per product** (MES/DMS/TMS/Courier/Calibration/Ecom) — the same company scores 62 for TMS and 30 for MES. Nobody sells that. |
| L7 | **No intent signals for SMEs.** Their "intent" products track web content consumption by big companies. | Roadmap: India-specific intent — hiring for production/quality roles, new GST registrations, Udyam growth, NABL accreditation (compliance-driven demand for Calibration MS). |

**Positioning:** Apollo sells a phone book. We are building a **living, self-correcting revenue system** for Indian SME B2B, where every call makes the database smarter.

---

## 2. Our moats (built ✅ / building 🔨 / roadmap 🗺️)

1. ✅ **Feedback flywheel** — call outcomes rescore leads in real time (`POST /api/lead-feedback`); wrong numbers never re-enter (blacklist in scraper).
2. ✅ **Freshness guarantee** — leads scored down as they age; re-scrape cycle keeps data <14 days old.
3. ✅ **GSTIN authenticity** — offline check-digit validation; fabricated/mistyped GSTs earn nothing.
4. ✅ **Product-aware ICP scoring** — six product profiles drive queries, titles, turnover bands, scoring.
5. ✅ **Decision-maker extraction** — website + IndiaMART profile crawling for named Plant/Factory/IT Managers and Owners; human queue for the rest (automation 80%, Supritha 20%).
6. ✅ **Synthetic-data immunity** — deterministic audit catches fabricated records (learned the hard way).
7. 🔨 **Multi-source triangulation** — same company found via IndiaMART + Maps + website ⇒ +confidence (+3 today; expand to per-field provenance).
8. 🗺️ **India intent signals** (Phase 5, in priority order):
   - **NABL directory scraper** → every accredited lab is a warm Calibration MS lead (compliance need, public list, zero competition for this signal).
   - **Job-posting monitor** (Naukri/Indeed queries per city): hiring "production engineer"/"quality engineer" = growing factory = MES intent.
   - **Udyam/MSME registry** — employee counts, investment data (spec Phase 5 already).
   - **GST portal status check** — company active/cancelled, filing regularity = health signal.
9. 🗺️ **WhatsApp-first outreach** (Module 5 Tier 3) — hot leads get a WhatsApp intro before the call; Indian SME owners respond to WhatsApp 10x more than email.
10. 🗺️ **ML scoring** after 60 days of feedback (spec Phase 5) — train on our OWN outcome data; Apollo has no outcome data.

---

## 3. Product campaign playbook (which segment, how many)

**Recommended rollout order** (my call as your growth partner):

| Priority | Product | Why now | Daily scrape | Weekly qualified target |
|---|---|---|---|---|
| 1 | **MES** | Core product, 5 look-alike customers, deepest ICP data | 60 | 25–35 |
| 2 | **Calibration MS** | Compliance-driven demand + NABL public directory = cheap, high-fit leads; low competition | 25 | 10–15 |
| 3 | **TMS** | Big fragmented market, phone-first buyers, Google Maps coverage is strong | 40 | 15–20 |
| 4 | **DMS** | Dealerships are easy to find (Maps) but longer sales cycle | 40 | 15–20 |
| 5 | **Courier MS** | Smaller ticket; run monthly bursts, not daily | 30 | 10 |
| 6 | **Ecom (Shiplystic)** | Needs different sources (Shopify detection, Instagram sellers, ONDC) — build Phase 5 | 30 | 10 |

**Capacity math:** 2 reps × 50–60 calls/day ≈ 550/week. At current reach rates (~37%) you need ~200–250 *fresh qualified* leads/week to keep them fed — run MES daily + one secondary product per day, rotating.

**Turnover targeting:** sweet spots are configured per product (MES ₹10–500 Cr, Calibration ₹1–50 Cr, etc.) and applied as scoring bonus — not a hard filter, because turnover is unknown for most SMEs until enrichment/manual research fills it.

---

## 4. Operating cadence (daily)

```
06:30  python scripts/run_scraper.py --product mes --yes            (cron)
07:30  python scripts/run_scraper.py --product <rotating> --yes     (cron)
08:30  python scripts/run_enrichment.py --limit 150                 (cron)
09:00  Supritha: manual review queue (high priority first)
09:30  Reps: call hot list (score desc), log outcomes in calling UI
18:00  python scripts/sync_hubspot.py                               (when key set)
Sun    python scripts/compute_source_performance.py                 (weekly)
```

Every Friday: review source-performance recommendations (SCALE/MAINTAIN/REDUCE/KILL) and product funnel conversion — kill queries that produce junk, double the ones producing "interested".

---

## 5. Honest gaps (what would actually make us world-class)

1. **JustDial scraper** (spec Phase 2) — best phone coverage for services (TMS/Courier/Calibration); anti-bot is hard, needs care.
2. **IndiaMART logged-in scraping** — contact names/designations are richer behind login; needs a burner account strategy and ToS-risk acceptance.
3. **Truecaller-style phone validation** — pre-call name-match on numbers. No clean free API; evaluate paid per-lookup (₹0.1–0.5/number) once volume justifies.
4. **DND registry check** before calling (spec Phase 4, compliance).
5. **DPDP compliance layer** — opt-out endpoint + 12-month purge (spec Phase 4). Do this before scaling outreach.
6. **Grafana dashboards** on the existing metrics endpoints (spec had it; 1 day of work).
```
