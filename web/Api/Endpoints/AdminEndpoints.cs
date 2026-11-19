using System.Security.Claims;
using Api.Data;
using Api.Services;
using Microsoft.EntityFrameworkCore;

namespace Api.Endpoints;

public static class AdminEndpoints
{
    public record UserIn(string Username, string Password, string FullName, string Role = "sales_rep");
    public record PasswordIn(string Password);
    public record AssignIn(List<Guid> LeadIds, int UserId);
    public record BulkAssignIn(int UserId, int Count, string? Product, string? City, string? Industry,
                               int? MinScore, string? Source);
    public record JobIn(string Name, Dictionary<string, string>? Options);

    public static void MapAdmin(this RouteGroupBuilder api)
    {
        var g = api.MapGroup("/admin").RequireAuthorization("admin");

        g.MapGet("/users", async (AppDb db) =>
        {
            var counts = await db.Leads.Where(l => l.AssignedTo != null).GroupBy(l => l.AssignedTo)
                                 .Select(x => new { id = x.Key, n = x.Count() }).ToDictionaryAsync(x => x.id!.Value, x => x.n);
            var users = await db.Users.AsNoTracking().OrderBy(u => u.FullName).ToListAsync();
            return Results.Ok(users.Select(u => new { u.Id, u.Username, u.FullName, u.Role, u.IsActive, u.CreatedAt,
                                                      assigned = counts.GetValueOrDefault(u.Id) }));
        });

        g.MapPost("/users", async (UserIn body, AppDb db) =>
        {
            if (string.IsNullOrWhiteSpace(body.Username) || (body.Password ?? "").Length < 8)
                return Results.BadRequest(new { error = "username required and password must be at least 8 characters" });
            if (body.Role is not ("admin" or "sales_rep")) return Results.BadRequest(new { error = "role must be admin or sales_rep" });
            if (await db.Users.AnyAsync(u => u.Username == body.Username)) return Results.Conflict(new { error = "username taken" });
            var u = new User { Username = body.Username.Trim(), FullName = body.FullName.Trim(), Role = body.Role,
                               PasswordHash = BCrypt.Net.BCrypt.HashPassword(body.Password), IsActive = true, CreatedAt = DateTime.Now };
            db.Users.Add(u);
            await db.SaveChangesAsync();
            return Results.Ok(new { u.Id });
        });

        g.MapPost("/users/{id:int}/toggle", async (int id, AppDb db, ClaimsPrincipal me) =>
        {
            if (id == me.Id()) return Results.BadRequest(new { error = "you cannot deactivate yourself" });
            var u = await db.Users.FindAsync(id);
            if (u == null) return Results.NotFound();
            u.IsActive = !(u.IsActive ?? true);
            await db.SaveChangesAsync();
            return Results.Ok(new { u.Id, u.IsActive });
        });

        g.MapPost("/users/{id:int}/password", async (int id, PasswordIn body, AppDb db) =>
        {
            if ((body.Password ?? "").Length < 8) return Results.BadRequest(new { error = "password must be at least 8 characters" });
            var u = await db.Users.FindAsync(id);
            if (u == null) return Results.NotFound();
            u.PasswordHash = BCrypt.Net.BCrypt.HashPassword(body.Password);
            await db.SaveChangesAsync();
            return Results.Ok();
        });

        g.MapPost("/assign", async (AssignIn body, AppDb db, ClaimsPrincipal me) =>
        {
            if (!await db.Users.AnyAsync(u => u.Id == body.UserId)) return Results.BadRequest(new { error = "unknown user" });
            var leads = await db.Leads.Where(l => body.LeadIds.Contains(l.Id)).ToListAsync();
            foreach (var l in leads)
            {
                l.AssignedTo = body.UserId; l.AssignedAt = DateTime.Now;
                db.LeadAssignments.Add(new LeadAssignment { LeadId = l.Id, AssignedTo = body.UserId, AssignedBy = me.Id(), AssignedAt = DateTime.Now });
            }
            await db.SaveChangesAsync();
            return Results.Ok(new { assigned = leads.Count });
        });

        g.MapPost("/assign-bulk", async (BulkAssignIn body, AppDb db, ClaimsPrincipal me) =>
        {
            if (!await db.Users.AnyAsync(u => u.Id == body.UserId)) return Results.BadRequest(new { error = "unknown user" });
            var f = new LeadsEndpoints.LeadQuery(Source: body.Source, City: body.City, Industry: body.Industry,
                Product: body.Product, MinScore: body.MinScore, HasPhone: true, AssignedTo: "unassigned");
            var leads = await db.Leads.Filter(f, me).Take(Math.Clamp(body.Count, 1, 1000)).ToListAsync();
            foreach (var l in leads)
            {
                l.AssignedTo = body.UserId; l.AssignedAt = DateTime.Now;
                db.LeadAssignments.Add(new LeadAssignment { LeadId = l.Id, AssignedTo = body.UserId, AssignedBy = me.Id(), AssignedAt = DateTime.Now });
            }
            await db.SaveChangesAsync();
            return Results.Ok(new { assigned = leads.Count });
        });

        g.MapGet("/assign-preview", async ([AsParameters] LeadsEndpoints.LeadQuery f, AppDb db, ClaimsPrincipal me) =>
            Results.Ok(new { available = await db.Leads.Filter(f with { AssignedTo = "unassigned", HasPhone = true }, me).CountAsync() }));

        // Python worker jobs (whitelisted in JobRunner)
        g.MapGet("/jobs", (JobRunner jobs) => Results.Ok(jobs.List()));
        g.MapPost("/jobs", (JobIn body, JobRunner jobs) =>
        {
            try { return Results.Ok(jobs.Start(body.Name, body.Options)); }
            catch (ArgumentException e) { return Results.BadRequest(new { error = e.Message }); }
            catch (InvalidOperationException e) { return Results.Conflict(new { error = e.Message }); }
        });
        g.MapPost("/jobs/{id}/stop", (string id, JobRunner jobs) => jobs.Stop(id) ? Results.Ok() : Results.NotFound());
        g.MapGet("/jobs/{id}/log", (string id, JobRunner jobs) => Results.Text(jobs.Tail(id)));

        g.MapGet("/scrape-jobs", async (AppDb db) => Results.Ok(await db.ScrapeJobs.AsNoTracking()
            .OrderByDescending(j => j.StartedAt).Take(50).ToListAsync()));
    }
}
