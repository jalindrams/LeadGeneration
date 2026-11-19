"""Store qualification: platform, India check, competitor shipping tool fingerprint."""
import re

PLATFORM_MARKERS = [
    ("shopify", ("cdn.shopify.com", "myshopify.com", "/cdn/shop/", "Shopify.theme")),
    ("woocommerce", ("wp-content/plugins/woocommerce", "woocommerce-", "wc-block")),
    ("magento", ("mage/cookies.js", "Magento_", "/static/version")),
    ("wix", ("wixstatic.com", "wix-ecommerce")),
    ("bigcommerce", ("cdn11.bigcommerce.com",)),
    ("dukaan", ("mydukaan.io", "dukaan.app")),
]

# Competitors are detected ONLY from code: script/iframe/link sources and tracking
# links. Phase 0 showed plain-text matching flags footers that merely name couriers.
COMPETITOR_DOMAINS = {
    "shiprocket": ("shiprocket.in", "shiprocket.co", "fastrr", "pickrr.com"),
    "shipway": ("shipway.com", "shipway.in"),
    "nimbuspost": ("nimbuspost.com",),
    "ithinklogistics": ("ithinklogistics.com", "ithinklogistics.co.in"),
    "shipmozo": ("shipmozo.com",),
    "clickpost": ("clickpost.ai", "clickpost.in"),
    "shipyaari": ("shipyaari.com",),
    "delhivery": ("delhivery.com",),
    "xpressbees": ("xpressbees.com",),
    "vamaship": ("vamaship.com",),
    "eshipz": ("eshipz.com",),
}
_SRC_RE = re.compile(r"""<(?:script|iframe|img|link)\b[^>]*\b(?:src|href)=["']([^"']+)["']""", re.I)
_A_RE = re.compile(r"""<a\b[^>]*\bhref=["']([^"']+)["']""", re.I)


def detect_platform(html: str) -> str | None:
    for name, markers in PLATFORM_MARKERS:
        if any(m in html for m in markers):
            return name
    return None


def detect_competitors(html: str) -> list[str]:
    urls = [u.lower() for u in _SRC_RE.findall(html)]
    # anchors count only when they point at a tracking page on the tool's domain
    urls += [u.lower() for u in _A_RE.findall(html) if "track" in u.lower()]
    found = set()
    for tool, domains in COMPETITOR_DOMAINS.items():
        if any(d in u for u in urls for d in domains):
            found.add(tool)
    return sorted(found)


def looks_indian(currency: str | None = None, html: str = "", country: str | None = None) -> bool:
    if (currency or "").upper() == "INR" or (country or "").lower() in ("india", "in"):
        return True
    if currency and currency.upper() != "INR":
        return False
    return bool(re.search(r"₹|\bRs\.?\s?\d|\bINR\b|\+91[\s-]?[6-9]\d{4}|\bGSTIN\b", html))
