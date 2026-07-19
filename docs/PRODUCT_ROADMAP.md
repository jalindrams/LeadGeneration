# Micraft Lead Engine — Product Roadmap
### Phase 1: MICRAFT (internal weapon) → Phase 2: WORLD (sellable product)

**Positioning we are building toward:** *"The phone-first, WhatsApp-first B2B lead engine
for India — with government/association-verified data Apollo doesn't have."*

Why we win: Apollo/ZoomInfo/Lusha are US-centric, email-first, $-priced, and thin on
Indian SMEs. Our moats: (1) authoritative directory data (NABL/AIPMA/IBA/OEM — verified
at the source), (2) call-verified phone flywheel (every rep call outcome improves the
data), (3) product-aware ICP scoring, (4) India-native outreach: WhatsApp + call, not
cold email.

---

## PHASE 1 — MICRAFT (Weeks 1–6)
Goal: every Micraft product (MES, DMS, TMS, Courier MS, Calibration MS) has a complete
pipeline: **source → score → sequence → call → close**, fully measured.

### 1.1 Outreach layer (Weeks 1–2)
- **WhatsApp Business Cloud API** (Meta direct — no BSP markup): template messages with
  merge fields; opt-out handling; delivery/read/reply webhooks into the lead timeline.
  Cost: ~₹0.8/marketing conversation.
- **Email**: Amazon SES + domain warm-up + DKIM/SPF (~₹8 per 1,000 mails); sequences
  with open/click tracking.
- **Smart Templates**: per product × segment × funnel-stage matrix. Templates pull
  data hooks we uniquely have: *"Your NABL accreditation renews in March — is your
  document control audit-ready?"* Template performance (reply %) tracked per variant.

### 1.2 Sequencer (Weeks 2–3)
- Cadence engine: e.g. Day 0 WhatsApp → Day 1 call task on rep workboard → Day 3
  email → Day 5 WhatsApp follow-up → Day 8 call. Stop-on-reply / stop-on-interested.
- Per-product playbooks; hot leads jump the queue (alerts already built — activate
  Twilio/Slack creds).

### 1.3 Data completion (Weeks 3–4)
- Title-gap fix: treat NABL/IBA directory contacts as decision-makers (they are) —
  ~5,000 leads become hot-eligible instantly.
- Retag 1,473 NABL medical labs → calibration; DMS cross-sell list from NABL + AIPMA.
- GSTIN → turnover band enrichment (free GST portal lookups; optional Karza/Signzy
  API ~₹2–4/lookup for scale).
- LinkedIn title-verification queue for top-500 accounts (manual, rep-assisted).

### 1.4 Intent engine (Week 4) — our unfair advantage
- Renewal-window campaigns: call NABL labs 90 days before accreditation expiry;
  IBA operators before recommendation validity lapses. Renewal = compliance budget
  moment. No competitor has these dates.
- New-entry alerts: fresh NABL/AIPMA/IBA registrations = new company setting up
  processes = perfect timing.

### 1.5 Command deck (Week 5)
- Per-product funnel (sourced → qualified → contacted → interested → won), source ROI,
  rep leaderboard, speed-to-lead, template win-rates, wrong-number rate.

### 1.6 Automation (Week 6)
- Windows Task Scheduler: nightly harvest refresh, morning auto-assignment + call
  lists per rep. HubSpot sync live (Private App token).

**Phase 1 budget:** ~₹15–30k/month (WhatsApp conversations + SES + optional GST API).
**Phase 1 KPIs:** connect rate >40%, wrong-number rate <5%, meetings/week per rep,
cost per qualified meeting per product.

---

## PHASE 2 — WORLD (Months 3–9)
Goal: multi-tenant SaaS. Wedge = vertical data packs + India-native outreach at
₹-pricing vs Apollo's $49–99/seat.

### 2.1 Multi-tenant core (Months 3–4)
- Workspaces, RBAC, tenant data isolation, Razorpay + Stripe billing, self-serve
  onboarding.
- **ICP Builder UI**: generalize `app/products.py` — any customer defines their own
  product profiles (queries, keywords, decision-makers, turnover band); the scoring
  engine is already product-aware. This is the product's brain, exposed.

### 2.2 Compliance before commerce (Month 4) — non-negotiable
- DPDP Act 2023: consent & purpose records, data-principal rights, deletion workflows.
- TRAI/DND compliance for voice, WhatsApp Business policy, opt-out ledger, audit trail.

### 2.3 Platform hardening (Months 4–5)
- Managed Postgres + backups, Celery/Redis job queue for harvests, proxy pool,
  object storage for exports, observability (uptime, scrape health, queue depth),
  security audit (auth hardening, secrets vault, pen test), CI/CD + staging env.

### 2.4 Collective verification flywheel (Months 5–6)
- Every tenant's call outcomes feed shared phone-verification flags
  ("call-verified <90 days ago") and the wrong-number blacklist.
  Data quality compounds with usage — the moat deepens with every customer.

### 2.5 GTM (Month 6+)
- Freemium directory browser (limited contact reveals) → paid seats ₹1,999–4,999/user/mo.
- Vertical data packs as SKUs: Labs, Plastics, Transporters, Dealers, Pharma, EPC.
- Case study = ourselves: "We built this to sell MES. Here are our numbers."
- Channels: industry associations (AIPMA-style partnerships), CA/consultant referral
  network, vertical landing pages + SEO.

**Phase 2 budget:** infra ₹30–60k/month + WhatsApp at cost + 1–2 engineers/agency.
**Phase 2 KPIs:** 10 design partners by M6, ₹10L ARR by M9, logo churn <3%/mo.

---

## Build order (next 4 actions)
1. Title fix + medical retag + DMS cross-sell list (1 day — unlocks ~5,000 hot-eligible leads)
2. WhatsApp Cloud API + template engine (week 1)
3. Sequencer + per-product playbooks (week 2)
4. Command deck dashboard (week 3)
