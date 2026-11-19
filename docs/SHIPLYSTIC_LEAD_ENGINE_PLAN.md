# Shiplystic Lead Engine — Project & Development Plan

**Goal:** deliver 50 call-ready ecommerce seller leads every working day for Shiplystic.com (courier/shipping aggregation), on free sources first; then add a paid layer (₹10–25K/month) to reach 100 leads/day or 50 higher-quality leads/day.

**Audience:** the developer who will build it, and the owner who will approve decisions.
**Date:** 2026-11-11 · **Status:** Phases 0–4 built and tested locally on 2026-11-11 (not deployed). How to run it: [RUNBOOK.md](RUNBOOK.md).

---

## 1. Summary

1. The current tool cannot produce 50 ecommerce leads a day as built. Its Shiplystic source is a hand-typed list of 89 famous brands (Snitch, Bewakoof, mCaffeine) that are too large to switch courier partners on a cold call, and the list is exhausted in two days.
2. The fix is a discovery pipeline that finds small and mid-size Indian online stores in bulk, reads the contact details Indian law requires them to publish, and only releases a lead to the caller when it has a verified mobile number.
3. Five free sources can supply this. The strongest are stores that already use a competitor's shipping app (Shiprocket, Shipway, Delhivery, NimbusPost) and stores that publish a WhatsApp number on their site.
4. Target: 50 accepted leads/day by the end of week 3, on free sources only.
5. Paid phase (weeks 6–7): a guarded monthly budget of ₹10–25K. Recommended first purchase is one month of a store database (Store Leads) for a one-time bulk backfill of Indian stores, plus founder mobile lookups for the top-tier leads.
6. Stack: move the database to MS SQL now (about one developer-week). Do not rewrite the backend before leads are flowing. Rebuild the UI in React + Vite and the API in ASP.NET Core 10 in Phase 4, keeping the Python scrapers as background workers.

---

## 2. What exists today (analysed from the repository)

| Area | Finding |
|---|---|
| Backend | Python 3, FastAPI, SQLAlchemy, about 8,800 lines. **There is no Node.js in this project.** |
| Frontend | Server-rendered Jinja2 HTML templates (16 pages) with plain JS. **There is no React, Vite or Next.js.** |
| Database | PostgreSQL on a remote server. Tables: leads, scrape jobs, call logs, feedback, review queue, source performance, users, assignments. |
| Scrapers | IndiaMART, Google Maps (Places API, capped at 4,000 calls/month), TradeIndia, NABL, AIPMA, IBA transporters, OEM dealers, exhibition PDFs, D2C brands. |
| Working well | Per-product profiles, dedup, scoring, calling workboard, call feedback that rescores leads, wrong-number blacklist, fake-data audit, Places budget guard. |
| Hosting | Railway (web app only); scrapers run by hand on the owner's machine. |

### Why it is not an effective lead engine yet

| # | Problem | Evidence in code | Effect |
|---|---|---|---|
| 1 | No scalable ecommerce source | `app/scrapers/d2c_brands.py` uses 89 seed brands + one Startup India query | Cannot reach 50/day; wrong company size |
| 2 | Ecom profile searches the wrong market | `app/products.py` ecom queries are "garment manufacturer exporter", "cosmetics manufacturer" | Returns factories, not online sellers |
| 3 | Contacts are switchboard numbers | Contact pages give customer-care lines; no owner/founder resolution for ecom | Callers reach support staff, not decision makers |
| 4 | Scoring is built for manufacturers | `app/processing/scorer.py` rewards GST, turnover band, plant-manager titles | A good online store scores low |
| 5 | Nothing runs on its own | No scheduler; every scrape is a manual script | Lead flow stops when nobody runs it |
| 6 | "Lead" has no hard definition | A row with any email passes `is_qualified` | Volume looks fine, call outcomes are poor |
| 7 | No daily target tracking | Dashboards show totals, not "50 delivered today, per source" | Shortfalls are noticed late |

