using System.Security.Claims;
using Api.Data;
using Api.Domain;
using Api.Services;
using Microsoft.EntityFrameworkCore;

namespace Api.Endpoints;

public static class CallingEndpoints
{
    public record CallIn(string Outcome, string? Remarks, DateOnly? FollowUpDate, string? DecisionMaker,
                         string? PainPoint, string? DurationNote);
    public record TransferIn(int ToUserId);
    public record ResolveIn(string? Notes, string Status = "resolved");

    public static void MapCalling(this RouteGroupBuilder api)
    {
        var g = api.MapGroup("/calling");

        g.MapGet("/meta", () => Results.Ok(new { outcomes = Outcomes.All }));

        // Rep work queue: due follow-ups first, then untouched leads by score
        g.MapGet("/workboard", async (string? view, string? product, int? page, AppDb db, ClaimsPrincipal user) =>
        {
            var today = DateOnly.FromDateTime(DateTime.Today);
            var q = db.Leads.AsNoTracking().Where(l => l.Status != "synthetic");
            if (!user.IsAdmin()) { var me = user.Id(); q = q.Where(l => l.AssignedTo == me); }
            else q = q.Where(l => l.AssignedTo != null);
            if (!string.IsNullOrEmpty(product)) q = q.Where(l => l.TargetProduct == product);
            q = view switch
            {
                "follow_up" => q.Where(l => l.CallStatus == "follow_up").OrderBy(l => l.FollowUpDate == null)
                                .ThenBy(l => l.FollowUpDate),
                "retry" => q.Where(l => l.CallStatus == "no_answer" && (l.CallCount ?? 0) < 4)
                            .OrderBy(l => l.LastContactedAt),
                "done" => q.Where(l => l.CallStatus == "interested" || l.CallStatus == "not_interested"
                                       || l.CallStatus == "closed").OrderByDescending(l => l.LastContactedAt),
                _ => q.Where(l => l.CallStatus == null || l.CallStatus == "new"
                                  || (l.CallStatus == "follow_up" && l.FollowUpDate <= today))
                      .OrderBy(l => l.CallStatus == "follow_up" ? 0 : 1).ThenByDescending(l => l.Score),
            };
            var total = await q.CountAsync();
            var rows = await q.Skip(((page ?? 1) - 1) * 50).Take(50).ToListAsync();
            var names = await db.Users.ToDictionaryAsync(u => u.Id, u => u.FullName);
            return Results.Ok(new { total, leads = rows.Select(l => LeadsEndpoints.Row(l, names)) });
        });

        // Call mode: the single next lead this caller should dial.
        // Order: due follow-ups, then new leads by score, then no-answer retries (3h+ ago, under 4 tries).
        // If the caller's own queue is empty, one unassigned lead is claimed atomically, so two
        // callers can never be handed the same lead.
        g.MapGet("/next", async (string? skip, string? product, AppDb db, ClaimsPrincipal user) =>
        {
            var me = user.Id();
            var skipIds = (skip ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries)
                                      .Select(s => Guid.TryParse(s, out var x) ? x : Guid.Empty)
                                      .Where(x => x != Guid.Empty).Take(200).ToList();
            var (id, reason) = await NextFor(db, me, skipIds, product);
            if (id == null)
            {
                id = await ClaimFromPool(db, me, skipIds, product);
                reason = id == null ? null : "new";
            }
            var counts = await QueueCounts(db, me, product);
            var start = DateTime.Today;
            var name = user.Name();
            var callsToday = await db.CallLogs.CountAsync(c => c.CalledAt >= start && c.CalledBy == name);
            return Results.Ok(new { leadId = id, reason, counts, callsToday });
        });

        g.MapGet("/dashboard", async (AppDb db, ClaimsPrincipal user) =>
        {
            var start = DateTime.Today; var end = start.AddDays(1);
            var today = DateOnly.FromDateTime(start);
            var calls = db.CallLogs.AsNoTracking().Where(c => c.CalledAt >= start && c.CalledAt < end);
            var leads = db.Leads.AsNoTracking().Where(l => l.Status != "synthetic");
            if (!user.IsAdmin())
            {
                var me = user.Id();
                var mine = db.Leads.Where(l => l.AssignedTo == me).Select(l => l.Id);
                calls = calls.Where(c => mine.Contains(c.LeadId));
                leads = leads.Where(l => l.AssignedTo == me);
            }
            var todays = await calls.Select(c => c.CallStatus).ToListAsync();
            int reached = todays.Count(s => Outcomes.Find(s)?.Reached == true || s == "interested" || s == "not_interested");
            return Results.Ok(new
            {
                callsToday = todays.Count,
                reachedToday = reached,
                positiveToday = todays.Count(s => Outcomes.Positive.Contains(Outcomes.Find(s)?.Code ?? s)),
                wrongToday = todays.Count(s => Outcomes.Find(s)?.Code == "wrong_number"),
                followUpsDue = await leads.CountAsync(l => l.CallStatus == "follow_up" && l.FollowUpDate <= today),
                queue = await leads.CountAsync(l => l.CallStatus == null || l.CallStatus == "new"),
                byOutcome = todays.GroupBy(s => Outcomes.Find(s)?.Code ?? s).Select(x => new { key = x.Key, count = x.Count() }),
            });
        });

        g.MapPost("/leads/{id:guid}/call", async (Guid id, CallIn body, AppDb db, ClaimsPrincipal user) =>
        {
            var o = Outcomes.Find(body.Outcome);
            if (o == null) return Results.BadRequest(new { error = $"unknown outcome '{body.Outcome}'" });
            var lead = await db.Leads.FirstOrDefaultAsync(l => l.Id == id);
            if (lead == null) return Results.NotFound();
            if (!user.IsAdmin() && lead.AssignedTo != user.Id()) return Results.Forbid();
            if (o.Code is "call_back" or "not_owner" && body.FollowUpDate == null)
                body = body with { FollowUpDate = DateOnly.FromDateTime(DateTime.Today.AddDays(2)) };

            var now = DateTime.Now;
            // A double tap or a retried request must not log the same call twice.
            var recent = now.AddSeconds(-20);
            var caller = user.Name();
            if (await db.CallLogs.AnyAsync(c => c.LeadId == id && c.CalledBy == caller && c.CallStatus == o.Code && c.CalledAt >= recent))
                return Results.Ok(new { lead.Id, lead.CallStatus, lead.ResponseStatus, lead.FollowUpDate, lead.CallCount, duplicate = true });
            db.CallLogs.Add(new CallLog { LeadId = id, CalledAt = now, CallStatus = o.Code, ResponseType = o.Label,
                                          Remarks = body.Remarks, DurationNote = body.DurationNote, CalledBy = user.Name() });
            lead.CallStatus = o.LeadCallStatus;
            lead.CallCount = (lead.CallCount ?? 0) + 1;
            lead.FirstContactedAt ??= now;
            lead.LastContactedAt = now;
            lead.OutreachStatus = "contacted";
            lead.LastOutreachChannel = "call";
            if (body.FollowUpDate != null) lead.FollowUpDate = body.FollowUpDate;
            if (!string.IsNullOrWhiteSpace(body.DecisionMaker)) lead.DecisionMaker = body.DecisionMaker;
            if (!string.IsNullOrWhiteSpace(body.PainPoint)) lead.PainPoint = body.PainPoint;
            if (o.ResponseStatus != null)
            {
                lead.ResponseStatus = o.ResponseStatus;
                lead.FeedbackCount = (lead.FeedbackCount ?? 0) + 1;
                db.LeadFeedback.Add(new LeadFeedback { LeadId = id, Status = o.ResponseStatus, Notes = body.Remarks, CreatedAt = now });
            }
            if (o.SuppressReason != null && Dedup.NormalizePhone(lead.Phone) is { Length: 10 } phone
                && !await db.Suppression.AnyAsync(s => s.Kind == "phone" && s.Value == phone))
                db.Suppression.Add(new Suppression { Kind = "phone", Value = phone, Reason = o.SuppressReason,
                                                     AddedBy = user.Name(), AddedAt = now });
            await db.SaveChangesAsync();
            return Results.Ok(new { lead.Id, lead.CallStatus, lead.ResponseStatus, lead.FollowUpDate, lead.CallCount });
        });

        g.MapPost("/leads/{id:guid}/transfer", async (Guid id, TransferIn body, AppDb db, ClaimsPrincipal user) =>
        {
            var lead = await db.Leads.FirstOrDefaultAsync(l => l.Id == id);
            if (lead == null) return Results.NotFound();
            if (!user.IsAdmin() && lead.AssignedTo != user.Id()) return Results.Forbid();
            if (!await db.Users.AnyAsync(u => u.Id == body.ToUserId && u.IsActive != false))
                return Results.BadRequest(new { error = "target user not found or inactive" });
            lead.AssignedTo = body.ToUserId;
            lead.AssignedAt = DateTime.Now;
            db.LeadAssignments.Add(new LeadAssignment { LeadId = id, AssignedTo = body.ToUserId,
                                                        AssignedBy = user.Id(), AssignedAt = DateTime.Now });
            await db.SaveChangesAsync();
            return Results.Ok();
        });

        g.MapGet("/reps", async (AppDb db) => Results.Ok(await db.Users.AsNoTracking()
            .Where(u => u.IsActive != false).OrderBy(u => u.FullName)
            .Select(u => new { u.Id, u.FullName, u.Role }).ToListAsync()));

        g.MapPost("/import-csv", async (IFormFile file, string? product, AppDb db, ClaimsPrincipal user) =>
        {
            if (file.Length > 5_000_000) return Results.BadRequest(new { error = "file larger than 5 MB" });
            using var reader = new StreamReader(file.OpenReadStream());
            var rows = Csv.Parse(await reader.ReadToEndAsync());
            if (rows.Count == 0) return Results.BadRequest(new { error = "empty file" });
            var header = rows[0].Select(h => h.Trim().ToLowerInvariant().Replace(' ', '_')).ToList();
            int Col(params string[] names) => names.Select(n => header.IndexOf(n)).FirstOrDefault(i => i >= 0, -1);
            int cCompany = Col("company_name", "company", "business_name", "name");
            if (cCompany < 0) return Results.BadRequest(new { error = "CSV needs a company_name column" });
            int cPhone = Col("phone", "mobile", "phone_number"), cEmail = Col("email"), cPerson = Col("full_name", "contact_name", "person"),
                cTitle = Col("title", "designation"), cCity = Col("location", "city"), cInd = Col("industry"),
                cUrl = Col("company_url", "website", "url");
            string? V(List<string> r, int i) => i >= 0 && i < r.Count && !string.IsNullOrWhiteSpace(r[i]) ? r[i].Trim() : null;

            int added = 0, dup = 0, skipped = 0;
            var me = user.Id();
            var seen = new HashSet<string>();
            foreach (var r in rows.Skip(1))
            {
                var company = V(r, cCompany);
                if (company == null) { skipped++; continue; }
                var phone = V(r, cPhone);
                var hash = Dedup.Hash(company, phone, null, V(r, cCity));
                if (!seen.Add(hash) || await db.Leads.AnyAsync(l => l.DedupHash == hash)) { dup++; continue; }
                db.Leads.Add(new Lead
                {
                    Id = Guid.NewGuid(), CompanyName = company[..Math.Min(company.Length, 300)], Phone = phone,
                    Email = V(r, cEmail), FullName = V(r, cPerson), Title = V(r, cTitle), Location = V(r, cCity),
                    Industry = V(r, cInd), CompanyUrl = V(r, cUrl), Source = "csv_import", TargetProduct = product,
                    Status = "raw", Score = 0, CallStatus = "new", DedupHash = hash,
                    ScrapedAt = DateTime.Now, LeadCreatedAt = DateTime.Now,
                    AssignedTo = user.IsAdmin() ? null : me, AssignedAt = user.IsAdmin() ? null : DateTime.Now,
                });
                added++;
            }
            await db.SaveChangesAsync();
            return Results.Ok(new { added, duplicates = dup, skipped, note = "New leads are scored by the Python worker's next rescore run." });
        }).DisableAntiforgery();

        g.MapGet("/review-queue", async (AppDb db) =>
        {
            var items = await (from r in db.ReviewQueue.AsNoTracking()
                               join l in db.Leads.AsNoTracking() on r.LeadId equals l.Id
                               where r.Status == "pending" || r.Status == "in_progress"
                               orderby r.Priority == "high" ? 0 : r.Priority == "medium" ? 1 : 2, r.CreatedAt
                               select new { r.Id, r.Reason, r.Priority, r.Status, r.Notes, r.CreatedAt,
                                            leadId = l.Id, l.CompanyName, l.Phone, l.Email, l.CompanyUrl, l.Score })
                              .Take(300).ToListAsync();
            return Results.Ok(items);
        }).RequireAuthorization("admin");

        g.MapPost("/review/{id:int}/resolve", async (int id, ResolveIn body, AppDb db) =>
        {
            var item = await db.ReviewQueue.FindAsync(id);
            if (item == null) return Results.NotFound();
            item.Status = body.Status is "resolved" or "skipped" ? body.Status : "resolved";
            item.Notes = body.Notes ?? item.Notes;
            item.ResolvedAt = DateTime.Now;
            await db.SaveChangesAsync();
            return Results.Ok();
        }).RequireAuthorization("admin");
    }

