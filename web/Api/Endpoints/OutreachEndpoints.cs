using System.Security.Claims;
using Api.Data;
using Api.Services;
using Microsoft.EntityFrameworkCore;

namespace Api.Endpoints;

public static class OutreachEndpoints
{
    public record StatusIn(string Status);
    public record SendIn(string Product = "all", string Tier = "hot", int Limit = 50, bool DryRun = true);

    static readonly HashSet<string> ManualStatuses = ["sent", "responded", "skipped", "failed"];

    public static void MapOutreach(this RouteGroupBuilder api)
    {
        var g = api.MapGroup("/outreach").RequireAuthorization("admin");

        g.MapGet("/stats", async (AppDb db) =>
        {
            var since = DateTime.Today.AddDays(-30);
            var rows = await db.OutreachLog.AsNoTracking().Where(o => o.CreatedAt >= since || o.Status == "queued")
                               .GroupBy(o => new { o.Channel, o.Status }).Select(x => new { x.Key.Channel, x.Key.Status, n = x.Count() })
                               .ToListAsync();
            return Results.Ok(rows);
        });

        g.MapGet("/log", async (string? status, AppDb db) =>
        {
            var q = from o in db.OutreachLog.AsNoTracking()
                    join l in db.Leads.AsNoTracking() on o.LeadId equals l.Id
                    select new { o.Id, o.Channel, o.TemplateKey, o.MessagePreview, o.Status, o.CreatedAt, o.SentAt,
                                 leadId = l.Id, l.CompanyName, l.Phone, l.TargetProduct, l.Score };
            if (!string.IsNullOrEmpty(status)) q = q.Where(x => x.Status == status);
            return Results.Ok(await q.OrderByDescending(x => x.CreatedAt).Take(300).ToListAsync());
        });

        // A person sends queued intros from their own WhatsApp, then marks them here. Nothing is sent by the API.
        g.MapPost("/log/{id:int}/status", async (int id, StatusIn body, AppDb db) =>
        {
            if (!ManualStatuses.Contains(body.Status)) return Results.BadRequest(new { error = "status must be sent, responded, skipped or failed" });
            var o = await db.OutreachLog.FindAsync(id);
            if (o == null) return Results.NotFound();
            o.Status = body.Status;
            if (body.Status == "sent") o.SentAt = DateTime.Now;
            if (body.Status == "responded") o.RespondedAt = DateTime.Now;
            await db.SaveChangesAsync();
            return Results.Ok();
        });

        g.MapGet("/cadence", async (AppDb db) =>
        {
            var q = db.Leads.AsNoTracking().Where(l => l.Status != "synthetic" && l.Score >= 40);
            return Results.Ok(new
            {
                pending = await q.CountAsync(l => l.OutreachStatus == "pending" || l.OutreachStatus == null),
                contacted = await q.CountAsync(l => l.OutreachStatus == "contacted"),
                byStep = await q.GroupBy(l => l.FollowUpCount ?? 0).Select(x => new { step = x.Key, n = x.Count() }).OrderBy(x => x.step).ToListAsync(),
                responses = await q.Where(l => l.ResponseStatus == "interested" || l.ResponseStatus == "converted")
                                   .OrderByDescending(l => l.LastContactedAt).Take(20)
                                   .Select(l => new { l.Id, l.CompanyName, l.FullName, l.TargetProduct, l.ResponseStatus, l.Score, l.LastContactedAt })
                                   .ToListAsync(),
            });
        });

        // Runs the existing Python outreach cadence. Defaults to a dry run; a real send needs dryRun=false.
        g.MapPost("/run", (SendIn body, JobRunner jobs) =>
        {
            var opts = new Dictionary<string, string> { ["limit"] = body.Limit.ToString() };
            if (body.DryRun) opts["dry_run"] = "true";
            if (body.Product != "all") opts["product"] = body.Product;
            opts["tier"] = body.Tier;
            try { return Results.Ok(jobs.Start("outreach_send", opts)); }
            catch (ArgumentException e) { return Results.BadRequest(new { error = e.Message }); }
            catch (InvalidOperationException e) { return Results.Conflict(new { error = e.Message }); }
        });
    }
}