Problems 3, 5, 6 and 7 also explain the weak MES/DMS/Courier MS results. The fixes in this plan are built generically so those products benefit too (section 11).

---

## 3. Target customer and lead definition

### Who to call

| Tier | Profile | Why |
|---|---|---|
| **A — switchers** | Indian store already using a shipping aggregator or courier plugin; estimated 300–5,000 orders/month | Already ships at volume, understands the product, can compare rates the same day |
| **B — growing** | Live Shopify/WooCommerce store, 50–300 orders/month, runs ads or has active Instagram | Outgrowing manual booking; plugin install is a quick win |
| **C — new** | Store launched in the last 90 days, physical products, COD enabled | No partner locked in; low volume now |

**Exclude:** large brands with enterprise logistics contracts, digital-only products, stores not shipping from India, dead or password-protected stores, marketplaces themselves.

### An "accepted lead" (the only thing that counts toward 50/day)

All of these must hold:

1. Live store selling physical goods, shipping from India (INR prices, Indian address or GSTIN).
2. Platform identified: Shopify, WooCommerce, Magento, custom, or marketplace seller (Amazon/Flipkart).
3. At least one **Indian mobile number** (10 digits, starts 6–9), not a toll-free or shared agency number, found on the store's own site or confirmed by a second source.
4. Tier A, B or C assigned with the evidence stored (which signals, from which URL).
5. Not a duplicate (by domain, phone, GSTIN), not on the suppression list, not previously marked wrong number.

Nice to have, raises score: named owner/founder, WhatsApp number, competitor shipping tool detected, GSTIN, Instagram handle and follower count.

---

## 4. Free lead sources (Phase 1)

Ranked by expected quality. Yields are planning assumptions until the Phase 0 spikes measure them.

| # | Source | What it gives | How | Notes |
|---|---|---|---|---|
| S1 | **Shopify App Store reviews of shipping apps** | Store name + country for merchants who reviewed Shiprocket, Shipway, Delhivery, NimbusPost, iThink, ClickPost and similar | Crawl public review pages; keep India; resolve store name to domain | Low-star reviews are unhappy customers of a competitor: the hottest leads available. Same idea for WooCommerce plugin reviews on wordpress.org |
| S2 | **Competitor fingerprint on store sites** | Stores whose HTML loads a competitor's tracking page, widget or script | Fingerprint list maintained in config; checked during the crawl of every candidate | Turns any discovered store into a Tier A lead |
| S3 | **Search discovery** | Thousands of Indian store domains | Queries such as "powered by shopify" + category + city, "cash on delivery" + category, across 40 categories × 30 cities | Free search APIs are rate-limited; expect a few hundred new domains/day |
| S4 | **Web archive index (Common Crawl)** | Bulk one-time seed of `.in` and India-hosted domains with store URL patterns (`/collections/`, `/products/`, `/product-category/`) | Query the public URL index, no page downloads needed | One-time job giving a backlog of tens of thousands of candidates |
| S5 | **Newly registered domains** | Fresh stores (Tier C) | Daily free new-domain lists filtered by store keywords, then platform check | Lower quality; use as filler |
| S6 | **Marketplace sellers** (Amazon.in, Flipkart) | Seller legal name and address, which marketplaces must display | Category pages → seller profile → legal name → phone via GSTIN/website/Places | Fits the Amazon/Flipkart plugins. Marketplaces block scraping and their terms forbid it: build last, low volume, owner to accept the risk first |

### Getting the contact (applies to every source)

Indian ecommerce rules (Consumer Protection (E-Commerce) Rules, 2020) require every online seller to publish its legal name, address, customer-care contact and a named grievance officer. That makes the store's own site the authoritative source, the same principle that made the NABL directory work.

Extraction order per store:

