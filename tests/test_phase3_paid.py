import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
import app.models  # noqa: F401
import app.pipeline.models  # noqa: F401
from app.pipeline.models import Store, StoreContact
from app.pipeline.paid import ledger, serper, storeleads
from app.pipeline.paid.contacts_import import import_csv


@pytest.fixture
def db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def test_paid_is_off_by_default(db, monkeypatch):
    monkeypatch.delenv("PAID_TOTAL_CAP_INR", raising=False)
    monkeypatch.delenv("PAID_SERPER_CAP_INR", raising=False)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    with pytest.raises(ledger.BudgetExceeded):
        ledger.charge("serper", 1, 0.09, db=db)
    assert not serper.enabled() and not storeleads.enabled()
    with pytest.raises(RuntimeError):
        serper.discover(db)


def test_provider_and_total_caps_are_hard(db, monkeypatch):
    monkeypatch.setenv("PAID_TOTAL_CAP_INR", "100")
    monkeypatch.setenv("PAID_SERPER_CAP_INR", "60")
    monkeypatch.setenv("PAID_EASYLEADZ_CAP_INR", "80")
    ledger.charge("serper", 500, 0.1, db=db)             # 50
    with pytest.raises(ledger.BudgetExceeded):
        ledger.charge("serper", 200, 0.1, db=db)         # would be 70 > 60
    ledger.charge("easyleadz", 1, 40, db=db)             # total 90
    with pytest.raises(ledger.BudgetExceeded):
        ledger.charge("easyleadz", 1, 40, db=db)         # total would be 130 > 100
    s = ledger.summary(db)
    assert s["total_spent"] == 90.0
    assert {p["provider"]: p["spent"] for p in s["providers"]} == {"serper": 50.0, "easyleadz": 40.0}


def test_storeleads_record_mapping():
    c = storeleads.to_candidate({"name": "kimti.in", "merchant_name": "Kimti", "platform": "Shopify",
                                 "contact_info": [{"type": "phone", "value": "+91 98123 45601"},
                                                  {"type": "email", "value": "a@kimti.in"}],
                                 "apps": [{"name": "Shiprocket"}]})
    assert c["domain"] == "kimti.in" and c["platform"] == "shopify"
    assert c["paid_phones"] == ["+91 98123 45601"] and "Shiprocket" in c["note"]


def test_csv_contact_import_reaccepts_store(db, tmp_path, monkeypatch):
    monkeypatch.setenv("PAID_TOTAL_CAP_INR", "1000")
    monkeypatch.setenv("PAID_EASYLEADZ_CAP_INR", "1000")
    st = Store(domain="kimti.in", name="Kimti", source="x", state="rejected", reject_reason="no_mobile",
               platform="shopify", product_count=200)
    db.add(st)
    db.commit()
    f = tmp_path / "el.csv"
    f.write_text("Domain,Mobile,Name,Designation\nhttps://www.kimti.in,+91 98123 45601,Asha Rao,Founder\n"
                 "nosuch.in,9812345602,X,Y\nkimti.in,1800 123 4567,Z,W\n", encoding="utf-8")
    out = import_csv(db, str(f), "easyleadz", 40)
    assert out == {"rows": 3, "stored": 1, "bad_mobile": 1, "unknown_store": 1, "reaccepted": 1}
    c = db.query(StoreContact).one()
    assert c.phone_type == "paid" and c.name == "Asha Rao" and "el.csv" in c.source_url
    assert db.get(Store, st.id).state == "accepted"
    assert ledger.summary(db)["total_spent"] == 40.0
