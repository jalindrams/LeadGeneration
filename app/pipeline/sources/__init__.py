"""
Discovery sources. Each exposes discover(db, limit) -> list of candidate dicts
({domain, name?, source_ref?, note?, rating?, platform?}) and a SOURCE name.
Free sources only here; paid ones live in app/pipeline/paid/ behind the spend ledger.
"""
from app.pipeline.sources import app_reviews, tranco, commoncrawl, new_domains, marketplace

REGISTRY = {
    app_reviews.SOURCE: app_reviews,
    tranco.SOURCE_IN: tranco,
    tranco.SOURCE_COM: tranco,
    commoncrawl.SOURCE: commoncrawl,
    new_domains.SOURCE: new_domains,
    marketplace.SOURCE: marketplace,
}