1. `wa.me/91…` and `api.whatsapp.com/send?phone=` links. On small Indian stores this is usually the owner's own mobile.
2. `tel:` links and structured data (JSON-LD `telephone`).
3. Policy and contact pages: `/policies/contact-information`, `/policies/refund-policy`, `/pages/contact-us`, terms, privacy, shipping policy. Capture the grievance officer's name.
4. GSTIN in footer or policies → legal entity name → owner/director name from public company records.
5. Google Places lookup by legal name + city, inside the existing 4,000/month free cap, only for Tier A/B stores still missing a mobile.

Store sizing signals, all free: Shopify `/products.json` and `/meta.json` (product count, currency, last product update), WooCommerce store API, review-widget counts, presence of COD, ad pixels, Instagram link.

> **Phase 0 measured (2026-11-11):** mobile-found rate is 78–81%, but free search discovery is blocked and free store supply is about 2,000–2,500 stores. See [PHASE0_SPIKE_REPORT.md](PHASE0_SPIKE_REPORT.md); its numbers replace the assumptions below.

### Daily funnel needed for 50 accepted leads (assumptions to be measured)

| Stage | Per day | Assumed pass rate |
|---|---|---|
| Candidate domains discovered | 600 | — |
| Live Indian physical-goods store | 360 | 60% |
| Mobile number found | 160 | 45% |
| Passes tier + dedup + suppression | 65 | 40% |
| **Accepted and delivered** | **50** | buffer of 15 carried forward |

If the Phase 0 spikes show a lower mobile-found rate, raise discovery volume (S4 backlog makes this cheap) before anything else.

---

## 5. System design

```
 Discovery workers      Qualifier            Contact resolver       Verifier            Daily batch
 (S1..S6, scheduled) -> live? India?      -> site extraction     -> format, type,   ->  top 50 by score
                        platform, size       GSTIN, Places          cross-source,       assigned to callers
                        competitor tool                             dedup, suppression  07:30 every day
        |                                                                                    |
        +---------------- source yield + cost per accepted lead <---- call outcomes ---------+
```

### Components to build

| Component | Purpose | Reuses |
|---|---|---|
| Scheduler | Runs every stage daily without a person; retries; alerts on failure | New (APScheduler in the Python worker) |
| Candidate store | Queue of domains with state: discovered → qualified → contacted-resolved → accepted/rejected with reason | New tables |
| Discovery workers | One per source S1–S6, each resumable and rate-limited | `app/scrapers/base.py` |
| Qualifier | Platform detection, India check, size signals, competitor fingerprint | `detect_platform` in `d2c_brands.py` |
| Contact resolver | The five-step extraction above | `app/enrichment/website_extractor.py`, `places_budget.py` |
| Verifier | Mobile format and type, shared-number detection, cross-source agreement, confidence score | `app/processing/dedup.py` |
| Ecom scorer | New scoring model for stores (tier, signals, contact quality) | Product-aware hook in `scorer.py` |
| Daily batch | Picks the best 50, assigns to callers, records the shortfall if under 50 | `LeadAssignment`, workboard |
| Target dashboard | Today's delivered vs 50, funnel by source, cost per accepted lead, connect rate by source | Command Deck |
| Spend ledger | Hard monthly cap per paid provider, checked before every paid call | Generalises `places_budget.py` |
| Suppression list | Wrong numbers, do-not-call requests, opt-outs; checked before delivery | Existing blacklist |

### New data model (MS SQL)

| Table | Key columns |
|---|---|
| `stores` | domain (unique), platform, country, city, category, product_count, last_product_update, competitor_tool, tier, score, state, reject_reason |
| `store_signals` | store_id, signal_type, value, source_url, observed_at |
| `contacts` | store_id, name, role, phone, phone_type, email, whatsapp, source, source_url, confidence, verified_at |
| `source_runs` | source, started_at, discovered, qualified, accepted, cost_inr |
| `daily_batches` | date, product, target, delivered, shortfall_reason |
| `suppression` | phone/domain/email, reason, added_by, added_at |
| `spend_ledger` | provider, month, units, cost_inr, cap_inr |
| all tables | `tenant_id` from day one, so selling the tool later needs no schema rewrite |

Every contact keeps the URL it was read from. This is the safeguard against a repeat of the July 2026 fabricated-leads incident: a lead with no source URL cannot be accepted.

