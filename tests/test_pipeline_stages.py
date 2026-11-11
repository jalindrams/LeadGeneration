"""End-to-end stage test on fake pages: in-memory SQLite, no network."""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
import app.models  # noqa: F401
from app.models import Lead, User
from app.pipeline import stages, fetch
from app.pipeline.models import Store, Suppression, DailyBatch

HOME = """<html><head><link href="//cdn.shopify.com/s/x.css"></head><body>
<a href="https://wa.me/91{wa}">Chat</a> Price ₹499
<script src="https://sr-cdn.shiprocket.in/w.js"></script>{pad}</body></html>""".replace("{pad}", "<p>" + "catalogue " * 40 + "</p>")
META = {"myshopify_domain": "x.myshopify.com", "name": "{name}", "currency": "INR",
        "country": "India", "city": "Pune", "published_products_count": 120}

SITES = {
    "alpha.in": {"wa": "9812345601"},
    "beta.in": {"wa": "9812345602"},
    "gamma.in": {"wa": "7012345699"},   # gamma and delta share a number -> both rejected
    "delta.in": {"wa": "7012345699"},
    "usa.com": {"wa": "9812345609", "currency": "USD", "country": "United States"},
}


def fake_get(url, timeout=10, **kw):
    host = url.split("/")[2]
    path = "/" + "/".join(url.split("/")[3:])
    site = SITES.get(host)
    if not site:
        return 0, "", url
    if path.startswith("/meta.json"):
        meta = dict(META, name=host.split(".")[0].title(),
                    currency=site.get("currency", "INR"), country=site.get("country", "India"))
        return 200, json.dumps(meta), url
    if path.startswith("/products.json"):
        return 200, json.dumps({"products": [{"updated_at": "2026-11-01T10:00:00+05:30"}]}), url
    if path == "/":
        html = HOME.format(wa=site["wa"])
        if site.get("currency") == "USD":
            html = html.replace("₹499", "$20")
        return 200, html, url
    return 404, "", url


@pytest.fixture
def db(monkeypatch):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    monkeypatch.setattr(fetch, "get", fake_get)
    s = sessionmaker(bind=eng)()
    s.add_all([User(username="r1", password_hash="x", full_name="Rep One", role="sales_rep"),
               User(username="r2", password_hash="x", full_name="Rep Two", role="sales_rep")])
    s.commit()
    yield s
    s.close()


def run_all(db):
    for st in db.query(Store).all():
        stages.qualify_store(db, st)
        if st.state == "qualified":
            stages.resolve_store(db, st, use_places=False)
    for st in db.query(Store).filter(Store.state == "resolved").all():
        stages.accept_store(db, st)


def test_full_pipeline(db):
    n = stages.add_candidates(db, [{"domain": d} for d in SITES] + [{"domain": "https://www.alpha.in/"}],
                              source="test")
    assert n == 5                                   # www/https duplicate collapsed
    run_all(db)
    state = {s.domain: (s.state, s.reject_reason) for s in db.query(Store)}
    assert state["alpha.in"] == ("accepted", None)
    assert state["beta.in"] == ("accepted", None)
    assert state["usa.com"] == ("rejected", "not_india")
    assert state["gamma.in"][0] == "rejected" and state["delta.in"][0] == "rejected"
    assert db.query(Suppression).filter_by(value="7012345699", reason="shared_number").count() == 1

    alpha = db.query(Store).filter_by(domain="alpha.in").one()
    assert alpha.tier == "A" and alpha.competitor_tool == "shiprocket"
    lead = db.get(Lead, alpha.lead_id)
    assert lead.phone == "9812345601" and lead.target_product == "ecom"
    assert "https://alpha.in/" in lead.remarks       # contact source URL kept as evidence

    batch = stages.build_daily_batch(db, target=50)
    assert batch.delivered == 2 and "only 2/50" in batch.shortfall_reason
    assigned = {db.get(Lead, s.lead_id).assigned_to for s in db.query(Store).filter_by(state="delivered")}
    assert len(assigned) == 2                       # round-robin across both reps
    again = stages.build_daily_batch(db, target=50)  # idempotent for the same day
    assert again.delivered == 2 and db.query(DailyBatch).count() == 1


def test_wrong_number_never_reaccepted(db):
    db.add(Lead(company_name="Old", phone="9812345601", source="x", response_status="wrong_contact"))
    db.commit()
    stages.add_candidates(db, [{"domain": "alpha.in"}], source="test")
    run_all(db)
    st = db.query(Store).filter_by(domain="alpha.in").one()
    assert st.state == "rejected" and st.reject_reason == "no_clean_mobile"
