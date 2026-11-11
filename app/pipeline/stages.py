"""
Pipeline stages operating on the `stores` table.

  add_candidates  -> state=discovered
  qualify_store   -> qualified | rejected   (platform, India, size, competitor tools)
  resolve_store   -> resolved  | rejected   (contacts from the store's own pages)
  accept_store    -> accepted  | rejected   (hard bar, scoring, creates a Lead row)
  build_daily_batch -> delivered            (top N to callers, records shortfall)
"""
from datetime import datetime, date, timezone
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lead, User, LeadAssignment
from app.pipeline import fetch
from app.pipeline.extract import extract_contacts, extract_gstin
from app.pipeline.models import Store, StoreContact, StoreSignal, Suppression, DailyBatch
from app.pipeline.qualify import detect_platform, detect_competitors, looks_indian
from app.pipeline.scoring import score_store
from app.pipeline.verify import accept_check, normalize_mobile
from app.processing.dedup import compute_dedup_hash
from app.utils.logger import get_logger

log = get_logger("pipeline")

CONTACT_PATHS = {
    "shopify": ["/policies/contact-information", "/pages/contact-us", "/pages/contact",
                "/policies/refund-policy", "/policies/shipping-policy", "/policies/terms-of-service"],
    "woocommerce": ["/contact-us/", "/contact/", "/refund-policy/", "/terms-and-conditions/",
                    "/privacy-policy/", "/shipping-policy/"],
    None: ["/contact-us", "/contact", "/pages/contact-us", "/terms", "/refund-policy"],
}
PHONE_RANK = {"whatsapp": 0, "tel_link": 1, "jsonld": 2, "paid": 3, "places": 4, "page_text": 5}
MAX_ATTEMPTS = 3


def clean_domain(raw: str) -> str:
    raw = (raw or "").strip().lower()
    if "://" not in raw:
        raw = "https://" + raw
    host = urlparse(raw).netloc.split(":")[0]
    return host[4:] if host.startswith("www.") else host


# ---------------------------------------------------------------- discover
def add_candidates(db: Session, items: list[dict], source: str, product: str = "ecom") -> int:
    """items: {domain, name?, source_ref?, note?, rating?, platform?}. Returns new count."""
    new = 0
    existing = set()
    domains = [clean_domain(i.get("domain", "")) for i in items]
    for chunk in [domains[i:i + 500] for i in range(0, len(domains), 500)]:
        existing |= {d for (d,) in db.execute(
            select(Store.domain).where(Store.product == product, Store.domain.in_(chunk)))}
    for item, dom in zip(items, domains):
        if not dom or "." not in dom or dom in existing:
            continue
        existing.add(dom)
        s = Store(product=product, domain=dom, name=item.get("name"), source=source,
                  source_ref=item.get("source_ref"), source_note=item.get("note"),
                  platform=item.get("platform"), city=item.get("city"))
        db.add(s)
        db.flush()
        for ph in item.get("paid_phones") or []:
            p = normalize_mobile(ph)
            if p:
                db.add(StoreContact(store_id=s.id, phone=p, phone_type="paid", source=source,
                                    source_url=f"{source} record for {dom}", confidence=70))
        if item.get("rating") is not None:
            db.add(StoreSignal(store_id=s.id, signal_type="review_rating",
                               value=str(item["rating"]), source_url=item.get("source_ref")))
        new += 1
    db.commit()
    return new


def _reject(store: Store, reason: str):
    store.state = "rejected"
    store.reject_reason = reason
    store.checked_at = datetime.now()


