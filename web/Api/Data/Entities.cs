// Entities mapped onto the tables the Python workers own (SQLAlchemy creates them).
// Property names map to snake_case columns via AppDb.OnModelCreating.
namespace Api.Data;

public class Lead
{
    public Guid Id { get; set; }
    public string? FirstName { get; set; }
    public string? LastName { get; set; }
    public string? FullName { get; set; }
    public string? Title { get; set; }
    public string? Email { get; set; }
    public string? Phone { get; set; }
    public string CompanyName { get; set; } = "";
    public string? CompanyUrl { get; set; }
    public string? Industry { get; set; }
    public string? CompanySize { get; set; }
    public string? Location { get; set; }
    public string Source { get; set; } = "";
    public string? GstNumber { get; set; }
    public string? ProductCategory { get; set; }
    public string? Turnover { get; set; }
    public string? TargetProduct { get; set; }
    public string? Status { get; set; }
    public int? Score { get; set; }
    public DateTime? ScrapedAt { get; set; }
    public DateTime? LeadCreatedAt { get; set; }
    public DateTime? FirstContactedAt { get; set; }
    public DateTime? LastContactedAt { get; set; }
    public string? ResponseStatus { get; set; }
    public int? ResponseScore { get; set; }
    public int? FeedbackCount { get; set; }
    public string? OutreachStatus { get; set; }
    public string? LastOutreachChannel { get; set; }
    public int? FollowUpCount { get; set; }
    public string? HubspotContactId { get; set; }
    public string? CallStatus { get; set; }
    public string? DecisionMaker { get; set; }
    public string? PainPoint { get; set; }
    public DateOnly? FollowUpDate { get; set; }
    public string? Remarks { get; set; }
    public int? CallCount { get; set; }
    public string? DedupHash { get; set; }
    public int? AssignedTo { get; set; }
    public DateTime? AssignedAt { get; set; }
}

public class User
{
    public int Id { get; set; }
    public string Username { get; set; } = "";
    public string PasswordHash { get; set; } = "";
    public string FullName { get; set; } = "";
    public string? Role { get; set; }
    public bool? IsActive { get; set; }
    public DateTime? CreatedAt { get; set; }
}

public class CallLog
{
    public int Id { get; set; }
    public Guid LeadId { get; set; }
    public DateTime? CalledAt { get; set; }
    public string? DurationNote { get; set; }
    public string CallStatus { get; set; } = "";
    public string? ResponseType { get; set; }
    public string? Remarks { get; set; }
    public string? CalledBy { get; set; }
}

public class LeadFeedback
{
    public int Id { get; set; }
    public Guid LeadId { get; set; }
    public string Status { get; set; } = "";
    public string? Notes { get; set; }
    public DateTime? CreatedAt { get; set; }
}

public class LeadAssignment
{
    public int Id { get; set; }
    public Guid LeadId { get; set; }
    public int AssignedTo { get; set; }
    public int? AssignedBy { get; set; }
    public DateTime? AssignedAt { get; set; }
}

public class ManualReviewItem
{
    public int Id { get; set; }
    public Guid LeadId { get; set; }
    public string Reason { get; set; } = "";
    public string Priority { get; set; } = "medium";
    public string? AssignedTo { get; set; }
    public string? Status { get; set; }
    public string? Notes { get; set; }
    public DateTime? CreatedAt { get; set; }
    public DateTime? ResolvedAt { get; set; }
}

public class OutreachLog
{
    public int Id { get; set; }
    public Guid LeadId { get; set; }
    public string? Channel { get; set; }
    public string? TemplateKey { get; set; }
    public string? MessagePreview { get; set; }
    public string? Status { get; set; }
    public string? WaMessageId { get; set; }
    public string? Error { get; set; }
    public DateTime? SentAt { get; set; }
    public DateTime? DeliveredAt { get; set; }
    public DateTime? ReadAt { get; set; }
    public DateTime? RespondedAt { get; set; }
    public DateTime? CreatedAt { get; set; }
}

public class ScrapeJob
{
    public int Id { get; set; }
    public string Source { get; set; } = "";
    public string? SearchQuery { get; set; }
    public string? City { get; set; }
    public string? Status { get; set; }
    public int? RecordsFound { get; set; }
    public int? RecordsStored { get; set; }
    public int? RecordsDuplicate { get; set; }
    public int? TotalPages { get; set; }
    public int? CurrentPage { get; set; }
    public bool? IsHalted { get; set; }
    public DateTime? StartedAt { get; set; }
    public DateTime? CompletedAt { get; set; }
    public string? ErrorLog { get; set; }
    public int? DurationSeconds { get; set; }
}

