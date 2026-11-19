using System.Text.RegularExpressions;
using Microsoft.EntityFrameworkCore;

namespace Api.Data;

/// <summary>
/// Maps existing tables (schema owned by the Python side). No EF migrations:
/// table and column names follow the SQLAlchemy models (snake_case).
/// </summary>
public class AppDb(DbContextOptions<AppDb> options) : DbContext(options)
{
    public DbSet<Lead> Leads => Set<Lead>();
    public DbSet<User> Users => Set<User>();
    public DbSet<CallLog> CallLogs => Set<CallLog>();
    public DbSet<LeadFeedback> LeadFeedback => Set<LeadFeedback>();
    public DbSet<LeadAssignment> LeadAssignments => Set<LeadAssignment>();
    public DbSet<ManualReviewItem> ReviewQueue => Set<ManualReviewItem>();
    public DbSet<OutreachLog> OutreachLog => Set<OutreachLog>();
    public DbSet<ScrapeJob> ScrapeJobs => Set<ScrapeJob>();
    public DbSet<SourcePerformance> SourcePerformance => Set<SourcePerformance>();
    public DbSet<Store> Stores => Set<Store>();
    public DbSet<StoreContact> StoreContacts => Set<StoreContact>();
    public DbSet<StoreSignal> StoreSignals => Set<StoreSignal>();
    public DbSet<SourceRun> SourceRuns => Set<SourceRun>();
    public DbSet<DailyBatch> DailyBatches => Set<DailyBatch>();
    public DbSet<Suppression> Suppression => Set<Suppression>();
    public DbSet<SpendLedger> SpendLedger => Set<SpendLedger>();

    private static string Snake(string name) =>
        Regex.Replace(name, "(?<=[a-z0-9])([A-Z])", "_$1").ToLowerInvariant();

    protected override void OnModelCreating(ModelBuilder b)
    {
        var tables = new Dictionary<Type, string>
        {
            [typeof(Lead)] = "leads", [typeof(User)] = "users", [typeof(CallLog)] = "call_logs",
            [typeof(LeadFeedback)] = "lead_feedback", [typeof(LeadAssignment)] = "lead_assignments",
            [typeof(ManualReviewItem)] = "manual_review_queue", [typeof(OutreachLog)] = "outreach_log",
            [typeof(ScrapeJob)] = "scrape_jobs", [typeof(SourcePerformance)] = "source_performance",
            [typeof(Store)] = "stores", [typeof(StoreContact)] = "store_contacts",
            [typeof(StoreSignal)] = "store_signals", [typeof(SourceRun)] = "source_runs",
            [typeof(DailyBatch)] = "daily_batches", [typeof(Suppression)] = "suppression",
            [typeof(SpendLedger)] = "spend_ledger",
        };
        foreach (var (type, table) in tables)
        {
            var e = b.Entity(type);
            e.ToTable(table);
            foreach (var p in type.GetProperties())
                e.Property(p.Name).HasColumnName(Snake(p.Name));
        }
        b.Entity<Lead>().Property(l => l.Id).ValueGeneratedNever();
        b.Entity<User>().ToTable("users");
    }
}
