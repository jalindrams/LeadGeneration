"""
Micraft Growth Engine - Database Models
All 6 core tables for the lead generation pipeline.
"""

import uuid
from datetime import datetime, date

from sqlalchemy import (
    Column, String, Integer, Text, DateTime, Date,
    ForeignKey, UniqueConstraint, Index, Boolean, Numeric,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# 1. LEADS TABLE - Core lead storage
# ---------------------------------------------------------------------------
class Lead(Base):
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name = Column(String(100))
    last_name = Column(String(100))
    full_name = Column(String(200))
    title = Column(String(200))  # Job title / designation
    email = Column(String(255))
    phone = Column(String(50))
    company_name = Column(String(300), nullable=False)
    company_url = Column(String(500))
    industry = Column(String(200))
    company_size = Column(String(100))  # e.g. "50-100 employees"
    location = Column(String(300))
    source = Column(String(100), nullable=False)  # indiamart, google_maps, etc.
    gst_number = Column(String(20))  # Indian GST for dedup
    product_category = Column(String(300))  # What they manufacture
    turnover = Column(String(200))  # Company turnover
    target_product = Column(String(30))  # Which Micraft product this lead is for (mes, dms, tms, ...)

    # Pipeline status
    status = Column(String(50), default="raw")  # raw, enriched, qualified, pushed, contacted
    score = Column(Integer, default=0)

    # Timestamps
    scraped_at = Column(DateTime, default=func.now())
    lead_created_at = Column(DateTime, default=func.now())

    # Outreach tracking (populated in later phases)
    first_contacted_at = Column(DateTime)
    last_contacted_at = Column(DateTime)
    response_status = Column(String(50))  # interested, not_interested, no_response, wrong_contact
    response_score = Column(Integer, default=0)
    feedback_count = Column(Integer, default=0)
    outreach_status = Column(String(50), default="pending")
    last_outreach_channel = Column(String(50))
    follow_up_count = Column(Integer, default=0)

    # CRM reference (Phase 3)
    hubspot_contact_id = Column(String(100))

    # Phase 1.5 - Calling System
    call_status = Column(String(50), default="new")  # new, follow_up, interested, not_interested, closed, no_answer
    decision_maker = Column(String(200))
    pain_point = Column(Text)
    follow_up_date = Column(Date)
    remarks = Column(Text)
    call_count = Column(Integer, default=0)

    # Dedup hash
    dedup_hash = Column(String(64), unique=True)

    # Phase 1.6 - Multi-User System
    assigned_to = Column(Integer, ForeignKey("users.id"))
    assigned_at = Column(DateTime)

    # Relationships
    feedback = relationship("LeadFeedback", back_populates="lead", cascade="all, delete-orphan")
    review_items = relationship("ManualReviewQueue", back_populates="lead", cascade="all, delete-orphan")
    assignee = relationship("User", foreign_keys=[assigned_to], backref="assigned_leads")

    __table_args__ = (
        Index("idx_leads_source", "source"),
        Index("idx_leads_status", "status"),
        Index("idx_leads_call_status", "call_status"),
        Index("idx_leads_company", "company_name"),
        Index("idx_leads_location", "location"),
        Index("idx_leads_gst", "gst_number"),
        Index("idx_leads_phone", "phone"),
        Index("idx_leads_score", "score"),
        Index("idx_leads_created", "lead_created_at"),
        Index("idx_leads_follow_up", "follow_up_date"),
        Index("idx_leads_target_product", "target_product"),
    )

    def __repr__(self):
        return f"<Lead {self.company_name} - {self.full_name}>"


# ---------------------------------------------------------------------------
# 2. SCRAPE JOBS TABLE - Track scraping runs
# ---------------------------------------------------------------------------
class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(100), nullable=False)
    search_query = Column(String(500))
    city = Column(String(100))
    status = Column(String(50), default="running")  # running, completed, failed, halted
    records_found = Column(Integer, default=0)
    records_stored = Column(Integer, default=0)
    records_duplicate = Column(Integer, default=0)
    total_pages = Column(Integer, default=0)
    current_page = Column(Integer, default=0)
    is_halted = Column(Boolean, default=False)
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime)
    error_log = Column(Text)
    duration_seconds = Column(Integer)

    __table_args__ = (
        Index("idx_scrape_source", "source"),
        Index("idx_scrape_status", "status"),
    )

    def __repr__(self):
        return f"<ScrapeJob {self.source}:{self.city} - {self.status}>"


