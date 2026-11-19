"""
Store pipeline tables. Every table carries tenant_id so the tool can be sold
to other companies later without a schema rewrite (tenant 1 = Micraft).

State machine for stores.state:
  discovered -> qualified -> resolved -> accepted -> delivered
             +-> rejected (reject_reason says why, at any stage)
"""
from sqlalchemy import (
    Column, Integer, Unicode, UnicodeText, DateTime, Date, Boolean, Numeric,
    ForeignKey, Index, UniqueConstraint, Uuid, func,
)
from sqlalchemy.orm import relationship

from app.database import Base

STATES = ("discovered", "qualified", "resolved", "accepted", "delivered", "rejected")


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, default=1)
    product = Column(Unicode(30), nullable=False, default="ecom")
    domain = Column(Unicode(255), nullable=False)
    name = Column(Unicode(300))
    platform = Column(Unicode(30))            # shopify, woocommerce, magento, custom, marketplace
    country = Column(Unicode(60))
    currency = Column(Unicode(10))
    city = Column(Unicode(120))
    category = Column(Unicode(120))
    product_count = Column(Integer)
    last_product_update = Column(DateTime)
    competitor_tool = Column(Unicode(200))    # comma-separated shipping tools detected
    gstin = Column(Unicode(20))
    instagram = Column(Unicode(200))
    tier = Column(Unicode(1))                 # A, B, C
    score = Column(Integer, default=0)
    state = Column(Unicode(20), nullable=False, default="discovered")
    reject_reason = Column(Unicode(80))
    source = Column(Unicode(60), nullable=False)   # first source that found it
    source_ref = Column(Unicode(500))              # e.g. review URL / list name
    source_note = Column(UnicodeText)              # e.g. review rating + text
    attempts = Column(Integer, default=0)
    lead_id = Column(Uuid, ForeignKey("leads.id"))  # set when accepted
    discovered_at = Column(DateTime, default=func.now())
    checked_at = Column(DateTime)
    accepted_at = Column(DateTime)
    delivered_at = Column(DateTime)

    contacts = relationship("StoreContact", back_populates="store", cascade="all, delete-orphan")
    signals = relationship("StoreSignal", back_populates="store", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "product", "domain", name="uq_store_domain"),
        Index("idx_store_state", "state"),
        Index("idx_store_score", "score"),
        Index("idx_store_source", "source"),
    )


class StoreSignal(Base):
    __tablename__ = "store_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, default=1)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    signal_type = Column(Unicode(50), nullable=False)   # competitor, cod, review_rating, size, ...
    value = Column(Unicode(500))
    source_url = Column(Unicode(500))
    observed_at = Column(DateTime, default=func.now())

    store = relationship("Store", back_populates="signals")
    __table_args__ = (Index("idx_signal_store", "store_id"),)


class StoreContact(Base):
    __tablename__ = "store_contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, default=1)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    name = Column(Unicode(200))
    role = Column(Unicode(100))           # owner, grievance_officer, support, ...
    phone = Column(Unicode(15))           # 10-digit Indian mobile, no prefix
    phone_type = Column(Unicode(20))      # whatsapp, tel_link, jsonld, page_text, places, paid
    email = Column(Unicode(255))
    source = Column(Unicode(60), nullable=False)
    source_url = Column(Unicode(500), nullable=False)   # mandatory: no URL, no lead
    confidence = Column(Integer, default=0)             # 0-100
    is_primary = Column(Boolean, default=False)
    verified_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())

    store = relationship("Store", back_populates="contacts")
    __table_args__ = (
        Index("idx_contact_store", "store_id"),
        Index("idx_contact_phone", "phone"),
    )


class SourceRun(Base):
    __tablename__ = "source_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, default=1)
    source = Column(Unicode(60), nullable=False)
    stage = Column(Unicode(30), nullable=False, default="discover")
    started_at = Column(DateTime, default=func.now())
    finished_at = Column(DateTime)
    status = Column(Unicode(20), default="running")   # running, ok, failed
    discovered = Column(Integer, default=0)
    processed = Column(Integer, default=0)
    accepted = Column(Integer, default=0)
    rejected = Column(Integer, default=0)
    cost_inr = Column(Numeric(10, 2), default=0)
    error = Column(UnicodeText)
    __table_args__ = (Index("idx_run_source", "source", "started_at"),)


class DailyBatch(Base):
    __tablename__ = "daily_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, default=1)
    product = Column(Unicode(30), nullable=False, default="ecom")
    batch_date = Column(Date, nullable=False)
    target = Column(Integer, nullable=False, default=50)
    delivered = Column(Integer, default=0)
    shortfall_reason = Column(Unicode(300))
    created_at = Column(DateTime, default=func.now())
    __table_args__ = (UniqueConstraint("tenant_id", "product", "batch_date", name="uq_batch_day"),)


class Suppression(Base):
    __tablename__ = "suppression"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, default=1)
    kind = Column(Unicode(10), nullable=False)    # phone, domain, email
    value = Column(Unicode(255), nullable=False)
    reason = Column(Unicode(100))                 # wrong_number, do_not_call, opt_out, shared_number
    added_by = Column(Unicode(100))
    added_at = Column(DateTime, default=func.now())
    __table_args__ = (UniqueConstraint("tenant_id", "kind", "value", name="uq_suppression"),)


class SpendLedger(Base):
    __tablename__ = "spend_ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, default=1)
    provider = Column(Unicode(50), nullable=False)
    month = Column(Unicode(7), nullable=False)          # YYYY-MM
    units = Column(Integer, default=0)
    cost_inr = Column(Numeric(10, 2), default=0)
    cap_inr = Column(Numeric(10, 2), nullable=False, default=0)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("tenant_id", "provider", "month", name="uq_spend_month"),)
