from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
import app.models  # noqa: F401
import app.pipeline.models  # noqa: F401
from app.models import CallLog, Lead, OutreachLog
from app.pipeline.models import Store, StoreContact, Suppression
from app.pipeline import outcomes, ranking, outreach_queue
from app.pipeline.pitch import opening_line


def mkdb():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_outcome_codes_and_legacy_mapping():
    assert outcomes.canonical("demo_booked") == "demo_booked"
    assert outcomes.canonical("closed") == "wrong_number"      # old UI code
    assert outcomes.canonical("follow_up") == "call_back"
    assert outcomes.canonical("bogus") is None


def test_sync_outcomes_suppresses_wrong_and_dnc():
    db = mkdb()
    a = Lead(company_name="A", phone="9812345601", source="ecom:x", target_product="ecom")
    b = Lead(company_name="B", phone="9812345602", source="ecom:x", target_product="ecom")
    c = Lead(company_name="C", phone="9812345603", source="ecom:x", target_product="ecom")
    db.add_all([a, b, c])
    db.flush()
    db.add_all([CallLog(lead_id=a.id, call_status="wrong_number"),
                CallLog(lead_id=b.id, call_status="do_not_call"),
                CallLog(lead_id=c.id, call_status="demo_booked")])
    db.commit()
    res = outcomes.sync_outcomes(db, 0)
    assert res["applied"] == 3
    sup = {s.value: s.reason for s in db.query(Suppression)}
    assert sup == {"9812345601": "wrong_number", "9812345602": "do_not_call"}
    assert db.get(Lead, c.id).response_status == "interested"
    assert outcomes.sync_outcomes(db, res["last_id"])["applied"] == 0   # cursor works


def test_recommendation_rules():
    assert ranking.recommend(10, 0.5, 0.0, 0.2) == "learning"
    assert ranking.recommend(40, 0.6, 0.40, 0.1) == "kill"
    assert ranking.recommend(40, 0.6, 0.05, 0.10) == "scale"
    assert ranking.recommend(40, 0.6, 0.10, 0.01) == "reduce"
    assert ranking.recommend(40, 0.6, 0.10, 0.05) == "maintain"


def test_source_stats_uses_latest_outcome_per_lead():
    db = mkdb()
    leads = [Lead(company_name=f"L{i}", phone=f"98123456{i:02d}", source="ecom:tranco_in",
                  target_product="ecom", lead_created_at=datetime.now()) for i in range(4)]
    db.add_all(leads)
    db.flush()
    db.add_all([CallLog(lead_id=leads[0].id, call_status="no_answer", called_at=datetime(2026, 11, 1)),
                CallLog(lead_id=leads[0].id, call_status="interested", called_at=datetime(2026, 11, 2)),
                CallLog(lead_id=leads[1].id, call_status="wrong_number"),
                CallLog(lead_id=leads[2].id, call_status="not_owner")])
    db.commit()
    s = ranking.source_stats(db)["tranco_in"]
    assert (s["delivered"], s["called"], s["reached"], s["wrong"], s["positive"]) == (4, 3, 2, 1, 1)


def test_opening_line_uses_only_held_evidence():
    review = opening_line(store_name="Kimti", platform="shopify", competitor_tools=["shiprocket"],
                          review_app="nimbuspost", review_rating=2, product_count=300, city="Mumbai")
    assert "review of nimbuspost" in review and "Shopify app" in review
    tool = opening_line(store_name="Kimti", platform="woocommerce", competitor_tools=["shiprocket"],
                        review_app=None, review_rating=None, product_count=None, city=None)
    assert "Shiprocket" in tool and "WooCommerce plugin" in tool
    plain = opening_line(store_name="Kimti", platform=None, competitor_tools=[], review_app=None,
                         review_rating=None, product_count=None, city=None)
    assert "Shiprocket" not in plain and "review" not in plain


def test_intro_queue_only_tier_a_site_whatsapp_and_never_sends():
    db = mkdb()
    rows = []
    for i, (tier, ptype, src) in enumerate([("A", "whatsapp", "site"), ("B", "whatsapp", "site"),
                                            ("A", "places", "places"), ("A", "whatsapp", "site")]):
        lead = Lead(company_name=f"S{i}", source="ecom:x", target_product="ecom")
        db.add(lead)
        db.flush()
        st = Store(domain=f"s{i}.in", source="x", state="delivered", tier=tier, score=80, lead_id=lead.id)
        db.add(st)
        db.flush()
        db.add(StoreContact(store_id=st.id, phone=f"98123450{i:02d}", phone_type=ptype, source=src,
                            source_url="https://x", is_primary=True))
        rows.append(st)
    db.add(Suppression(kind="phone", value="9812345003", reason="do_not_call"))
    db.commit()
    assert outreach_queue.queue_intros(db) == 1            # only store 0 qualifies
    assert {o.status for o in db.query(OutreachLog)} == {"queued"}
    assert outreach_queue.queue_intros(db) == 0            # idempotent


def test_amazon_seller_parser():
    from app.pipeline.sources.marketplace import parse_seller
    html = ("<div><h3>Detailed Seller Information</h3><span>Business Name:</span><span>KIMTI RETAIL LLP</span>"
            "<span>Business Address:</span><div>12 MG Road</div><div>Andheri East</div><div>Mumbai</div>"
            "<div>MAHARASHTRA</div><div>400069</div><div>IN</div></div>")
    info = parse_seller(html)
    assert info["business_name"] == "KIMTI RETAIL LLP" and info["pincode"] == "400069"
    assert "Andheri East" in info["address"]
    assert parse_seller("<html>no seller here</html>") is None
