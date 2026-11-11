using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Api.Data;
using Api.Domain;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Api.Tests;

/// <summary>
/// Runs the real API against MicraftLeads_Test (schema created by the Python models:
/// `DATABASE_URL=...MicraftLeads_Test... python -c "from app.pipeline.runner import ensure_tables; ensure_tables()"`).
/// </summary>
public class ApiFactory : WebApplicationFactory<Program>
{
    public const string Conn = "Server=localhost\\SQLEXPRESS;Database=MicraftLeads_Test;Trusted_Connection=True;TrustServerCertificate=True;MultipleActiveResultSets=True";

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseSetting("ConnectionStrings:Leads", Conn);
        builder.UseSetting("Python:EnvFile", Path.Combine(Path.GetTempPath(), "shiplystic_test.env"));
    }

    public Guid AdminLead, RepLead, OtherLead;
    public int AdminId, RepId, Rep2Id;

    public void Seed()
    {
        using var scope = Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDb>();
        foreach (var t in new[] { "store_contacts", "store_signals", "stores", "call_logs", "lead_feedback", "lead_assignments",
                                  "outreach_log", "manual_review_queue", "suppression", "daily_batches", "spend_ledger", "leads", "users" })
            db.Database.ExecuteSqlRaw($"DELETE FROM [{t}]");
        var hash = BCrypt.Net.BCrypt.HashPassword("Secret123!");
        var admin = new User { Username = "t_admin", FullName = "Test Admin", Role = "admin", PasswordHash = hash, IsActive = true };
        var rep = new User { Username = "t_rep", FullName = "Test Rep", Role = "sales_rep", PasswordHash = hash, IsActive = true };
        var rep2 = new User { Username = "t_rep2", FullName = "Other Rep", Role = "sales_rep", PasswordHash = hash, IsActive = true };
        var off = new User { Username = "t_off", FullName = "Inactive", Role = "sales_rep", PasswordHash = hash, IsActive = false };
        db.Users.AddRange(admin, rep, rep2, off);
        db.SaveChanges();
        (AdminId, RepId, Rep2Id) = (admin.Id, rep.Id, rep2.Id);
        Lead L(string name, int? to, int score) => new()
        {
            Id = Guid.NewGuid(), CompanyName = name, Phone = "+91 98123 4" + Random.Shared.Next(1000, 9999), Source = "ecom:test",
            TargetProduct = "ecom", Status = "qualified", Score = score, CallStatus = "new", AssignedTo = to,
            LeadCreatedAt = DateTime.Now, ScrapedAt = DateTime.Now,
        };
        var a = L("Unassigned Co", null, 90); var r = L("Rep Co", rep.Id, 75); var o = L("Other Co", rep2.Id, 50);
        db.Leads.AddRange(a, r, o);
        db.SaveChanges();
        (AdminLead, RepLead, OtherLead) = (a.Id, r.Id, o.Id);
    }
}

public class ApiTests : IClassFixture<ApiFactory>
{
    readonly ApiFactory _f;
    public ApiTests(ApiFactory f) { _f = f; f.Seed(); }

    async Task<HttpClient> Login(string user)
    {
        var c = _f.CreateClient(new WebApplicationFactoryClientOptions { HandleCookies = true });
        var r = await c.PostAsJsonAsync("/api/auth/login", new { username = user, password = "Secret123!" });
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        return c;
    }