# ---------------------------------------------------------------- qualify
def qualify_store(db: Session, store: Store) -> str:
    store.attempts = (store.attempts or 0) + 1
    if store.platform == "marketplace":   # Amazon.in seller: India-only marketplace, no site
        store.country, store.currency = "India", "INR"
        store.state, store.checked_at = "qualified", datetime.now()
        db.commit()
        return store.state
    status, html, final = fetch.get(f"https://{store.domain}/", timeout=12)
    if status != 200 or len(html) < 300:
        if store.attempts >= MAX_ATTEMPTS:
            _reject(store, f"unreachable_{status}")
        db.commit()
        return store.state
    final_dom = clean_domain(final)
    if final_dom and final_dom != store.domain:
        clash = db.execute(select(Store.id).where(Store.product == store.product,
                                                  Store.domain == final_dom)).first()
        if clash:
            _reject(store, "duplicate")
            db.commit()
            return store.state
        store.domain = final_dom

    platform = detect_platform(html) or store.platform
    meta = None
    if platform == "shopify" or "shopify" in html.lower():
        meta = fetch.get_json(f"https://{store.domain}/meta.json")
        if isinstance(meta, dict) and "myshopify_domain" in meta:
            platform = "shopify"
            store.name = store.name or meta.get("name")
            store.currency = meta.get("currency")
            store.country = meta.get("country")
            store.city = meta.get("city") or store.city
            pc = meta.get("published_products_count")
            store.product_count = pc if isinstance(pc, int) else None
            prods = fetch.get_json(f"https://{store.domain}/products.json?limit=5")
            if isinstance(prods, dict) and prods.get("products"):
                stamps = [p.get("updated_at") for p in prods["products"] if p.get("updated_at")]
                if stamps:
                    try:
                        store.last_product_update = datetime.fromisoformat(max(stamps)).astimezone(
                            timezone.utc).replace(tzinfo=None)
                    except ValueError:
                        pass
    elif platform == "woocommerce":
        status_w, body, _ = fetch.get(f"https://{store.domain}/wp-json/wc/store/v1/products?per_page=1")
        if status_w == 200 and body.strip().startswith("["):
            store.product_count = store.product_count or None
    store.platform = platform
    if not store.name:
        import re
        m = re.search(r"<title[^>]*>([^<]{2,120})</title>", html, re.I)
        store.name = (m.group(1).split("|")[0].split("–")[0].strip() if m else store.domain)[:300]

    if not platform and not any(k in html.lower() for k in ("add to cart", "add-to-cart", "checkout")):
        _reject(store, "not_a_store")
    elif not looks_indian(store.currency, html, store.country):
        _reject(store, "not_india")
    elif store.product_count == 0:
        _reject(store, "no_products")
    else:
        tools = detect_competitors(html)
        store.competitor_tool = ",".join(tools) or None
        for t in tools:
            db.add(StoreSignal(store_id=store.id, signal_type="competitor", value=t,
                               source_url=f"https://{store.domain}/"))
        if "cash on delivery" in html.lower() or "cod available" in html.lower():
            db.add(StoreSignal(store_id=store.id, signal_type="cod", value="1",
                               source_url=f"https://{store.domain}/"))
        store.gstin = extract_gstin(html)
        store.state = "qualified"
        store._home_html = html  # reused by resolve in the same run
    store.checked_at = datetime.now()
    db.commit()
    return store.state


# ---------------------------------------------------------------- resolve
def _save_contacts(db: Session, store: Store, contacts: list[dict], source: str):
    have = {(c.phone, c.email) for c in store.contacts}
    for c in contacts:
        key = (c.get("phone"), c.get("email"))
        if key in have:
            continue
        have.add(key)
        conf = {"whatsapp": 80, "tel_link": 65, "jsonld": 65, "page_text": 55,
                "places": 60, "paid": 70}.get(c.get("phone_type"), 40)
        db.add(StoreContact(store_id=store.id, name=c.get("name"), role=c.get("role"),
                            phone=c.get("phone"), phone_type=c.get("phone_type"),
                            email=c.get("email"), source=source, source_url=c["source_url"],
                            confidence=conf))


def _places_lookup(store: Store) -> list[dict]:
    """Free-tier Places fallback (guarded by places_budget.allow)."""
    if not settings.GOOGLE_MAPS_API_KEY:
        return []
    from app.utils import places_budget
    import requests
    if not places_budget.allow(1, kind="text_search"):
        return []
    try:
        r = requests.get("https://maps.googleapis.com/maps/api/place/textsearch/json", params={
            "query": f"{store.name} {store.city or 'India'}", "key": settings.GOOGLE_MAPS_API_KEY,
            "region": "in"}, timeout=15).json().get("results", [])[:1]
        if not r or not places_budget.allow(1, kind="details"):
            return []
        d = requests.get("https://maps.googleapis.com/maps/api/place/details/json", params={
            "place_id": r[0]["place_id"], "key": settings.GOOGLE_MAPS_API_KEY,
            "fields": "international_phone_number,website,name"}, timeout=15).json().get("result", {})
        site = clean_domain(d.get("website") or "")
        if store.platform == "marketplace":
            from difflib import SequenceMatcher
            if SequenceMatcher(None, (store.name or "").lower(), (d.get("name") or "").lower()).ratio() < 0.75:
                return []
        elif site != store.domain:   # only trust Places when it confirms the same website
            return []
        p = normalize_mobile(d.get("international_phone_number"))
        url = f"https://www.google.com/maps/place/?q=place_id:{r[0]['place_id']}"
        return [{"phone": p, "phone_type": "places", "source_url": url}] if p else []
    except Exception as e:
        log.debug("places_error", domain=store.domain, error=str(e)[:80])
        return []


