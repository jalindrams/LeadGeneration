using System.Security.Claims;
using Api.Data;
using Api.Domain;
using Api.Services;
using Microsoft.EntityFrameworkCore;

namespace Api.Endpoints;

/// <summary>Command deck: one screen for the day (admin sees everyone, reps see their own).</summary>
public static class CommandEndpoints
{
    public static void MapCommand(this RouteGroupBuilder api)
    {
        api.MapGet("/command/deck", async (AppDb db, ClaimsPrincipal user) =>
        {
            var start = DateTime.Today;
            var today = DateOnly.FromDateTime(start);
            var leads = db.Leads.AsNoTracking().Where(l => l.Status != "synthetic");
            var calls = db.CallLogs.AsNoTracking().Where(c => c.CalledAt >= start);
            if (!user.IsAdmin())
            {
                var me = user.Id();
                leads = leads.Where(l => l.AssignedTo == me);
                var mine = db.Leads.Where(l => l.AssignedTo == me).Select(l => l.Id);
                calls = calls.Where(c => mine.Contains(c.LeadId));
            }
            var todays = await calls.Select(c => c.CallStatus).ToListAsync();
            var batch = await db.DailyBatches.AsNoTracking().FirstOrDefaultAsync(b => b.Product == "ecom" && b.BatchDate == today);
            var names = await db.Users.ToDictionaryAsync(u => u.Id, u => u.FullName);

            var hot = await leads.Where(l => l.Score >= 70 && (l.CallStatus == null || l.CallStatus == "new"))
                                 .OrderByDescending(l => l.Score).Take(10).ToListAsync();
            var due = await leads.Where(l => l.CallStatus == "follow_up" && l.FollowUpDate <= today)
                                 .OrderBy(l => l.FollowUpDate).Take(10).ToListAsync();
            var recent = await (from c in calls
                                join l in db.Leads.AsNoTracking() on c.LeadId equals l.Id
                                orderby c.CalledAt descending
                                select new { c.CalledAt, c.CallStatus, c.Remarks, c.CalledBy, leadId = l.Id, l.CompanyName })
                               .Take(12).ToListAsync();
            var failing = user.IsAdmin()
                ? await db.SourceRuns.AsNoTracking().Where(r => r.Status == "failed" && r.StartedAt >= start.AddDays(-2))
                          .OrderByDescending(r => r.Id).Take(5).Select(r => new { r.Source, r.Error, r.StartedAt }).ToListAsync()
                : [];
            return Results.Ok(new
            {
                kpis = new
                {
                    batchDelivered = batch?.Delivered ?? 0, batchTarget = batch?.Target ?? 50,
                    callsToday = todays.Count,
                    reachedToday = todays.Count(s => Outcomes.Find(s)?.Reached == true),
                    positiveToday = todays.Count(s => Outcomes.Positive.Contains(Outcomes.Find(s)?.Code ?? "")),
                    demosToday = todays.Count(s => Outcomes.Find(s)?.Code == "demo_booked"),
                    followUpsDue = await leads.CountAsync(l => l.CallStatus == "follow_up" && l.FollowUpDate <= today),
                    newLeadsToday = await leads.CountAsync(l => l.LeadCreatedAt >= start),
                },
                hot = hot.Select(l => LeadsEndpoints.Row(l, names)),
                due = due.Select(l => LeadsEndpoints.Row(l, names)),
                recent,
                failing,
            });
        });
    }
}
