"""
WhatsApp intro QUEUE for Tier A leads (plan Phase 2). This never sends: it
creates outreach_log rows with status 'queued' that a person approves and
sends. Only numbers the store published itself (phone_type whatsapp, from
the store's own site) qualify; suppressed numbers are skipped.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lead, OutreachLog
from app.pipeline.models import Store, StoreContact, Suppression

TEMPLATE_KEY = "shiplystic_intro"
TEMPLATE = ("Hi {name} team, this is Shiplystic. We help Indian online stores ship with "
            "multiple courier partners at lower rates, with a 1-click {plugin}. "
            "Can we call you for 2 minutes today? Reply STOP to opt out.")


def queue_intros(db: Session, limit: int = 50) -> int:
    rows = db.execute(
        select(Store, StoreContact).join(StoreContact, StoreContact.store_id == Store.id)
        .where(Store.state == "delivered", Store.tier == "A", StoreContact.is_primary == True,  # noqa: E712
               StoreContact.phone_type == "whatsapp", StoreContact.source == "site")
        .order_by(Store.score.desc()).limit(limit * 3)).all()
    queued = 0
    for store, contact in rows:
        if queued >= limit or not store.lead_id:
            continue
        if db.execute(select(Suppression.id).where(Suppression.kind == "phone",
                                                   Suppression.value == contact.phone)).first():
            continue
        if db.execute(select(OutreachLog.id).where(OutreachLog.lead_id == store.lead_id,
                                                   OutreachLog.template_key == TEMPLATE_KEY)).first():
            continue
        plugin = {"shopify": "Shopify app", "woocommerce": "WooCommerce plugin"}.get(store.platform, "integration")
        msg = TEMPLATE.format(name=store.name or store.domain, plugin=plugin)
        db.add(OutreachLog(lead_id=store.lead_id, channel="whatsapp", template_key=TEMPLATE_KEY,
                           message_preview=msg[:200], status="queued"))
        queued += 1
    db.commit()
    return queued
