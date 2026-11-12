using System.Security.Claims;
using Api.Data;
using Api.Domain;
using Api.Services;
using Microsoft.EntityFrameworkCore;

namespace Api.Endpoints;

public static class PipelineEndpoints
{
    public record SuppressIn(string Kind, string Value, string? Reason);

    public static void MapPipeline(this RouteGroupBuilder api)
    {
        var g = api.MapGroup("/pipeline").RequireAuthorization("admin");

        // Daily target: today vs 50, last 14 days, backlog
        g.MapGet("/target", async (string? product, AppDb db) =>
        {
            var p = product ?? "ecom";
            var today = DateOnly.FromDateTime(DateTime.Today);
            var batches = await db.DailyBatches.AsNoTracking().Where(b => b.Product == p && b.BatchDate >= today.AddDays(-13))
                                  .OrderBy(b => b.BatchDate).ToListAsync();
            var states = await db.Stores.AsNoTracking().Where(s => s.Product == p).GroupBy(s => s.State)
                                 .Select(x => new { state = x.Key, n = x.Count() }).ToDictionaryAsync(x => x.state, x => x.n);
            var acceptedToday = await db.Stores.CountAsync(s => s.Product == p && s.AcceptedAt >= DateTime.Today);
            var t = batches.FirstOrDefault(b => b.BatchDate == today);
            return Results.Ok(new
            {
                today = new { date = today, target = t?.Target ?? 50, delivered = t?.Delivered ?? 0, shortfall = t?.ShortfallReason },
                acceptedToday,
                readyToDeliver = states.GetValueOrDefault("accepted"),
                inPipeline = states.GetValueOrDefault("discovered") + states.GetValueOrDefault("qualified") + states.GetValueOrDefault("resolved"),
                states,
                history = batches.Select(b => new { date = b.BatchDate, b.Target, delivered = b.Delivered ?? 0, b.ShortfallReason }),
                daysAvailable = Math.Round(states.GetValueOrDefault("accepted") / 50.0, 1),
            });
        });

        // Funnel + call quality per source
        g.MapGet("/funnel", async (AppDb db) =>
        {
            var byState = await db.Stores.AsNoTracking().GroupBy(s => new { s.Source, s.State })
                                  .Select(x => new { x.Key.Source, x.Key.State, n = x.Count() }).ToListAsync();
            var rejects = await db.Stores.AsNoTracking().Where(s => s.State == "rejected")
                                  .GroupBy(s => new { s.Source, s.RejectReason })
                                  .Select(x => new { x.Key.Source, reason = x.Key.RejectReason, n = x.Count() }).ToListAsync();
            var calls = await (from s in db.Stores.AsNoTracking()
                               join c in db.CallLogs.AsNoTracking() on s.LeadId equals c.LeadId
                               select new { s.Source, c.LeadId, c.CallStatus, c.CalledAt }).ToListAsync();
            var tiers = await db.Stores.AsNoTracking().Where(s => s.State == "accepted" || s.State == "delivered")
                                .GroupBy(s => new { s.Source, s.Tier }).Select(x => new { x.Key.Source, x.Key.Tier, n = x.Count() }).ToListAsync();
            var sources = byState.Select(x => x.Source).Distinct().OrderBy(x => x);
            return Results.Ok(sources.Select(src =>
            {
                int S(string st) => byState.Where(x => x.Source == src && x.State == st).Sum(x => x.n);
                var last = calls.Where(c => c.Source == src).GroupBy(c => c.LeadId)
                                .Select(gr => Outcomes.Find(gr.OrderByDescending(c => c.CalledAt).First().CallStatus)).ToList();
                int called = last.Count;
                return new
                {
                    source = src,
                    total = byState.Where(x => x.Source == src).Sum(x => x.n),
                    discovered = S("discovered") + S("qualified") + S("resolved"),
                    rejected = S("rejected"), accepted = S("accepted"), delivered = S("delivered"),
                    rejectReasons = rejects.Where(r => r.Source == src).OrderByDescending(r => r.n).Select(r => new { r.reason, r.n }),
                    tiers = tiers.Where(t => t.Source == src).Select(t => new { t.Tier, t.n }),
                    called,
                    reachRate = called > 0 ? Math.Round(last.Count(o => o?.Reached == true) / (double)called, 3) : (double?)null,
                    wrongRate = called > 0 ? Math.Round(last.Count(o => o?.Code == "wrong_number") / (double)called, 3) : (double?)null,
                    positiveRate = called > 0 ? Math.Round(last.Count(o => o != null && Outcomes.Positive.Contains(o.Code)) / (double)called, 3) : (double?)null,
                };
            }));
        });

        g.MapGet("/runs", async (AppDb db) => Results.Ok(await db.SourceRuns.AsNoTracking()
            .OrderByDescending(r => r.Id).Take(60).ToListAsync()));

        g.MapGet("/stores", async (string? state, string? tier, string? source, string? search, int? page, AppDb db) =>
        {
            var q = db.Stores.AsNoTracking().AsQueryable();
            if (!string.IsNullOrEmpty(state)) q = q.Where(s => s.State == state);
            if (!string.IsNullOrEmpty(tier)) q = q.Where(s => s.Tier == tier);
            if (!string.IsNullOrEmpty(source)) q = q.Where(s => s.Source == source);
            if (!string.IsNullOrWhiteSpace(search)) q = q.Where(s => s.Domain.Contains(search) || s.Name!.Contains(search));
            var total = await q.CountAsync();
            var rows = await q.OrderByDescending(s => s.Score).ThenByDescending(s => s.Id)
                              .Skip(((page ?? 1) - 1) * 50).Take(50).ToListAsync();
            return Results.Ok(new { total, stores = rows });
        });

        g.MapGet("/stores/{id:int}", async (int id, AppDb db) =>
        {
            var s = await db.Stores.AsNoTracking().FirstOrDefaultAsync(x => x.Id == id);
            if (s == null) return Results.NotFound();
            return Results.Ok(new
            {
                store = s,
                contacts = await db.StoreContacts.AsNoTracking().Where(c => c.StoreId == id).ToListAsync(),
                signals = await db.StoreSignals.AsNoTracking().Where(c => c.StoreId == id).ToListAsync(),
            });
        });

        g.MapGet("/suppression", async (string? search, AppDb db) =>
        {
            var q = db.Suppression.AsNoTracking().AsQueryable();
            if (!string.IsNullOrWhiteSpace(search)) q = q.Where(s => s.Value.Contains(search));
            return Results.Ok(await q.OrderByDescending(s => s.AddedAt).Take(500).ToListAsync());
        });

        g.MapPost("/suppression", async (SuppressIn body, AppDb db, ClaimsPrincipal user) =>
        {
            var kind = body.Kind?.ToLowerInvariant();
            string? value = kind switch
            {
                "phone" => Dedup.NormalizeMobile(body.Value) ?? Dedup.NormalizePhone(body.Value),
                "domain" => body.Value.Trim().ToLowerInvariant().Replace("https://", "").Replace("http://", "").Replace("www.", "").TrimEnd('/'),
                "email" => body.Value.Trim().ToLowerInvariant(),
                _ => null,
            };
            if (string.IsNullOrEmpty(value)) return Results.BadRequest(new { error = "kind must be phone, domain or email with a valid value" });
            if (await db.Suppression.AnyAsync(s => s.Kind == kind && s.Value == value)) return Results.Ok(new { value, existed = true });
            db.Suppression.Add(new Suppression { Kind = kind!, Value = value, Reason = body.Reason ?? "manual",
                                                 AddedBy = user.Name(), AddedAt = DateTime.Now });
            await db.SaveChangesAsync();
            return Results.Ok(new { value, existed = false });
        });

        g.MapDelete("/suppression/{id:int}", async (int id, AppDb db) =>
        {
            var s = await db.Suppression.FindAsync(id);
            if (s == null) return Results.NotFound();
            db.Suppression.Remove(s);
            await db.SaveChangesAsync();
            return Results.Ok();
        });

        g.MapGet("/spend", async (AppDb db, IConfiguration cfg, EnvSettings env) =>
        {
            var month = DateTime.Today.ToString("yyyy-MM");
            var rows = await db.SpendLedger.AsNoTracking().Where(s => s.Month == month).ToListAsync();
            return Results.Ok(new { month, rows, totalSpent = rows.Sum(r => r.CostInr ?? 0), settings = env.Get() });
        });
    }
}
