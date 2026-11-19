using Api.Services;

namespace Api.Endpoints;

public static class SettingsEndpoints
{
    public static void MapSettings(this RouteGroupBuilder api)
    {
        var g = api.MapGroup("/settings").RequireAuthorization("admin");
        g.MapGet("", (EnvSettings env) => Results.Ok(env.Get()));
        g.MapPost("", (Dictionary<string, string?> body, EnvSettings env) =>
        {
            try { env.Save(body); return Results.Ok(new { saved = body.Count, note = "Restart the Python worker to apply." }); }
            catch (ArgumentException e) { return Results.BadRequest(new { error = e.Message }); }
        });
    }
}
