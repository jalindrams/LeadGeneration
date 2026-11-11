"""
Ecom store scoring (0-100) and tier.
  A = switcher: competitor shipping tool evidence + mid-size catalogue
  B = growing: 30+ products or recent catalogue activity
  C = everything else that still passes the acceptance bar
Weights are a starting point; Phase 2 source ranking tunes on call outcomes.
"""

PHONE_POINTS = {"whatsapp": 30, "tel_link": 22, "jsonld": 22, "places": 20, "paid": 25, "page_text": 18}


def score_store(*, platform, product_count, competitor_tools, review_rating, best_phone_type,
                has_named_person, gstin, city, days_since_product_update) -> dict:
    pts, why = 0, []

    def add(n, reason):
        nonlocal pts
        pts += n
        why.append(f"{'+' if n >= 0 else ''}{n} {reason}")

    add(PHONE_POINTS.get(best_phone_type or "", 0), f"phone:{best_phone_type}")
    if has_named_person:
        add(10, "named person")
    if competitor_tools:
        add(20, "uses " + ",".join(competitor_tools))
    if review_rating is not None:
        add(10 if review_rating <= 3 else 5, f"reviewed a shipping app ({review_rating}*)")
    pc = product_count if isinstance(product_count, int) else None
    if pc is not None:
        if 10 <= pc <= 5000:
            add(15, f"{pc} products")
        elif pc > 5000:
            add(-10, f"{pc} products (too large)")
    if platform:
        add(3, platform)
    if gstin:
        add(5, "GSTIN")
    if city:
        add(3, "city known")
    if days_since_product_update is not None and days_since_product_update <= 60:
        add(7, "catalogue active")
    score = max(0, min(100, pts))

    switcher = bool(competitor_tools) or review_rating is not None
    if switcher and pc is not None and 10 <= pc <= 5000:
        tier = "A"
    elif (pc or 0) >= 30 or (days_since_product_update is not None and days_since_product_update <= 60):
        tier = "B"
    else:
        tier = "C"
    return {"score": score, "tier": tier, "why": why}
