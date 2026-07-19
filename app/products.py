"""
Micraft Growth Engine - Product Campaign Profiles
Every scrape run targets ONE product. The product profile drives:
  - which search queries run (IndiaMART / Google Maps)
  - which industries count as ICP in scoring
  - which job titles count as decision-makers
  - which turnover band is the sweet spot
  - which cities to prioritize

Products: MES, DMS, TMS, Courier MS, Calibration MS, Ecommerce (Shiplystic).
"""

PRODUCT_PROFILES: dict[str, dict] = {
    "mes": {
        "name": "MES — Manufacturing Execution System",
        "pitch": "Shop-floor digitization for SME manufacturers",
        "search_queries": [
            "automotive parts manufacturer", "auto components manufacturer",
            "plastic injection molding company", "precision components manufacturer",
            "sheet metal fabrication", "forging company", "CNC machining company",
            "casting manufacturer",
        ],
        "icp_keywords": [
            "automotive", "auto part", "auto component", "auto ancillary",
            "seating", "axle", "gear", "brake", "clutch", "piston",
            "plastic", "mould", "mold", "injection", "polymer",
            "fabrication", "sheet metal", "forging", "casting", "machining",
            "precision engineering", "stamping", "cnc", "manufactur",
        ],
        "decision_makers": {
            "senior": ["plant head", "plant manager", "factory manager", "works manager"],
            "manager": ["production manager", "operations manager", "it manager", "it head",
                        "quality manager", "quality head"],
        },
        "turnover_band_crore": (10, 500),
        "cities": ["Pune", "Mumbai", "Chennai", "Ahmedabad", "Aurangabad", "Rajkot"],
        "daily_target": 60,
        "notes": "Core product. Look-alikes: TM Seatings, MSKH Seatings, Tata Autocomp, "
                 "Track Components, Geon Batteries — automotive-heavy.",
    },
    "dms": {
        "name": "DMS — Document Management System",
        "pitch": "Document control & digitization for compliance-bound and paper-heavy organizations",
        "search_queries": [
            "ISO certified manufacturer", "pharmaceutical manufacturer",
            "medical device manufacturer", "engineering design services",
            "EPC company", "diagnostic laboratory", "CA firm", "law firm",
        ],
        "icp_keywords": [
            # segment 1: compliance-bound (document control is MANDATED)
            "iso", "iatf", "gmp", "gxp", "certified", "pharma", "pharmaceutical",
            "medical device", "quality", "audit", "laboratory", "diagnostic",
            "calibration", "nabl",
            # segment 2: digitization-bound (paper-heavy operations)
            "engineering", "design", "epc", "consultant", "chartered accountant",
            "ca firm", "law", "legal", "advocate", "logistics", "documentation",
        ],
        "decision_makers": {
            "senior": ["quality head", "qa head", "management representative",
                       "admin head", "operations head", "director"],
            "manager": ["quality manager", "document controller", "it manager",
                        "admin manager", "office manager"],
        },
        "turnover_band_crore": (2, 300),
        "cities": ["Pune", "Mumbai", "Ahmedabad", "Chennai", "Hyderabad", "Vadodara"],
        "daily_target": 40,
        "notes": "Two buyer segments: (1) compliance-bound — ISO 9001/IATF/ISO 17025/GxP "
                 "companies where document control is mandated; NABL labs + certified AIPMA "
                 "manufacturers already in the DB are instant cross-sell pools. "
                 "(2) digitization-bound — paper-heavy offices: engineering/EPC, diagnostics, "
                 "CA/law firms, logistics (LR/POD paperwork).",
    },
    "tms": {
        "name": "TMS — Transport Management System",
        "pitch": "Fleet, trip & freight management for transporters",
        "search_queries": [
            "transport company", "logistics company", "fleet owners",
            "freight forwarders", "truck transport services",
            "cold chain logistics", "container transport services",
        ],
        "icp_keywords": [
            "transport", "logistics", "fleet", "freight", "trucking", "carrier",
            "cargo", "cold chain", "container", "roadways", "movers",
        ],
        "decision_makers": {
            "senior": ["fleet manager", "transport manager", "operations head"],
            "manager": ["operations manager", "logistics manager", "it manager", "dispatch manager"],
        },
        "turnover_band_crore": (5, 200),
        "cities": ["Mumbai", "Pune", "Chennai", "Ahmedabad", "Nagpur", "Indore"],
        "daily_target": 40,
        "notes": "Phone-first industry; owners often drive operations directly.",
    },
    "courier": {
        "name": "Courier MS — Courier Management System",
        "pitch": "Booking, tracking & billing for courier companies",
        "search_queries": [
            "courier services", "courier company", "express parcel services",
            "domestic courier services", "logistics courier franchise",
            "last mile delivery company",
        ],
        "icp_keywords": [
            "courier", "parcel", "express", "delivery", "last mile", "logistics",
            "cargo", "shipment",
        ],
        "decision_makers": {
            "senior": ["operations head", "branch head"],
            "manager": ["operations manager", "branch manager", "it manager", "hub manager"],
        },
        "turnover_band_crore": (1, 50),
        "cities": ["Mumbai", "Pune", "Ahmedabad", "Chennai", "Delhi", "Bengaluru"],
        "daily_target": 30,
        "notes": "Fragmented market — franchises and regional players; smaller ticket size.",
    },
    "calibration": {
        "name": "Calibration MS — Calibration Management System",
        "pitch": "Instrument calibration scheduling, certificates & NABL compliance",
        "search_queries": [
            "calibration services", "calibration laboratory", "NABL accredited laboratory",
            "instrument calibration services", "testing laboratory",
            "measuring instrument calibration",
        ],
        "icp_keywords": [
            "calibration", "nabl", "testing lab", "laboratory", "metrology",
            "instrument", "gauge", "inspection",
        ],
        "decision_makers": {
            "senior": ["lab head", "technical manager", "quality head"],
            "manager": ["quality manager", "lab manager", "it manager"],
        },
        "turnover_band_crore": (1, 50),
        "cities": ["Pune", "Mumbai", "Chennai", "Ahmedabad", "Bengaluru", "Vadodara"],
        "daily_target": 25,
        "notes": "Niche but high-fit: NABL labs MUST manage calibration records — compliance-driven demand. "
                 "NABL's public directory of accredited labs is a high-quality free source (Phase 5 scraper).",
    },
    "ecom": {
        "name": "Ecommerce — Shiplystic",
        "pitch": "Shipping aggregation for D2C brands & online sellers",
        "search_queries": [
            "garment manufacturer exporter", "handicraft manufacturer exporter",
            "cosmetics manufacturer", "food products manufacturer",
            "home decor manufacturer", "ayurvedic products manufacturer",
        ],
        "icp_keywords": [
            "export", "d2c", "online", "ecommerce", "brand", "garment", "apparel",
            "cosmetic", "handicraft", "food product", "ayurvedic", "home decor",
        ],
        "decision_makers": {
            "senior": ["founder", "co-founder"],
            "manager": ["ecommerce manager", "operations manager", "supply chain manager"],
        },
        "turnover_band_crore": (0.5, 20),
        "cities": ["Mumbai", "Delhi", "Jaipur", "Surat", "Bengaluru", "Ahmedabad"],
        "daily_target": 30,
        "notes": "IndiaMART/Maps only partially cover D2C. Better sources (Phase 5): Shopify site "
                 "detection, Instagram sellers, marketplace seller directories, ONDC registry.",
    },
}


def get_profile(product_key: str) -> dict:
    key = (product_key or "").strip().lower()
    if key not in PRODUCT_PROFILES:
        raise KeyError(
            f"Unknown product '{product_key}'. Valid: {', '.join(PRODUCT_PROFILES)}")
    return PRODUCT_PROFILES[key]


def product_menu() -> str:
    """Interactive product picker for CLI runs."""
    keys = list(PRODUCT_PROFILES)
    print("\nWhich product is this scrape for?")
    for i, k in enumerate(keys, 1):
        p = PRODUCT_PROFILES[k]
        band = p["turnover_band_crore"]
        print(f"  {i}. {p['name']}")
        print(f"      target: Rs.{band[0]}-{band[1]} Cr turnover | {p['daily_target']} leads/day | "
              f"{', '.join(p['cities'][:4])}")
    while True:
        choice = input(f"\nEnter 1-{len(keys)} (or product key): ").strip().lower()
        if choice.isdigit() and 1 <= int(choice) <= len(keys):
            return keys[int(choice) - 1]
        if choice in PRODUCT_PROFILES:
            return choice
        print("Invalid choice, try again.")