public class SourcePerformance
{
    public int Id { get; set; }
    public string Source { get; set; } = "";
    public DateOnly PeriodStart { get; set; }
    public DateOnly PeriodEnd { get; set; }
    public int? TotalRaw { get; set; }
    public int? TotalQualified { get; set; }
    public int? TotalContacted { get; set; }
    public int? TotalConverted { get; set; }
    public decimal? ConversionRate { get; set; }
    public decimal? DataCompleteness { get; set; }
    public decimal? ResponseRate { get; set; }
    public decimal? AvgLeadScore { get; set; }
    public decimal? SourceScore { get; set; }
    public decimal? CostPerLead { get; set; }
    public string? Recommendation { get; set; }
    public DateTime? CreatedAt { get; set; }
}

// ---- store pipeline (app/pipeline/models.py) ----
public class Store
{
    public int Id { get; set; }
    public int TenantId { get; set; } = 1;
    public string Product { get; set; } = "ecom";
    public string Domain { get; set; } = "";
    public string? Name { get; set; }
    public string? Platform { get; set; }
    public string? Country { get; set; }
    public string? Currency { get; set; }
    public string? City { get; set; }
    public string? Category { get; set; }
    public int? ProductCount { get; set; }
    public DateTime? LastProductUpdate { get; set; }
    public string? CompetitorTool { get; set; }
    public string? Gstin { get; set; }
    public string? Instagram { get; set; }
    public string? Tier { get; set; }
    public int? Score { get; set; }
    public string State { get; set; } = "discovered";
    public string? RejectReason { get; set; }
    public string Source { get; set; } = "";
    public string? SourceRef { get; set; }
    public string? SourceNote { get; set; }
    public int? Attempts { get; set; }
    public Guid? LeadId { get; set; }
    public DateTime? DiscoveredAt { get; set; }
    public DateTime? CheckedAt { get; set; }
    public DateTime? AcceptedAt { get; set; }
    public DateTime? DeliveredAt { get; set; }
}

public class StoreContact
{
    public int Id { get; set; }
    public int TenantId { get; set; } = 1;
    public int StoreId { get; set; }
    public string? Name { get; set; }
    public string? Role { get; set; }
    public string? Phone { get; set; }
    public string? PhoneType { get; set; }
    public string? Email { get; set; }
    public string Source { get; set; } = "";
    public string SourceUrl { get; set; } = "";
    public int? Confidence { get; set; }
    public bool? IsPrimary { get; set; }
    public DateTime? VerifiedAt { get; set; }
    public DateTime? CreatedAt { get; set; }
}

public class StoreSignal
{
    public int Id { get; set; }
    public int TenantId { get; set; } = 1;
    public int StoreId { get; set; }
    public string SignalType { get; set; } = "";
    public string? Value { get; set; }
    public string? SourceUrl { get; set; }
    public DateTime? ObservedAt { get; set; }
}

public class SourceRun
{
    public int Id { get; set; }
    public int TenantId { get; set; } = 1;
    public string Source { get; set; } = "";
    public string Stage { get; set; } = "discover";
    public DateTime? StartedAt { get; set; }
    public DateTime? FinishedAt { get; set; }
    public string? Status { get; set; }
    public int? Discovered { get; set; }
    public int? Processed { get; set; }
    public int? Accepted { get; set; }
    public int? Rejected { get; set; }
    public decimal? CostInr { get; set; }
    public string? Error { get; set; }
}

public class DailyBatch
{
    public int Id { get; set; }
    public int TenantId { get; set; } = 1;
    public string Product { get; set; } = "ecom";
    public DateOnly BatchDate { get; set; }
    public int Target { get; set; }
    public int? Delivered { get; set; }
    public string? ShortfallReason { get; set; }
    public DateTime? CreatedAt { get; set; }
}

public class Suppression
{
    public int Id { get; set; }
    public int TenantId { get; set; } = 1;
    public string Kind { get; set; } = "phone";
    public string Value { get; set; } = "";
    public string? Reason { get; set; }
    public string? AddedBy { get; set; }
    public DateTime? AddedAt { get; set; }
}

public class SpendLedger
{
    public int Id { get; set; }
    public int TenantId { get; set; } = 1;
    public string Provider { get; set; } = "";
    public string Month { get; set; } = "";
    public int? Units { get; set; }
    public decimal? CostInr { get; set; }
    public decimal CapInr { get; set; }
    public DateTime? UpdatedAt { get; set; }
}