---

## 6. Technology decisions

### Database: move to MS SQL now

SQLAlchemy supports SQL Server through `pyodbc`, so the existing Python code keeps working with changes limited to the connection string, UUID columns, a few Postgres-specific queries and a one-time data copy. Estimate: 4–5 developer-days including testing. SQL Server Express is free up to 10 GB per database, which is enough for several years of lead data; a paid edition is only needed beyond that. Doing this first means the new tables are created once, in MS SQL.

### Frontend: React + Vite, not Next.js

This is a logged-in internal tool. It needs no search-engine indexing and no server rendering, which are the reasons to pay Next.js's extra complexity. A Vite single-page app is served as static files by the API at no extra hosting cost.

### Backend: ASP.NET Core 10, staged, and as Web API rather than MVC

| Option | Cost | Verdict |
|---|---|---|
| Rewrite everything in ASP.NET Core 10 now | About 6–8 developer-weeks with zero new leads; scraping libraries (Playwright, PDF parsing, fuzzy matching) are stronger in Python | Not recommended |
| Keep everything in Python forever | Zero | Fine technically, but does not match the team's .NET direction |
| **Staged hybrid (recommended)** | About 4 weeks, in Phase 4, after leads are flowing | ASP.NET Core 10 Web API + React for users, auth, leads, calling, dashboards. Python stays as scheduled workers writing to the same MS SQL database |

.NET 10 is a long-term-support release and free. With a React frontend, MVC views are redundant, so use Web API controllers. There is no Node.js to keep or migrate.

Licensing and hosting cost of the target stack: ₹0 in software licences (SQL Server Express, .NET 10, React, Vite). Hosting is one small Windows or Linux server; the developer should quote this against the current Railway bill.

---

## 7. Phases, deliverables and acceptance

Assumes one full-time developer plus about one hour a day from a reviewer/caller for feedback.

### Phase 0 — Spikes and decisions (3–4 days)

| Task | Output |
|---|---|
| Measure S1: crawl reviews of 5 shipping apps | Count of Indian stores, % resolvable to a domain |
| Measure contact extraction on 200 real Indian stores | % with a mobile number, % with a named person |
| Confirm Shopify `/meta.json` and `/products.json` availability on a 100-store sample | Go/no-go for sizing signals |
| Test 3 free search APIs for S3 volume | Domains/day achievable at ₹0 |
| Owner decisions (section 12) | Signed-off answers |

**Exit:** measured funnel rates replace the assumptions in section 4; plan volumes adjusted.

### Phase 1 — Free engine to 50/day (weeks 1–3)

| Week | Build | Acceptance |
|---|---|---|
| 1 | MS SQL migration; new tables; candidate store; scheduler; qualifier (platform, India, size, competitor fingerprint) | Existing app runs on MS SQL with all current data; 500 domains/day flow through the qualifier unattended |
| 2 | Sources S1, S2, S3; contact resolver steps 1–4; verifier; suppression list | 25+ accepted leads/day; every contact has a source URL |
| 3 | Source S4 backlog; Places fallback; ecom scorer; daily batch; target dashboard | **50 accepted leads delivered by 07:30 on 5 consecutive working days** |

### Phase 2 — Quality loop and calling workflow (weeks 4–5)

| Build | Acceptance |
|---|---|
| Call outcome codes specific to Shiplystic (connected, wrong number, not owner, already with X, interested, demo booked, signed up) | Every call logged with one tap |
| Outcomes feed source scoring: sources ranked by connect rate and interested rate, weak sources throttled automatically | Weekly source report generated without manual work |
| Caller screen shows store URL, platform, competitor tool, monthly-volume estimate and a suggested opening line | Caller needs no separate research per lead |
| WhatsApp intro message before the call for Tier A (existing WhatsApp module) | Sent only to numbers found on the store's own site; opt-out honoured |
| Sources S5 and, if approved, S6 | Buffer of 3+ days of accepted leads |
| Monitoring and alerts when a source breaks or the day's batch is short | Owner gets a message by 08:00 if delivery < 50 |

