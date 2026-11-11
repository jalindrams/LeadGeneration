using Api.Data;
using Api.Domain;
using Microsoft.EntityFrameworkCore;

namespace Api.Endpoints;

public static class MetricsEndpoints
{
    public static void MapMetrics(this RouteGroupBuilder api)
    {
        var g = api.MapGroup("/metrics").RequireAuthorization("admin");

        g.MapGet("/summary", async (AppDb db) =>
        {
            var real = db.Leads.AsNoTracking().Where(l => l.Status != "synthetic");
            return Results.Ok(new
            {
                total = await real.CountAsync(),
                qualified = await real.CountAsync(l => l.Status == "qualified"),
                hot = await real.CountAsync(l => l.Score >= 70),
                warm = await real.CountAsync(l => l.Score >= 40 && l.Score < 70),
                contacted = await real.CountAsync(l => l.FirstContactedAt != null),
                interested = await real.CountAsync(l => l.ResponseStatus == "interested"),
                converted = await real.CountAsync(l => l.ResponseStatus == "converted"),
                unassignedWithPhone = await real.CountAsync(l => l.AssignedTo == null && l.Phone != null && l.Phone != ""),
                byProduct = await real.GroupBy(l => l.TargetProduct)
                    .Select(x => new { product = x.Key, total = x.Count(), hot = x.Count(l => l.Score >= 70),
                                       contacted = x.Count(l => l.FirstContactedAt != null),
                                       interested = x.Count(l => l.ResponseStatus == "interested" || l.ResponseStatus == "converted") })
                    .OrderByDescending(x => x.total).ToListAsync(),
            });
        });

        g.MapGet("/trend", async (int? days, AppDb db) =>
        {
            var since = DateTime.Today.AddDays(-(days ?? 14) + 1);
            var leads = await db.Leads.AsNoTracking().Where(l => l.LeadCreatedAt >= since && l.Status != "synthetic")
                                .GroupBy(l => l.LeadCreatedAt!.Value.Date).Select(x => new { day = x.Key, n = x.Count() }).ToListAsync();
            var calls = await db.CallLogs.AsNoTracking().Where(c => c.CalledAt >= since)
                                .Select(c => new { day = c.CalledAt!.Value.Date, c.CallStatus }).ToListAsync();
            var series = Enumerable.Range(0, days ?? 14).Select(i => since.AddDays(i)).Select(d => new
            {
                day = DateOnly.FromDateTime(d),
                leads = leads.FirstOrDefault(x => x.day == d)?.n ?? 0,
                calls = calls.Count(c => c.day == d),
                positive = calls.Count(c => c.day == d && Outcomes.Positive.Contains(Outcomes.Find(c.CallStatus)?.Code ?? c.CallStatus)),
            });
            return Results.Ok(series);
        });

        g.MapGet("/speed-to-lead", async (AppDb db) =>
        {
            var since = DateTime.Today.AddDays(-30);
            var pairs = await db.Leads.AsNoTracking()
                .Where(l => l.FirstContactedAt != null && l.LeadCreatedAt != null && l.LeadCreatedAt >= since)
                .Select(l => new { l.LeadCreatedAt, l.FirstContactedAt }).ToListAsync();
            var hours = pairs.Select(p => (p.FirstContactedAt!.Value - p.LeadCreatedAt!.Value).TotalHours).Where(h => h >= 0).OrderBy(h => h).ToList();
            return Results.Ok(new { leads = hours.Count,
                                    medianHours = hours.Count > 0 ? Math.Round(hours[hours.Count / 2], 1) : (double?)null,
                                    within24h = hours.Count(h => h <= 24) });
        });

        g.MapGet("/source-performance", async (AppDb db) => Results.Ok(await db.SourcePerformance.AsNoTracking()
            .OrderByDescending(s => s.PeriodEnd).ThenBy(s => s.Source).Take(100).ToListAsync()));
    }
}