def resolve_store(db: Session, store: Store, use_places: bool = True) -> str:
    site = store.domain
    if store.platform == "marketplace":
        from app.pipeline.sources.name_to_domain import resolve as name_resolve
        own, _ = name_resolve(store.name or "")
        site = own
        pages = [("/", None)] + [(p, None) for p in CONTACT_PATHS["shopify"]] if own else []
    else:
        pages = [("/", getattr(store, "_home_html", None))]
        pages += [(p, None) for p in CONTACT_PATHS.get(store.platform, CONTACT_PATHS[None])]
    # Network first, no open transaction (holding locks during fetches deadlocks SQL Server)
    db.commit()
    found, gstin = [], store.gstin
    for path, html in pages:
        url = f"https://{site}{path}"
        if html is None:
            status, html, _ = fetch.get(url, timeout=10)
            if status != 200:
                continue
        found.append((extract_contacts(html, url), "site"))
        gstin = gstin or extract_gstin(html)
    has_mobile = any(c.get("phone") for cs, _ in found for c in cs)
    worth_places = store.platform == "marketplace" or store.competitor_tool or (store.product_count or 0) >= 30
    if not has_mobile and use_places and worth_places:
        places = _places_lookup(store)
        found.append((places, "places"))
        has_mobile = bool(places)
    # Then one short write transaction
    for cs, src in found:
        _save_contacts(db, store, cs, source=src)
    store.gstin = gstin
    if has_mobile:
        store.state = "resolved"
    else:
        _reject(store, "no_mobile")
    store.checked_at = datetime.now()
    db.commit()
    return store.state


# ---------------------------------------------------------------- accept
def _suppressed(db: Session, kind: str, value: str) -> bool:
    if not value:
        return False
    return db.execute(select(Suppression.id).where(Suppression.kind == kind,
                                                   Suppression.value == value)).first() is not None


def _wrong_number_phones(db: Session) -> set:
    from app.processing.dedup import normalize_phone
    rows = db.execute(select(Lead.phone).where(Lead.response_status == "wrong_contact",
                                               Lead.phone.isnot(None))).all()
    return {normalize_phone(p)[-10:] for (p,) in rows if p}


def _phone_shared(db: Session, store: Store, phone: str) -> bool:
    other = db.execute(select(func.count(func.distinct(StoreContact.store_id))).where(
        StoreContact.phone == phone, StoreContact.store_id != store.id)).scalar()
    return bool(other)