**Exit:** wrong-number rate under 15%; at least 30% of calls reach a person at the business.

### Phase 3 — Paid layer (weeks 6–7), ₹10–25K/month

Spend ledger first, with a hard cap that cannot be bypassed; then providers in the order of section 8.

**Exit:** 100 accepted leads/day, or 50/day where at least 60% carry a named owner's direct mobile; cost per accepted lead reported per provider.

### Phase 4 — Replatform and product readiness (weeks 8–13)

| Build | Notes |
|---|---|
| ASP.NET Core 10 Web API: auth, users, leads, calling, batches, dashboards | Python workers unchanged |
| React + Vite UI replacing the 16 Jinja pages | Workboard and dashboard first |
| Tenant isolation, roles, audit log, per-tenant source and budget settings | Uses the `tenant_id` columns already in place |
| Campaign configuration in the UI instead of `app/products.py` | Lets a non-developer add a product |
| Data-protection features: opt-out endpoint, retention/purge, export of a person's data | Required before selling to other companies |

**Exit:** second product (MES or Courier MS) running on the new stack as a separate campaign with no code change.

### Timeline

| Weeks | Phase | Result |
|---|---|---|
| 0 | Spikes | Measured funnel |
| 1–3 | Free engine | 50 leads/day |
| 4–5 | Quality loop | Lower wrong-number rate, self-tuning sources |
| 6–7 | Paid layer | 100/day or 50 premium/day |
| 8–13 | Replatform | React + ASP.NET Core 10, sellable foundation |

---

## 8. Paid phase budget

Prices below were checked on 2026-11-11 from third-party pricing summaries, not from each vendor's own page. Confirm on the vendor site before paying. Conversion assumed at about ₹88 per US dollar.

| Provider | What it adds | Price found | Fit |
|---|---|---|---|
| **Store Leads** | Database of 13M+ online stores with platform, country, installed apps (filter "India + uses Shiprocket app"), contact fields | Premium $75/mo (2,000 searches, no export); Pro $250/mo (export + API) | Best single purchase. Buy Pro for one month, export all Indian stores, cancel. Check its terms on keeping exported data |
| **EasyLeadz** | Direct mobile numbers of Indian founders | Startup plan about ₹2,417/mo billed yearly (about ₹29,000 upfront), 720 credits/year; sources disagree | For Tier A stores with no owner mobile. Yearly commitment: test on the free 5 credits first |
| **Google Places, paid overflow** | Phone lookup beyond the free cap | Place Details Enterprise $20 per 1,000 after 1,000 free; Text Search Pro $32 per 1,000 after 5,000 free | ₹2–4K buys roughly 1,000–2,000 more phone lookups a month |
| **Search API (Serper or similar)** | Removes the S3 discovery rate limit | About $50 for 50,000 queries | Cheap volume once free tiers are the bottleneck |
| **Apify** | Hosted scrapers for Instagram sellers and Meta ad advertisers | Starter $19/mo plus usage | Opens Instagram-first sellers, which free scraping cannot reach reliably |
| **Number validation (HLR)** | Confirms a mobile is live before the call | Typically well under ₹1 per number; quote needed | Cuts dead-number calls |
| **WhatsApp Business API** | Intro message before the call | About ₹0.86 per marketing message + GST | 1,500 messages ≈ ₹1,500/month |
| **Inbound ads test** | Sellers who ask to be called | Cost per lead unknown until tested | Different channel; run only as a small test |

### Recommended allocations

| Item | ₹10K/month | ₹25K/month |
|---|---|---|
| Store Leads | — (or Premium ₹6.6K for one month as a trial) | Pro, month 1 only: ₹22K |
| Search API | ₹2K | ₹2K |
| Places overflow | ₹3K | ₹3K (from month 2) |
| EasyLeadz | ₹2.5K equivalent | ₹6K tier from month 2 |
| Number validation + WhatsApp | ₹2.5K | ₹4K |
| Apify | — | ₹3K from month 2 |
| Inbound ads test | — | ₹5K from month 2 |