    static IQueryable<Lead> Callable(AppDb db, string? product) =>
        db.Leads.Where(l => l.Status != "synthetic" && l.Phone != null && l.Phone != ""
                            && (string.IsNullOrEmpty(product) || l.TargetProduct == product));

    static async Task<(Guid?, string?)> NextFor(AppDb db, int me, List<Guid> skip, string? product)
    {
        var today = DateOnly.FromDateTime(DateTime.Today);
        var retryBefore = DateTime.Now.AddHours(-3);
        var mine = Callable(db, product).AsNoTracking().Where(l => l.AssignedTo == me && !skip.Contains(l.Id));

        var due = await mine.Where(l => l.CallStatus == "follow_up" && (l.FollowUpDate == null || l.FollowUpDate <= today))
                            .OrderBy(l => l.FollowUpDate).ThenByDescending(l => l.Score).Select(l => (Guid?)l.Id).FirstOrDefaultAsync();
        if (due != null) return (due, "follow_up");
        var fresh = await mine.Where(l => l.CallStatus == null || l.CallStatus == "new")
                              .OrderByDescending(l => l.Score).ThenBy(l => l.AssignedAt).Select(l => (Guid?)l.Id).FirstOrDefaultAsync();
        if (fresh != null) return (fresh, "new");
        var retry = await mine.Where(l => l.CallStatus == "no_answer" && (l.CallCount ?? 0) < 4
                                          && (l.LastContactedAt == null || l.LastContactedAt < retryBefore))
                              .OrderBy(l => l.LastContactedAt).Select(l => (Guid?)l.Id).FirstOrDefaultAsync();
        return retry != null ? (retry, "retry") : (null, null);
    }