def accept_store(db: Session, store: Store, wrong_numbers: set | None = None) -> str:
    wrong_numbers = wrong_numbers if wrong_numbers is not None else _wrong_number_phones(db)
    phones = sorted([c for c in store.contacts if c.phone],
                    key=lambda c: (PHONE_RANK.get(c.phone_type, 9), -(c.confidence or 0)))
    best = None
    for c in phones:
        if c.phone in wrong_numbers or _suppressed(db, "phone", c.phone):
            continue
        if _phone_shared(db, store, c.phone):
            if not _suppressed(db, "phone", c.phone):
                db.add(Suppression(kind="phone", value=c.phone, reason="shared_number",
                                   added_by="pipeline"))
                db.flush()
            continue
        best = c
        break
    dup_lead = None
    if best:
        dup_lead = db.execute(select(Lead.id).where(
            Lead.dedup_hash == compute_dedup_hash(store.name or store.domain, best.phone))).first()
    ok, reason = accept_check(
        is_indian=True, phone=best.phone if best else None,
        source_url=best.source_url if best else None,
        phone_shared_with_other_store=False, suppressed=_suppressed(db, "domain", store.domain),
        duplicate_domain=dup_lead is not None)
    if not ok:
        _reject(store, reason if best or reason != "no_mobile" else "no_clean_mobile")
        db.commit()
        return store.state

    rating = next((int(s.value) for s in store.signals if s.signal_type == "review_rating"
                   and (s.value or "").isdigit()), None)
    named = next((c for c in store.contacts if c.name), None)
    days = (datetime.now() - store.last_product_update).days if store.last_product_update else None
    tools = (store.competitor_tool or "").split(",") if store.competitor_tool else []
    sc = score_store(platform=store.platform, product_count=store.product_count,
                     competitor_tools=tools, review_rating=rating, best_phone_type=best.phone_type,
                     has_named_person=bool(named), gstin=store.gstin, city=store.city,
                     days_since_product_update=days)
    best.is_primary = True
    store.score, store.tier = sc["score"], sc["tier"]
    email = next((c.email for c in store.contacts if c.email), None)
    from app.pipeline.pitch import opening_line
    review_app = None
    if store.source == "shopify_app_reviews" and store.source_ref:
        review_app = store.source_ref.split("apps.shopify.com/")[-1].split("/")[0]
    opener = opening_line(store_name=store.name or store.domain, platform=store.platform,
                          competitor_tools=tools, review_app=review_app, review_rating=rating,
                          product_count=store.product_count, city=store.city)
    evidence = [f"Opener: {opener}", f"Tier {sc['tier']} · score {sc['score']}", "; ".join(sc["why"]),
                f"Phone ({best.phone_type}) from {best.source_url}",
                f"Found via {store.source}" + (f": {store.source_ref}" if store.source_ref else "")]
    if store.source_note:
        evidence.append(store.source_note[:300])
    lead = Lead(
        company_name=(store.name or store.domain)[:300],
        company_url=store.source_ref if store.platform == "marketplace" else f"https://{store.domain}",
        phone=best.phone, email=email, full_name=named.name if named else None,
        title=(named.role or "").replace("_", " ").title() if named else None,
        location=store.city, industry=f"Ecommerce ({store.platform or 'unknown'})",
        product_category=store.category, gst_number=store.gstin,
        source=f"ecom:{store.source}", target_product=store.product, status="qualified",
        score=sc["score"], remarks="\n".join(evidence)[:4000],
        dedup_hash=compute_dedup_hash(store.name or store.domain, best.phone),
    )
    db.add(lead)
    db.flush()
    store.lead_id = lead.id
    store.state = "accepted"
    store.accepted_at = datetime.now()
    db.commit()
    return store.state


# ---------------------------------------------------------------- batch
def build_daily_batch(db: Session, product: str = "ecom", target: int = 50,
                      day: date | None = None) -> DailyBatch:
    day = day or date.today()
    batch = db.execute(select(DailyBatch).where(DailyBatch.product == product,
                                                DailyBatch.batch_date == day)).scalar_one_or_none()
    if not batch:
        batch = DailyBatch(product=product, batch_date=day, target=target, delivered=0)
        db.add(batch)
        db.flush()
    need = max(0, target - (batch.delivered or 0))
    tier_order = func.coalesce(Store.tier, "Z")
    picks = db.execute(select(Store).where(Store.product == product, Store.state == "accepted")
                       .order_by(tier_order, Store.score.desc(), Store.accepted_at)
                       .limit(need)).scalars().all()
    # == True, not .is_(True): "IS 1" is invalid on SQL Server
    reps = db.execute(select(User).where(User.is_active == True, User.role == "sales_rep")  # noqa: E712
                      .order_by(User.id)).scalars().all()
    for i, s in enumerate(picks):
        s.state, s.delivered_at = "delivered", datetime.now()
        if reps and s.lead_id:
            rep = reps[i % len(reps)]
            lead = db.get(Lead, s.lead_id)
            if lead and not lead.assigned_to:
                lead.assigned_to, lead.assigned_at = rep.id, datetime.now()
                db.add(LeadAssignment(lead_id=lead.id, assigned_to=rep.id))
    batch.delivered = (batch.delivered or 0) + len(picks)
    if batch.delivered < target:
        backlog = db.execute(select(func.count()).select_from(Store).where(
            Store.product == product, Store.state.in_(("discovered", "qualified", "resolved")))).scalar()
        batch.shortfall_reason = (f"only {batch.delivered}/{target} accepted leads available; "
                                  f"{backlog} stores still in the pipeline")
    else:
        batch.shortfall_reason = None
    db.commit()
    return batch
