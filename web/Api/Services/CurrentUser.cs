using System.Security.Claims;

namespace Api.Services;

public static class CurrentUser
{
    public static int Id(this ClaimsPrincipal u) => int.Parse(u.FindFirstValue(ClaimTypes.NameIdentifier)!);
    public static bool IsAdmin(this ClaimsPrincipal u) => u.IsInRole("admin");
    public static string Name(this ClaimsPrincipal u) => u.FindFirstValue("full_name") ?? u.Identity?.Name ?? "user";
}
