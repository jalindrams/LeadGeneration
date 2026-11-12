using System.Security.Claims;
using System.Text;
using Api.Data;
using Api.Services;
using Microsoft.EntityFrameworkCore;

namespace Api.Endpoints;

public static class LeadsEndpoints
{
    public record LeadQuery(int Page = 1, int PerPage = 50, string? Source = null, string? CallStatus = null,
        string? Status = null, string? City = null, string? Industry = null, string? Product = null,
        int? MinScore = null, bool? HasPhone = null, string? AssignedTo = null, string? Search = null,
        string? Tier = null, string SortBy = "score", string SortOrder = "desc");

    public static string Tier(int? score) => score >= 70 ? "hot" : score >= 40 ? "warm" : "cold";

    /// <summary>Shared filter used by list, export and bulk assign. Reps only ever see their own leads.</summary>
    public static IQueryable<Lead> Filter(this IQueryable<Lead> q, LeadQuery f, ClaimsPrincipal user)
    {
        q = q.Where(l => l.Status != "synthetic");
        if (!user.IsAdmin()) { var me = user.Id(); q = q.Where(l => l.AssignedTo == me); }
        if (!string.IsNullOrEmpty(f.Source)) q = q.Where(l => l.Source == f.Source);
        if (!string.IsNullOrEmpty(f.CallStatus)) q = q.Where(l => l.CallStatus == f.CallStatus);
        if (!string.IsNullOrEmpty(f.Status)) q = q.Where(l => l.Status == f.Status);
        if (!string.IsNullOrEmpty(f.City)) q = q.Where(l => l.Location!.Contains(f.City));
        if (!string.IsNullOrEmpty(f.Industry)) q = q.Where(l => l.Industry!.Contains(f.Industry));
        if (!string.IsNullOrEmpty(f.Product)) q = q.Where(l => l.TargetProduct == f.Product);
        if (f.MinScore is int ms) q = q.Where(l => l.Score >= ms);
        if (f.HasPhone == true) q = q.Where(l => l.Phone != null && l.Phone != "");
        if (f.Tier == "hot") q = q.Where(l => l.Score >= 70);
        else if (f.Tier == "warm") q = q.Where(l => l.Score >= 40 && l.Score < 70);
        else if (f.Tier == "cold") q = q.Where(l => l.Score < 40 || l.Score == null);
        if (f.AssignedTo == "unassigned") q = q.Where(l => l.AssignedTo == null);
        else if (int.TryParse(f.AssignedTo, out var uid)) q = q.Where(l => l.AssignedTo == uid);
        if (!string.IsNullOrWhiteSpace(f.Search))
            q = q.Where(l => l.CompanyName.Contains(f.Search) || l.FullName!.Contains(f.Search)
                          || l.Phone!.Contains(f.Search) || l.CompanyUrl!.Contains(f.Search)
                          || l.ProductCategory!.Contains(f.Search));
        bool asc = f.SortOrder == "asc";
        return f.SortBy switch
        {
            "company_name" => asc ? q.OrderBy(l => l.CompanyName) : q.OrderByDescending(l => l.CompanyName),
            "lead_created_at" => asc ? q.OrderBy(l => l.LeadCreatedAt) : q.OrderByDescending(l => l.LeadCreatedAt),
            "follow_up_date" => q.OrderBy(l => l.FollowUpDate == null).ThenBy(l => l.FollowUpDate),
            _ => asc ? q.OrderBy(l => l.Score) : q.OrderByDescending(l => l.Score).ThenByDescending(l => l.LeadCreatedAt),
        };
    }

    public static object Row(Lead l, Dictionary<int, string>? names = null) => new
    {
        l.Id, l.CompanyName, l.CompanyUrl, l.FullName, l.Title, l.Phone, l.Email, l.Location, l.Industry,
        l.Source, l.TargetProduct, l.Status, l.Score, tier = Tier(l.Score), l.CallStatus, l.ResponseStatus,
        l.CallCount, l.FollowUpDate, l.LastContactedAt, l.LeadCreatedAt, l.AssignedTo,
        assignedName = l.AssignedTo is int a && names != null && names.TryGetValue(a, out var n) ? n : null,
    };