    [Fact]
    public async Task Everything_requires_login()
    {
        var c = _f.CreateClient();
        foreach (var url in new[] { "/api/leads", "/api/command/deck", "/api/pipeline/target", "/api/settings", "/api/admin/users" })
            Assert.Equal(HttpStatusCode.Unauthorized, (await c.GetAsync(url)).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync("/health")).StatusCode);
    }

    [Fact]
    public async Task Bad_password_and_inactive_user_rejected()
    {
        var c = _f.CreateClient();
        Assert.Equal(HttpStatusCode.Unauthorized,
            (await c.PostAsJsonAsync("/api/auth/login", new { username = "t_admin", password = "nope" })).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized,
            (await c.PostAsJsonAsync("/api/auth/login", new { username = "t_off", password = "Secret123!" })).StatusCode);
    }

    [Fact]
    public async Task Rep_sees_only_own_leads_and_no_admin_pages()
    {
        var c = await Login("t_rep");
        var body = await c.GetFromJsonAsync<JsonElement>("/api/leads");
        Assert.Equal(1, body.GetProperty("total").GetInt32());
        Assert.Equal(HttpStatusCode.Forbidden, (await c.GetAsync($"/api/leads/{_f.OtherLead}")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync($"/api/leads/{_f.RepLead}")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await c.GetAsync("/api/admin/users")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await c.GetAsync("/api/settings")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden,
            (await c.PostAsJsonAsync($"/api/calling/leads/{_f.OtherLead}/call", new { outcome = "interested" })).StatusCode);
    }

    [Fact]
    public async Task Wrong_number_logs_call_and_suppresses_phone()
    {
        var c = await Login("t_rep");
        var r = await c.PostAsJsonAsync($"/api/calling/leads/{_f.RepLead}/call", new { outcome = "wrong_number", remarks = "not theirs" });
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        using var scope = _f.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDb>();
        var lead = db.Leads.Single(l => l.Id == _f.RepLead);
        Assert.Equal("wrong_contact", lead.ResponseStatus);
        Assert.Equal("closed", lead.CallStatus);
        Assert.Equal(1, lead.CallCount);
        Assert.Single(db.CallLogs.Where(x => x.LeadId == _f.RepLead && x.CallStatus == "wrong_number"));
        Assert.True(db.Suppression.Any(s => s.Kind == "phone" && s.Value == Dedup.NormalizePhone(lead.Phone)));
        Assert.Equal(HttpStatusCode.BadRequest,
            (await c.PostAsJsonAsync($"/api/calling/leads/{_f.RepLead}/call", new { outcome = "maybe" })).StatusCode);
    }

    [Fact]
    public async Task Call_back_sets_follow_up_date()
    {
        var c = await Login("t_rep");
        await c.PostAsJsonAsync($"/api/calling/leads/{_f.RepLead}/call", new { outcome = "call_back" });
        var detail = await c.GetFromJsonAsync<JsonElement>($"/api/leads/{_f.RepLead}");
        Assert.Equal("follow_up", detail.GetProperty("lead").GetProperty("callStatus").GetString());
        Assert.False(detail.GetProperty("lead").GetProperty("followUpDate").ValueKind == JsonValueKind.Null);
    }

    [Fact]
    public async Task Admin_bulk_assigns_unassigned_leads_with_phone()
    {
        var c = await Login("t_admin");
        var r = await c.PostAsJsonAsync("/api/admin/assign-bulk", new { userId = _f.Rep2Id, count = 10 });
        var body = await r.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(1, body.GetProperty("assigned").GetInt32());
    }

    [Fact]
    public async Task Settings_never_return_secret_values()
    {
        File.WriteAllText(Path.Combine(Path.GetTempPath(), "shiplystic_test.env"), "SERPER_API_KEY=supersecret\nPAID_TOTAL_CAP_INR=0\n");
        var c = await Login("t_admin");
        var text = await c.GetStringAsync("/api/settings");
        Assert.DoesNotContain("supersecret", text);
        Assert.Contains("\"isSet\":true", text);
        var bad = await c.PostAsJsonAsync("/api/settings", new Dictionary<string, string> { ["DATABASE_URL"] = "x" });
        Assert.Equal(HttpStatusCode.BadRequest, bad.StatusCode);
        var ok = await c.PostAsJsonAsync("/api/settings", new Dictionary<string, string> { ["PAID_TOTAL_CAP_INR"] = "10000", ["SERPER_API_KEY"] = "" });
        Assert.Equal(HttpStatusCode.OK, ok.StatusCode);
        var env = File.ReadAllText(Path.Combine(Path.GetTempPath(), "shiplystic_test.env"));
        Assert.Contains("PAID_TOTAL_CAP_INR=10000", env);
        Assert.Contains("SERPER_API_KEY=supersecret", env);   // blank secret keeps the stored value
    }

    [Fact]
    public async Task Only_whitelisted_jobs_and_options_run()
    {
        var c = await Login("t_admin");
        Assert.Equal(HttpStatusCode.BadRequest, (await c.PostAsJsonAsync("/api/admin/jobs", new { name = "rm_rf" })).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await c.PostAsJsonAsync("/api/admin/jobs",
            new { name = "pipeline_discover", options = new Dictionary<string, string> { ["source"] = "x; del *" } })).StatusCode);
    }

    [Fact]
    public async Task Pipeline_target_and_funnel_respond()
    {
        var c = await Login("t_admin");
        var t = await c.GetFromJsonAsync<JsonElement>("/api/pipeline/target");
        Assert.Equal(50, t.GetProperty("today").GetProperty("target").GetInt32());
        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync("/api/pipeline/funnel")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync("/api/command/deck")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync("/api/metrics/summary")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync("/api/metrics/trend")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync("/api/outreach/cadence")).StatusCode);
    }

    [Fact]
    public async Task Csv_import_dedups_with_python_compatible_hash()
    {
        var c = await Login("t_admin");
        var csv = "company_name,phone,city\nKimti Retail Pvt Ltd,+91 98123 45601,Mumbai\nKimti Retail Pvt Ltd,+91 98123 45601,Mumbai\nAcme LLP,,Pune\n";
        var form = new MultipartFormDataContent { { new StringContent(csv), "file", "x.csv" } };
        var body = await (await c.PostAsync("/api/calling/import-csv?product=ecom", form)).Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(2, body.GetProperty("added").GetInt32());
        Assert.Equal(1, body.GetProperty("duplicates").GetInt32());
    }

    [Fact]
    public void Dedup_hash_matches_python()
    {
        // values produced by app/processing/dedup.py compute_dedup_hash
        Assert.Equal("6b0741b4dd754ddb616e2245e21a60d4d58bd05fa82f5862bdf4026faaba0e59", Dedup.Hash("Kimti Retail Pvt Ltd", "+91 98123 45601"));
        Assert.Equal("d3e727e9032953798195ae634ba537f0773f5d894de4bb2df476370530835eb9", Dedup.Hash("Acme LLP", null, null, "Pune"));
        Assert.Equal("9812345601", Dedup.NormalizeMobile("+91 98123 45601"));
        Assert.Null(Dedup.NormalizeMobile("1800 123 4567"));
    }
}
