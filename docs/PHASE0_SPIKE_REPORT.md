# Phase 0 Spike Report — Shiplystic Lead Engine

**Date:** 2026-11-11 · **Plan:** [SHIPLYSTIC_LEAD_ENGINE_PLAN.md](SHIPLYSTIC_LEAD_ENGINE_PLAN.md)
**Scripts:** `scripts/spikes/s1_shopify_reviews.py`, `scripts/spikes/s2_resolve_and_extract.py`
**Raw outputs (contain phone numbers, gitignored):** `exports/spike_*.json`

All tests were read-only requests to public pages at a polite rate. No paid service was used.

---

## 1. Headline

1. **Contacts are easier to find than the plan assumed.** 78–81% of Indian Shopify stores publish a usable mobile number on their own site, against the 45% assumed in the plan.
2. **Finding stores is the real bottleneck.** The free sources that work give a one-time pool of roughly 2,000–2,500 stores, about 6–8 weeks of supply at 50 leads/day. Free search engines block automated discovery, so there is no free daily feed yet.
3. Therefore the daily funnel needs about **70 candidate stores/day, not 600**, but the engine must keep adding new stores after the first two months.

---

## 2. Results by test

### S1 — Shopify App Store reviews of Indian shipping apps

| Measure | Result |
|---|---|
| Apps with readable review pages | nimbuspost, ithink-logistics, shipmozo, xpressbees, shiprocket-engage (Shiprocket, Shipway, Delhivery main apps not found under guessed URLs) |
| Reviews collected | 177 (175 unique stores) |
| Indian stores | 175 of 175 (100%) |
| Reviews rated 1–3 stars | 39 (unhappy with a competitor) |
| Store name resolved to its domain | 139 (79%) |
| Indian store confirmed on resolution | 132 |
| **With a usable mobile number** | **107 (81% of resolved, 61% of all reviewers)** |
| With a WhatsApp number on the site | 47 |
| Of the mobile leads, from 1–3 star reviews | 35 |

How domains were resolved, at zero cost: guess `name.com/.in/.co.in/...` and accept only when Shopify's own `/meta.json` on that domain returns a matching store name.

**More review pools exist.** Indian-only apps with readable reviews: kwikpass (11 pages), cod-order-confirmation (3), vamaship (3), Cashfree, PhonePe, PayU. Global apps filtered to India: ParcelPanel (321 pages, about 1 in 10 reviewers Indian on page 1). Estimated further pool: 500–1,000 Indian stores. This estimate is not measured.

### S2 — Contact extraction and sizing

| Signal | Reviewer stores (132) | Random Indian Shopify stores (89) |
|---|---|---|
| Usable mobile number | 81% | 78% |
| WhatsApp number | 36% | 33% |
| GSTIN on site | 19% | 24% |
| Product count from `/meta.json` | available for all | available for all |
| Stores with 10–5,000 products | 99 | 78 |

"Usable mobile" means a correctly formatted Indian mobile, found on the store's own pages and not shared with any other store. It is **not yet proven live or the owner's**. WhatsApp numbers are the higher-confidence subset.

### S3 — Free search engines for discovery

| Engine | Result |
|---|---|
| DuckDuckGo | Blocked automated queries (HTTP 202 challenge) |
| Mojeek | Refused (HTTP 403) |
| Brave | Rate-limited (HTTP 429) on the first query |
| Yahoo | Error (HTTP 500) |
| Bing | Returns 10 results/page but ignores quoted phrases; returned dictionary sites for `"powered by shopify"` |

**Conclusion:** free search is not a workable discovery source at volume. A paid search API (for example Serper, about $50 for 50,000 queries) would replace it.

### S4 — Bulk domain lists

| Source | Result |
|---|---|
| Common Crawl URL index | Down during the test: HTTP 504 even for a single-domain query on two crawls. **Not measured; retry.** |
| Tranco top-1M list (free) | 11,559 `.in`/`.co.in` domains; 10% are Indian Shopify stores (31 of 300 and 89 of 900 sampled) → **about 1,150 stores** |

Not yet tested: Indian stores on `.com` domains within Tranco (a far larger list to probe), and WooCommerce stores.

---

## 3. Problems found that the build must handle

1. **Shared numbers.** 7 numbers appeared on several unrelated stores (one on 7 stores). These are theme, agency or app-vendor numbers. Rule: reject any number seen on more than one store.
2. **Competitor detection is over-broad.** A simple text match flagged 88 of 132 stores, mostly from footer text naming couriers. It must check script sources, tracking-page links and installed-app markers instead. Tier A tagging is not reliable until this is rebuilt.
3. **Large stores slip in.** 10 of 89 random stores list more than 5,000 products (likely marketplace-style or enterprise). Use product count as a tier signal.
4. **Name-to-domain guessing works only for Shopify** (it relies on `/meta.json`). WooCommerce and custom stores need another check.

---

## 4. Changes to the plan

| Plan item | Was | Now |
|---|---|---|
| Daily discovery needed for 50 leads | 600 domains | ~70 Indian store candidates |
| Mobile-found rate | 45% (assumed) | 78–81% (measured, before live-number check) |
| S3 free search | Week 2 source | **Dropped**; replaced by a paid search API or the Store Leads backfill |
| S4 Common Crawl | Week 3 backlog | Retry; Tranco used meanwhile |
| Week 1–2 supply | — | S1 reviews + Tranco `.in` pool (~2,000 stores) start immediately |
| Competitor fingerprint | Simple check | Rebuild with script and link detection before Tier A is trusted |
| Paid backfill timing | Week 6 | **Decision needed:** bring forward to about week 6 at the latest, since free supply lasts 6–8 weeks |

---

## 5. Decisions needed from the owner

1. **Free supply runs out in about 6–8 weeks.** Approve a paid discovery source (Serper ~₹4,400 once, or one month of Store Leads Pro ~₹22,000) by week 5, or accept a lower daily target after that.
2. **Start building now on the measured pool?** About 2,000 stores are ready to process, enough for the first weeks of Phase 1.
3. **Number verification.** A live-number check (HLR, paid, typically under ₹1/number) would confirm the 78–81% figure before callers spend time. Decide whether to test it on 100 numbers.
4. The other open decisions in plan section 12 still apply.
