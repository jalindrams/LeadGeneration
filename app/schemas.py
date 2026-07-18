"""
Micraft Growth Engine - Pydantic Schemas
Request/response models for the API layer.
"""

from datetime import datetime, date
from uuid import UUID
from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Lead Schemas
# ---------------------------------------------------------------------------
class LeadBase(BaseModel):
    company_name: str
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company_url: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    location: Optional[str] = None
    source: str
    gst_number: Optional[str] = None
    product_category: Optional[str] = None
    turnover: Optional[str] = None


class LeadCreate(LeadBase):
    pass


class LeadResponse(LeadBase):
    id: UUID
    status: str
    score: int
    scraped_at: Optional[datetime] = None
    lead_created_at: Optional[datetime] = None
    dedup_hash: Optional[str] = None
    
    # Phase 1.6 fields
    assigned_to: Optional[int] = None
    assigned_at: Optional[datetime] = None
    
    # Calling fields
    call_status: str = "new"
    decision_maker: Optional[str] = None
    pain_point: Optional[str] = None
    follow_up_date: Optional[date] = None
    remarks: Optional[str] = None
    call_count: int = 0

    class Config:
        from_attributes = True


class LeadListResponse(BaseModel):
    leads: list[LeadResponse]
    total: int
    page: int
    per_page: int


# ---------------------------------------------------------------------------
# Scrape Job Schemas
# ---------------------------------------------------------------------------
class ScrapeJobResponse(BaseModel):
    id: int
    source: str
    search_query: Optional[str] = None
    city: Optional[str] = None
    status: str
    records_found: int
    records_stored: int
    records_duplicate: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    error_log: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Pipeline Metrics Schemas
# ---------------------------------------------------------------------------
class PipelineMetricsResponse(BaseModel):
    id: int
    source: str
    date: date
    raw_leads: int
    enriched_leads: int
    verified_leads: int
    deduped_leads: int
    final_qualified: int
    pushed_to_crm: int
    contacted: int
    converted: int

    class Config:
        from_attributes = True


class PipelineSummary(BaseModel):
    total_raw: int
    total_enriched: int
    total_verified: int
    total_deduped: int
    total_qualified: int
    total_pushed: int
    total_contacted: int
    total_converted: int
    sources: dict[str, int]  # source -> raw count
    date_range: dict[str, Optional[str]]  # start, end


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str
    database: str
    timestamp: datetime
    leads_count: int
    version: str = "1.0.0-phase1"

# ---------------------------------------------------------------------------
# Calling System Schemas (Phase 1.5)
# ---------------------------------------------------------------------------
class CallLogCreate(BaseModel):
    duration_note: Optional[str] = None
    call_status: str
    response_type: Optional[str] = None
    remarks: Optional[str] = None

class CallLogResponse(BaseModel):
    id: int
    lead_id: UUID
    called_at: datetime
    duration_note: Optional[str] = None
    call_status: str
    response_type: Optional[str] = None
    remarks: Optional[str] = None
    called_by: str

    class Config:
        from_attributes = True

class CallUpdateRequest(BaseModel):
    duration_note: Optional[str] = None
    call_status: str
    response_type: Optional[str] = None
    decision_maker: Optional[str] = None
    pain_point: Optional[str] = None
    follow_up_date: Optional[date] = None
    remarks: Optional[str] = None

class DashboardStats(BaseModel):
    total_calls_today: int
    connected_today: int
    interested_today: int
    follow_ups_pending: int

# ---------------------------------------------------------------------------
# User and Auth Schemas (Phase 1.6)
# ---------------------------------------------------------------------------
class UserBase(BaseModel):
    username: str
    full_name: str
    role: str = "sales_rep"

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class LeadAssignmentCreate(BaseModel):
    lead_ids: list[UUID]
    assigned_to: int

class LoginRequest(BaseModel):
    username: str
    password: str
