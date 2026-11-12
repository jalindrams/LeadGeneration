from app.pipeline.verify import normalize_mobile, accept_check
from app.pipeline.extract import extract_contacts, extract_gstin, grievance_officer_name
from app.pipeline.qualify import detect_platform, detect_competitors, looks_indian
from app.pipeline.scoring import score_store


# ---- phone validation --------------------------------------------------
def test_mobile_formats_normalise_to_ten_digits():
    assert normalize_mobile("+91 98123 45678") == "9812345678"
    assert normalize_mobile("098123-45678") == "9812345678"
    assert normalize_mobile("919812345678") == "9812345678"
    assert normalize_mobile("(+91) 7012-345-678") == "7012345678"


def test_non_mobiles_and_placeholders_rejected():
    assert normalize_mobile("1800 123 4567") is None      # toll free
    assert normalize_mobile("022 2345 6789") is None      # landline
    assert normalize_mobile("9999999999") is None         # repeated digits
    assert normalize_mobile("9876543210") is None         # classic placeholder
    assert normalize_mobile("5812345678") is None         # Indian mobiles start 6-9
    assert normalize_mobile("") is None
    assert normalize_mobile(None) is None


# ---- contact extraction -----------------------------------------------
HTML = """
<html><head><script type="application/ld+json">{"@type":"Organization","telephone":"+91-8123456789"}</script></head>
<body>
<a href="https://wa.me/919812345678?text=hi">Chat</a>
<a href="tel:+917012345678">Call</a>
<p>Customer care: 9123456780 | Toll free 1800 200 3000</p>
<p>Grievance Officer: Mr. Rahul Sharma, email grievance@shopx.in</p>
<p>GSTIN: 27AAPFU0939F1ZV</p>
</body></html>
"""


def test_extract_ranks_whatsapp_first_and_keeps_source_url():
    cs = extract_contacts(HTML, "https://shopx.in/pages/contact")
    phones = [(c["phone"], c["phone_type"]) for c in cs if c.get("phone")]
    assert phones[0] == ("9812345678", "whatsapp")
    assert ("7012345678", "tel_link") in phones
    assert ("8123456789", "jsonld") in phones
    assert ("9123456780", "page_text") in phones
    assert all(c["source_url"] == "https://shopx.in/pages/contact" for c in cs)
    assert not any(c.get("phone") == "1800200300" for c in cs)


def test_extract_email_gstin_and_grievance_name():
    cs = extract_contacts(HTML, "https://shopx.in/pages/contact")
    assert any(c.get("email") == "grievance@shopx.in" for c in cs)
    assert extract_gstin(HTML) == "27AAPFU0939F1ZV"
    assert grievance_officer_name(HTML) == "Rahul Sharma"


def test_invalid_gstin_checksum_is_ignored():
    assert extract_gstin("GSTIN 27AAPFU0939F1ZX") is None


# ---- qualification ----------------------------------------------------
def test_platform_detection():
    assert detect_platform('<link href="//cdn.shopify.com/s/files/x.css">') == "shopify"
    assert detect_platform('<link href="/wp-content/plugins/woocommerce/a.css">') == "woocommerce"
    assert detect_platform('<script src="/static/version123/mage/cookies.js">') == "magento"
    assert detect_platform("<html>plain</html>") is None


def test_competitor_only_from_code_not_footer_text():
    footer = "<footer>We ship with Delhivery, Bluedart and DTDC via Shiprocket</footer>"
    assert detect_competitors(footer) == []
    code = ('<script src="https://sr-cdn.shiprocket.in/widget.js"></script>'
            '<a href="https://shopx.shiprocket.co/tracking">Track order</a>'
            '<iframe src="https://track.nimbuspost.com/x"></iframe>')
    assert detect_competitors(code) == ["nimbuspost", "shiprocket"]


def test_india_check():
    assert looks_indian(currency="INR")
    assert looks_indian(html="Price ₹ 499 incl. GST")
    assert not looks_indian(currency="USD", html="Price $20")


# ---- scoring & acceptance ---------------------------------------------
def test_switcher_scores_tier_a():
    s = score_store(platform="shopify", product_count=150, competitor_tools=["shiprocket"],
                    review_rating=2, best_phone_type="whatsapp", has_named_person=True,
                    gstin="27AAPFU0939F1ZV", city="Pune", days_since_product_update=10)
    assert s["tier"] == "A" and s["score"] >= 80


def test_unknown_small_store_scores_tier_c():
    s = score_store(platform="shopify", product_count=4, competitor_tools=[], review_rating=None,
                    best_phone_type="page_text", has_named_person=False, gstin=None,
                    city=None, days_since_product_update=None)
    assert s["tier"] == "C" and s["score"] < 50


def test_huge_catalogue_penalised():
    big = score_store(platform="shopify", product_count=25000, competitor_tools=[], review_rating=None,
                      best_phone_type="whatsapp", has_named_person=False, gstin=None,
                      city=None, days_since_product_update=None)
    mid = score_store(platform="shopify", product_count=300, competitor_tools=[], review_rating=None,
                      best_phone_type="whatsapp", has_named_person=False, gstin=None,
                      city=None, days_since_product_update=None)
    assert big["score"] < mid["score"]


def test_accept_check_rules():
    ok = dict(is_indian=True, phone="9812345678", source_url="https://x.in/c",
              phone_shared_with_other_store=False, suppressed=False, duplicate_domain=False)
    assert accept_check(**ok) == (True, None)
    assert accept_check(**{**ok, "phone": None}) == (False, "no_mobile")
    assert accept_check(**{**ok, "source_url": ""}) == (False, "no_source_url")
    assert accept_check(**{**ok, "phone_shared_with_other_store": True}) == (False, "shared_number")
    assert accept_check(**{**ok, "suppressed": True}) == (False, "suppressed")
    assert accept_check(**{**ok, "is_indian": False}) == (False, "not_india")
    assert accept_check(**{**ok, "duplicate_domain": True}) == (False, "duplicate")


def test_grievance_name_stops_at_field_labels():
    assert grievance_officer_name("<p>Grievance Officer: Abhishek Sethia Email: a@x.in</p>") == "Abhishek Sethia"
    assert grievance_officer_name("<p>Grievance Officer Name: Ms. Priya Nair Phone 98123</p>") == "Priya Nair"
    assert grievance_officer_name("<p>Grievance Officer Contact Details</p>") is None
