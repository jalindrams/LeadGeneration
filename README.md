# Micraft Growth Engine 🚀

**B2B Lead Generation & Revenue Engine for Micraft Solutions**

Automated pipeline to collect, enrich, score, and route manufacturing leads from IndiaMART and Google Maps.

## What's Built

**Phase 1 — Collection**
- ✅ FastAPI backend with REST API
- ✅ PostgreSQL database
- ✅ IndiaMART scraper (Playwright, stealth mode)
- ✅ Google Maps Places API scraper
- ✅ Multi-level deduplication (GST → Phone+Company → Fuzzy)
- ✅ Lead pipeline metrics tracking (yield tracker)
- ✅ CSV export for sales team

**Phase 2 — Enrichment & Scoring**
- ✅ ICP scoring engine (`app/processing/scorer.py`) — 100-point model, hot ≥70 / warm 40–69 / cold <40
- ✅ Qualification bar: ICP match + decision-maker (Plant/Factory/IT Manager, Owner, Director) + verified contact
- ✅ Enrichment waterfall (`app/enrichment/`): company website + IndiaMART profile → contact name, designation, email, GST
- ✅ Human Intelligence Queue auto-fill for good leads missing a decision-maker
- ✅ Data integrity audit (`scripts/audit_data_integrity.py`) — detects/quarantines synthetic leads

**Phase 3 — Revenue Engine**
- ✅ Hot Lead Trigger (`app/revenue/hot_trigger.py`) — WhatsApp (Twilio) / Slack / email, config-gated via `.env`
- ✅ Sales Feedback Loop — `POST /api/lead-feedback` rescoring leads on every call outcome
- ✅ Call feedback importer (`scripts/import_call_feedback.py`) for rep spreadsheets
- ✅ HubSpot batch sync (`app/integrations/hubspot.py` + `scripts/sync_hubspot.py`), config-gated
- ✅ Speed-to-Lead tracking — `GET /api/metrics/speed-to-lead`
- ✅ Source Performance Scoring — `scripts/compute_source_performance.py` + `GET /api/metrics/source-performance`

**Product Campaigns** — every scrape targets one Micraft product (`app/products.py` profiles drive queries, cities, decision-maker titles, turnover bands, and scoring):
- `mes` · `dms` · `tms` · `courier` · `calibration` · `ecom` (Shiplystic)

```bash
python scripts/run_scraper.py                        # interactive: asks which product
python scripts/run_scraper.py --product mes --yes    # MES campaign, profile defaults
python scripts/run_scraper.py --product tms --target 50 --city Mumbai
```

**Daily operation**
```bash
python scripts/run_scraper.py --product mes --yes       # collect (auto-scores + alerts + bad-phone blacklist)
python scripts/run_enrichment.py --limit 150            # enrich best candidates (websites + IndiaMART profiles)
python scripts/import_call_feedback.py <sheet.xlsx>     # import rep call outcomes
python scripts/compute_source_performance.py            # weekly
python scripts/sync_hubspot.py                          # after setting HUBSPOT_API_KEY
```

**Strategy:** see [docs/WORLD_CLASS_ENGINE.md](docs/WORLD_CLASS_ENGINE.md) — how this engine beats Apollo/Lusha for Indian SME B2B (feedback flywheel, GSTIN authenticity, product-aware ICP, freshness guarantee).

---

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ (or Docker)
- Google Maps API key (optional, for Google Maps scraper)

### Step 1: Install PostgreSQL

**Option A — Docker (recommended):**
```bash
docker-compose up -d
```

**Option B — Existing PostgreSQL:**
Create the database manually:
```sql
CREATE USER micraft WITH PASSWORD 'micraft_pass';
CREATE DATABASE micraft_leads OWNER micraft;
```

### Step 2: Create Virtual Environment

```bash
cd e:\Development\MicraftLeadGeneration
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### Step 4: Configure Environment

Edit `.env` file:
```env
DATABASE_URL=postgresql://micraft:micraft_pass@localhost:5432/micraft_leads
GOOGLE_MAPS_API_KEY=your_key_here   # Optional
```

### Step 5: Create Database Tables

```bash
python setup_db.py
```

Expected output:
```
✅ 6 tables created:
   • leads (30 columns)
   • scrape_jobs (12 columns)
   • lead_pipeline_metrics (12 columns)
   • lead_feedback (5 columns)
   • manual_review_queue (9 columns)
   • source_performance (15 columns)