    /// <summary>Claims one unassigned new lead. The conditional UPDATE makes the claim atomic.</summary>
    static async Task<Guid?> ClaimFromPool(AppDb db, int me, List<Guid> skip, string? product)
    {
        var candidates = await Callable(db, product).AsNoTracking()
            .Where(l => l.AssignedTo == null && (l.CallStatus == null || l.CallStatus == "new") && !skip.Contains(l.Id))
            .OrderByDescending(l => l.Score).Select(l => l.Id).Take(5).ToListAsync();
        foreach (var cid in candidates)
        {
            var now = DateTime.Now;
            var won = await db.Leads.Where(l => l.Id == cid && l.AssignedTo == null)
                                    .ExecuteUpdateAsync(s => s.SetProperty(l => l.AssignedTo, me).SetProperty(l => l.AssignedAt, now));
            if (won == 1)
            {
                db.LeadAssignments.Add(new LeadAssignment { LeadId = cid, AssignedTo = me, AssignedBy = me, AssignedAt = now });
                await db.SaveChangesAsync();
                return cid;
            }
        }
        return null;
    }

    static async Task<object> QueueCounts(AppDb db, int me, string? product)
    {
        var today = DateOnly.FromDateTime(DateTime.Today);
        var retryBefore = DateTime.Now.AddHours(-3);
        var mine = Callable(db, product).AsNoTracking().Where(l => l.AssignedTo == me);
        return new
        {
            due = await mine.CountAsync(l => l.CallStatus == "follow_up" && (l.FollowUpDate == null || l.FollowUpDate <= today)),
            fresh = await mine.CountAsync(l => l.CallStatus == null || l.CallStatus == "new"),
            retry = await mine.CountAsync(l => l.CallStatus == "no_answer" && (l.CallCount ?? 0) < 4
                                              && (l.LastContactedAt == null || l.LastContactedAt < retryBefore)),
            pool = await Callable(db, product).CountAsync(l => l.AssignedTo == null && (l.CallStatus == null || l.CallStatus == "new")),
        };
    }
}