    public static void MapLeads(this RouteGroupBuilder api)
    {
        var g = api.MapGroup("/leads");

        g.MapGet("", async ([AsParameters] LeadQuery f, AppDb db, ClaimsPrincipal user) =>
        {
            var per = Math.Clamp(f.PerPage, 1, 200);
            var q = db.Leads.AsNoTracking().Filter(f, user);
            var total = await q.CountAsync();
            var rows = await q.Skip((Math.Max(f.Page, 1) - 1) * per).Take(per).ToListAsync();
            var names = await db.Users.ToDictionaryAsync(u => u.Id, u => u.FullName);
            return Results.Ok(new { total, page = f.Page, perPage = per, leads = rows.Select(l => Row(l, names)) });
        });

        g.MapGet("/stats", async (AppDb db, ClaimsPrincipal user) =>
        {
            var q = db.Leads.AsNoTracking().Filter(new LeadQuery(), user);
            return Results.Ok(new
            {
                total = await q.CountAsync(),
                withPhone = await q.CountAsync(l => l.Phone != null && l.Phone != ""),
                hot = await q.CountAsync(l => l.Score >= 70),
                bySource = await q.GroupBy(l => l.Source).Select(x => new { key = x.Key, count = x.Count() })
                                  .OrderByDescending(x => x.count).ToListAsync(),
                byProduct = await q.GroupBy(l => l.TargetProduct).Select(x => new { key = x.Key, count = x.Count() })
                                   .OrderByDescending(x => x.count).ToListAsync(),
                byCallStatus = await q.GroupBy(l => l.CallStatus).Select(x => new { key = x.Key, count = x.Count() })
                                      .ToListAsync(),
            });
        });

        g.MapGet("/{id:guid}", async (Guid id, AppDb db, ClaimsPrincipal user) =>
        {
            var l = await db.Leads.AsNoTracking().FirstOrDefaultAsync(x => x.Id == id);
            if (l == null) return Results.NotFound();
            if (!user.IsAdmin() && l.AssignedTo != user.Id()) return Results.Forbid();
            var names = await db.Users.ToDictionaryAsync(u => u.Id, u => u.FullName);
            var calls = await db.CallLogs.AsNoTracking().Where(c => c.LeadId == id)
                                .OrderByDescending(c => c.CalledAt).ToListAsync();
            var store = await db.Stores.AsNoTracking().FirstOrDefaultAsync(s => s.LeadId == id);
            object? evidence = null;
            if (store != null)
            {
                evidence = new
                {
                    store,
                    contacts = await db.StoreContacts.AsNoTracking().Where(c => c.StoreId == store.Id)
                                       .OrderByDescending(c => c.IsPrimary).ThenByDescending(c => c.Confidence).ToListAsync(),
                    signals = await db.StoreSignals.AsNoTracking().Where(s => s.StoreId == store.Id).ToListAsync(),
                };
            }
            var opener = (l.Remarks ?? "").Split('\n').FirstOrDefault(x => x.StartsWith("Opener: "))?[8..];
            return Results.Ok(new
            {
                lead = new
                {
                    l.Id, l.CompanyName, l.CompanyUrl, l.FullName, l.Title, l.Phone, l.Email, l.Location,
                    l.Industry, l.CompanySize, l.Source, l.GstNumber, l.ProductCategory, l.Turnover,
                    l.TargetProduct, l.Status, l.Score, tier = Tier(l.Score), l.CallStatus, l.ResponseStatus,
                    l.DecisionMaker, l.PainPoint, l.FollowUpDate, l.Remarks, l.CallCount, l.AssignedTo,
                    assignedName = l.AssignedTo is int a && names.TryGetValue(a, out var n) ? n : null,
                    l.LeadCreatedAt, l.FirstContactedAt, l.LastContactedAt,
                },
                opener, calls, evidence,
            });
        });

        g.MapGet("/export", async ([AsParameters] LeadQuery f, AppDb db, ClaimsPrincipal user) =>
        {
            var rows = await db.Leads.AsNoTracking().Filter(f, user).Take(50000).ToListAsync();
            var sb = new StringBuilder("company_name,full_name,title,phone,email,company_url,location,industry,source,target_product,score,call_status,response_status,follow_up_date\n");
            static string Esc(object? v)
            {
                var s = v?.ToString() ?? "";
                if (s.Length > 0 && "=+-@".Contains(s[0])) s = "'" + s;   // block spreadsheet formula injection
                return s.Contains(',') || s.Contains('"') || s.Contains('\n') ? $"\"{s.Replace("\"", "\"\"")}\"" : s;
            }
            foreach (var l in rows)
                sb.AppendLine(string.Join(',', new object?[] { l.CompanyName, l.FullName, l.Title, l.Phone, l.Email,
                    l.CompanyUrl, l.Location, l.Industry, l.Source, l.TargetProduct, l.Score, l.CallStatus,
                    l.ResponseStatus, l.FollowUpDate }.Select(Esc)));
            return Results.File(Encoding.UTF8.GetPreamble().Concat(Encoding.UTF8.GetBytes(sb.ToString())).ToArray(),
                "text/csv", $"leads_{DateTime.Now:yyyyMMdd_HHmm}.csv");
        }).RequireAuthorization("admin");
    }
}