# ---------------------------------------------------------------------------
# 3. LEAD PIPELINE METRICS - Yield tracking per source/day
# ---------------------------------------------------------------------------
class LeadPipelineMetrics(Base):
    __tablename__ = "lead_pipeline_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(100), nullable=False)
    date = Column(Date, nullable=False, default=date.today)
    raw_leads = Column(Integer, default=0)
    enriched_leads = Column(Integer, default=0)
    verified_leads = Column(Integer, default=0)
    deduped_leads = Column(Integer, default=0)
    final_qualified = Column(Integer, default=0)
    pushed_to_crm = Column(Integer, default=0)
    contacted = Column(Integer, default=0)
    converted = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("source", "date", name="uq_source_date"),
    )

    def __repr__(self):
        return f"<Metrics {self.source} {self.date}: raw={self.raw_leads}>"


# ---------------------------------------------------------------------------
# 4. LEAD FEEDBACK - Sales feedback entries (Phase 3 schema)
# ---------------------------------------------------------------------------
class LeadFeedback(Base):
    __tablename__ = "lead_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), nullable=False)  # interested, not_interested, no_response, wrong_contact, converted
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())

    lead = relationship("Lead", back_populates="feedback")

    __table_args__ = (
        Index("idx_feedback_lead", "lead_id"),
    )


# ---------------------------------------------------------------------------
# 5. MANUAL REVIEW QUEUE - Human Intelligence Queue (Phase 2 schema)
# ---------------------------------------------------------------------------
class ManualReviewQueue(Base):
    __tablename__ = "manual_review_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    reason = Column(String(50), nullable=False)  # missing_email, high_value, incomplete_data, enrichment_failed, fuzzy_dup
    priority = Column(String(10), nullable=False, default="medium")  # high, medium, low
    assigned_to = Column(String(100), default="Supritha Patil")
    status = Column(String(20), default="pending")  # pending, in_progress, resolved, skipped
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    resolved_at = Column(DateTime)

    lead = relationship("Lead", back_populates="review_items")

    __table_args__ = (
        Index("idx_review_status", "status"),
        Index("idx_review_priority", "priority"),
    )


# ---------------------------------------------------------------------------
# 6. SOURCE PERFORMANCE - Source scoring (Phase 3 schema)
# ---------------------------------------------------------------------------
class SourcePerformance(Base):
    __tablename__ = "source_performance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(100), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    total_raw = Column(Integer, default=0)
    total_qualified = Column(Integer, default=0)
    total_contacted = Column(Integer, default=0)
    total_converted = Column(Integer, default=0)
    conversion_rate = Column(Numeric(5, 2))
    data_completeness = Column(Numeric(5, 2))
    response_rate = Column(Numeric(5, 2))
    avg_lead_score = Column(Numeric(5, 2))
    source_score = Column(Numeric(5, 2))
    cost_per_lead = Column(Numeric(10, 2))
    recommendation = Column(String(20))  # scale, maintain, reduce, kill
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("source", "period_start", name="uq_source_period"),
    )

# ---------------------------------------------------------------------------
# 7. CALL LOGS - Individual call attempts (Phase 1.5 schema)
# ---------------------------------------------------------------------------
class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    called_at = Column(DateTime, default=func.now())
    duration_note = Column(String(100))  # e.g., "5 mins", "Left voicemail"
    call_status = Column(String(50), nullable=False)  # new, follow_up, interested, not_interested, closed, no_answer
    response_type = Column(String(100))
    remarks = Column(Text)
    called_by = Column(String(100), default="Sales Rep")

    lead = relationship("Lead", backref="call_logs")

    __table_args__ = (
        Index("idx_call_log_lead", "lead_id"),
        Index("idx_call_log_date", "called_at"),
    )


# ---------------------------------------------------------------------------
# 8. USERS TABLE - Sales reps and admins
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    full_name = Column(String(200), nullable=False)
    role = Column(String(50), default="sales_rep")  # admin, sales_rep
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    def __repr__(self):
        return f"<User {self.username} - {self.role}>"


# ---------------------------------------------------------------------------
# 9. LEAD ASSIGNMENTS TABLE - Track who is assigned to what
# ---------------------------------------------------------------------------
class LeadAssignment(Base):
    __tablename__ = "lead_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_by = Column(Integer, ForeignKey("users.id"))
    assigned_at = Column(DateTime, default=func.now())

    # Relationships
    lead = relationship("Lead", backref="assignments")
    user = relationship("User", foreign_keys=[assigned_to], backref="assignments")
    assigner = relationship("User", foreign_keys=[assigned_by])

    __table_args__ = (
        Index("idx_assignment_lead", "lead_id"),
        Index("idx_assignment_user", "assigned_to"),
    )

