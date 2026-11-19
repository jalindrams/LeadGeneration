"""Suggested opening line for the caller, built only from evidence we hold."""

TOOL_NAMES = {"shiprocket": "Shiprocket", "shipway": "Shipway", "nimbuspost": "NimbusPost",
              "ithinklogistics": "iThink Logistics", "shipmozo": "Shipmozo", "clickpost": "ClickPost",
              "shipyaari": "Shipyaari", "delhivery": "Delhivery", "xpressbees": "Xpressbees",
              "vamaship": "Vamaship", "eshipz": "eShipz"}


def opening_line(*, store_name: str, platform: str | None, competitor_tools: list[str],
                 review_app: str | None, review_rating: int | None, product_count: int | None,
                 city: str | None) -> str:
    name = store_name or "your store"
    plugin = {"shopify": "Shopify app", "woocommerce": "WooCommerce plugin"}.get(platform or "", "integration")
    if review_rating is not None and review_rating <= 3 and review_app:
        return (f"Hi, calling from Shiplystic about {name}. I saw your review of {review_app} on the "
                f"Shopify App Store. We help stores like yours fix exactly those shipping issues, and our "
                f"{plugin} syncs orders in minutes. Do you have two minutes?")
    if competitor_tools:
        tool = TOOL_NAMES.get(competitor_tools[0], competitor_tools[0].title())
        return (f"Hi, calling from Shiplystic about {name}. I can see you ship with {tool} today. "
                f"Would you be open to comparing courier rates on your next 100 orders? Our {plugin} "
                f"connects without changing your workflow.")
    size = f"{product_count} products" if product_count else "your catalogue"
    where = f" in {city}" if city else ""
    return (f"Hi, calling from Shiplystic. I was looking at {name}{where} and {size}. How are you "
            f"booking couriers for your orders today? Our {plugin} automates it with multiple courier "
            f"partners and COD support.")