```

### Step 6: Seed Test Data (Optional)

```bash
python scripts/seed_data.py
```

### Step 7: Start API Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Visit: **http://localhost:8000/docs** for API documentation.

---

## Running Scrapers

### Run All Scrapers (All Cities)
```bash
python scripts/run_scraper.py --source all --city all
```

### Run IndiaMART Only (Specific City)
```bash
python scripts/run_scraper.py --source indiamart --city Pune
```

### Run Google Maps Only
```bash
python scripts/run_scraper.py --source google_maps --city Mumbai
```

### Custom Search Query
```bash
python scripts/run_scraper.py --source indiamart --city Chennai --query "plastic injection molding"
```

### Limit Pages
```bash
python scripts/run_scraper.py --source indiamart --city Pune --max-pages 3
```

---

## Exporting Leads (CSV)

### Export All Leads
```bash
python scripts/export_csv.py
```

### Export with Filters
```bash
# Only leads with phone numbers
python scripts/export_csv.py --has-phone

# Only from IndiaMART, in Pune
python scripts/export_csv.py --source indiamart --city Pune

# Custom output path
python scripts/export_csv.py --output ./exports/sales_today.csv
```

### Export via API
```
GET http://localhost:8000/api/leads/export/csv?has_phone=true&city=Pune
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | System health check |
| `/api/leads` | GET | List leads (paginated, filterable) |
| `/api/leads/{id}` | GET | Get single lead |
| `/api/leads/stats` | GET | Lead statistics summary |
| `/api/leads/export/csv` | GET | Download leads as CSV |
| `/api/metrics/pipeline` | GET | Pipeline metrics (yield tracking) |
| `/api/metrics/summary` | GET | Aggregated summary |
| `/api/metrics/today` | GET | Real-time today's metrics |
| `/api/metrics/jobs` | GET | Recent scrape job history |

### Query Parameters for `/api/leads`
- `page`, `per_page` — pagination
- `source` — filter by source (indiamart, google_maps)
- `status` — filter by status (raw, enriched, qualified)
- `city` — filter by city name
- `has_phone` — only leads with phone (true/false)
- `has_email` — only leads with email
- `search` — search in company name, contact name, product
- `sort_by` — lead_created_at, score, company_name
- `sort_order` — asc, desc

---

## Project Structure

```
MicraftLeadGeneration/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Settings from .env
│   ├── database.py          # SQLAlchemy engine
│   ├── models.py            # 6 database tables
│   ├── schemas.py           # Pydantic schemas
│   ├── api/                 # REST API endpoints
│   │   ├── health.py
│   │   ├── leads.py
│   │   └── metrics.py
│   ├── scrapers/            # Data collection
│   │   ├── base.py          # Abstract scraper
│   │   ├── indiamart.py     # IndiaMART scraper
│   │   └── google_maps.py   # Google Maps API
│   ├── processing/          # Data processing
│   │   └── dedup.py         # Deduplication engine
│   └── utils/
│       ├── logger.py        # Structured logging
│       └── yield_tracker.py # Pipeline metrics
├── scripts/
│   ├── run_scraper.py       # Scraper CLI
│   ├── export_csv.py        # CSV export
│   └── seed_data.py         # Test data
├── setup_db.py              # Database initialization
├── docker-compose.yml       # PostgreSQL + Redis
├── requirements.txt
├── .env
└── .env.example
```

---

## Target ICP

| Field | Value |
|---|---|
| Industries | Automotive parts, Plastic molding, Fabrication |
| Company Size | 20–200 employees |
| Roles | Owner, Plant Head, Production Manager |
| Cities | Pune, Mumbai MMR, Chennai, Ahmedabad |

---

## Phase 1 Deliverables Checklist

- [x] Project setup (FastAPI + PostgreSQL)
- [x] Database schema (6 tables)
- [x] IndiaMART scraper
- [x] Google Maps Places API scraper
- [x] Deduplication (GST + Phone/Company + Fuzzy)
- [x] Lead storage with pipeline tracking
- [x] CSV export for sales team
- [x] API with docs at /docs
- [ ] Run first real scrape
- [ ] Export first CSV for Supritha
