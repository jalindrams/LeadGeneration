using System.Text.Json;
using System.Text.Json.Serialization;
using Api.Data;
using Api.Endpoints;
using Api.Services;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddDbContext<AppDb>(o => o.UseSqlServer(
    builder.Configuration.GetConnectionString("Leads"),
    sql => sql.EnableRetryOnFailure(3)));

builder.Services.ConfigureHttpJsonOptions(o =>
{
    o.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.CamelCase;
    o.SerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.Never;
});

builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme)
    .AddCookie(o =>
    {
        o.Cookie.Name = "shiplystic_session";
        o.Cookie.HttpOnly = true;
        o.Cookie.SameSite = SameSiteMode.Strict;
        o.ExpireTimeSpan = TimeSpan.FromDays(7);
        o.SlidingExpiration = true;
        // API: answer 401/403 instead of redirecting to a login page
        o.Events.OnRedirectToLogin = c => { c.Response.StatusCode = 401; return Task.CompletedTask; };
        o.Events.OnRedirectToAccessDenied = c => { c.Response.StatusCode = 403; return Task.CompletedTask; };
    });
builder.Services.AddAuthorizationBuilder()
    .AddPolicy("admin", p => p.RequireRole("admin"));

builder.Services.AddSingleton<JobRunner>();
builder.Services.AddSingleton<EnvSettings>();

var app = builder.Build();

app.UseDefaultFiles();
app.UseStaticFiles();
app.UseAuthentication();
app.UseAuthorization();

app.MapGet("/health", async (AppDb db) =>
{
    var ok = await db.Database.CanConnectAsync();
    return ok ? Results.Ok(new { status = "ok", database = "connected" })
              : Results.Problem("database unreachable", statusCode: 503);
});

var api = app.MapGroup("/api");
api.MapAuth();
var secured = api.MapGroup("").RequireAuthorization();
secured.MapLeads();
secured.MapCalling();
secured.MapAdmin();
secured.MapMetrics();
secured.MapPipeline();
secured.MapOutreach();
secured.MapSettings();
secured.MapCommand();

// React single-page app: every non-API route serves index.html
app.MapFallbackToFile("index.html");

app.Run();

public partial class Program;