At ₹25K the first month is almost entirely the Store Leads backfill; from month 2 the same budget shifts to owner mobiles, validation and new channels. Every provider is kept only if its measured cost per *interested* lead beats the free sources.

---

## 9. Measures of success

| Metric | Target | When |
|---|---|---|
| Accepted leads delivered per working day | 50 | End of week 3 |
| Leads with source URL for the contact | 100% | Always |
| Wrong-number rate | < 15% | End of week 5 |
| Calls reaching a person at the business | ≥ 30% | End of week 5 |
| Interested / demo booked per 100 calls | Baseline in week 4, then improve monthly | Ongoing |
| Paid cost per accepted lead | Reported per provider | From week 7 |
| Days the batch ran with no manual step | 100% | From week 3 |

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Contact extraction finds fewer mobiles than assumed | Measured in Phase 0; the S4 backlog allows more discovery volume at no cost; paid lookups cover the top tier |
| Sources block or change layout | One worker per source, health check per run, alert on zero yield, several sources in parallel |
| Telemarketing rules (TRAI DND, commercial-call regulations) | Call only business numbers the store published; maintain suppression list; honour opt-outs immediately; get a legal opinion before scaling WhatsApp and calling volume |
| Personal data law (DPDP Act) | Store only business contact data with its public source URL; purge on request; full compliance features in Phase 4 before selling the tool |
| Marketplace terms forbid scraping (S6) | Built last, low volume, only with owner's written go-ahead |
| Paid spend overruns | Spend ledger with hard cap per provider, checked before each call |
| Fabricated or junk data re-enters | Source-URL rule; existing integrity audit run daily on new rows |
| Rewrite delays lead flow | Rewrite is Phase 4, after the engine is producing |

---

## 11. Carry-over to MES, DMS and Courier MS

Built once for Shiplystic, switched on per product by configuration:

- Scheduler, daily batch and target dashboard (each product gets its own daily target).
- Hard lead definition with a verified mobile and source URL.
- Verifier, suppression list and outcome-driven source ranking.
- Spend ledger, allowing paid owner-mobile lookups for the highest-scoring manufacturing leads.

Their sources stay as they are (AIPMA, NABL, IBA, IndiaMART, Maps).

---

## 12. Decisions needed from the owner

| # | Decision | Recommendation |
|---|---|---|
| 1 | Approve the lead definition in section 3 (mobile number mandatory) | Yes |
| 2 | Database: SQL Server Express on which server? | Same server class as today; developer to quote |
| 3 | Backend path: staged hybrid vs full rewrite now | Staged hybrid |
| 4 | Frontend: React + Vite | Yes |
| 5 | Marketplace seller scraping (S6) given the terms-of-service risk | Defer to Phase 2, decide then |
| 6 | Paid budget level and start date | Start at ₹10K in week 6; move to ₹25K for the Store Leads month if the trial shows good Indian coverage |
| 7 | Who calls, and how many callers (50 leads/day is about one full-time caller) | Name one owner for the daily batch |
| 8 | Legal review of calling and WhatsApp outreach | Before Phase 2 WhatsApp goes live |

---

## Price sources (checked 2026-11-11)

- Store Leads: https://coldiq.com/blog/storeleads-pricing · https://syncgtm.com/blog/store-leads-review-2026
- EasyLeadz: https://www.techjockey.com/detail/easyleadz · https://prospeo.io/s/easyleadz-pricing
- Google Places: https://developers.google.com/maps/billing-and-pricing/pricing
- WhatsApp Business API India: https://chatmaxima.com/whatsapp-api-pricing/india/ · https://whautomate.com/whatsapp-business-api-pricing-india
- Serper / Apify: https://costbench.com/software/web-scraping/serper/ · https://www.usagepricing.com/blueprint/activity/apify-2026-09-11-starter-plan-price-cut