/// <summary>Minimal RFC 4180 CSV parser (quotes, escaped quotes, newlines in fields).</summary>
public static class Csv
{
    public static List<List<string>> Parse(string text)
    {
        var rows = new List<List<string>>(); var row = new List<string>(); var cell = new System.Text.StringBuilder();
        bool q = false;
        for (int i = 0; i < text.Length; i++)
        {
            char c = text[i];
            if (q)
            {
                if (c == '"' && i + 1 < text.Length && text[i + 1] == '"') { cell.Append('"'); i++; }
                else if (c == '"') q = false;
                else cell.Append(c);
            }
            else if (c == '"') q = true;
            else if (c == ',') { row.Add(cell.ToString()); cell.Clear(); }
            else if (c == '\n' || c == '\r')
            {
                if (c == '\r' && i + 1 < text.Length && text[i + 1] == '\n') i++;
                row.Add(cell.ToString()); cell.Clear();
                if (row.Any(x => x.Length > 0)) rows.Add(row);
                row = [];
            }
            else cell.Append(c);
        }
        row.Add(cell.ToString());
        if (row.Any(x => x.Length > 0)) rows.Add(row);
        if (rows.Count > 0 && rows[0].Count > 0) rows[0][0] = rows[0][0].TrimStart('﻿');
        return rows;
    }
}
