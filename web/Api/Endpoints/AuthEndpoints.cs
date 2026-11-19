using System.Security.Claims;
using Api.Data;
using Api.Services;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.EntityFrameworkCore;

namespace Api.Endpoints;

public static class AuthEndpoints
{
    public record LoginIn(string Username, string Password);

    public static void MapAuth(this RouteGroupBuilder api)
    {
        var g = api.MapGroup("/auth");

        g.MapPost("/login", async (LoginIn body, AppDb db, HttpContext http) =>
        {
            var user = await db.Users.FirstOrDefaultAsync(u => u.Username == body.Username);
            bool ok = false;
            try { ok = user != null && BCrypt.Net.BCrypt.Verify(body.Password ?? "", user.PasswordHash); }
            catch (BCrypt.Net.SaltParseException) { ok = false; }
            if (!ok || user!.IsActive == false)
                return Results.Json(new { error = "Invalid username or password" }, statusCode: 401);
            var claims = new List<Claim>
            {
                new(ClaimTypes.NameIdentifier, user.Id.ToString()),
                new(ClaimTypes.Name, user.Username),
                new(ClaimTypes.Role, user.Role ?? "sales_rep"),
                new("full_name", user.FullName),
            };
            var principal = new ClaimsPrincipal(new ClaimsIdentity(claims, CookieAuthenticationDefaults.AuthenticationScheme));
            await http.SignInAsync(CookieAuthenticationDefaults.AuthenticationScheme, principal,
                new AuthenticationProperties { IsPersistent = true });
            return Results.Ok(new { user.Id, user.Username, user.FullName, role = user.Role });
        });

        g.MapPost("/logout", async (HttpContext http) =>
        {
            await http.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme);
            return Results.Ok();
        });

        g.MapGet("/me", (ClaimsPrincipal u) => Results.Ok(new
        {
            id = u.Id(), username = u.Identity!.Name, fullName = u.Name(),
            role = u.IsAdmin() ? "admin" : "sales_rep",
        })).RequireAuthorization();
    }
}
