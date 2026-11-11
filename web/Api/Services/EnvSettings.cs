namespace Api.Services;

/// <summary>
/// Reads and writes whitelisted keys in the project .env (shared with the Python
/// workers). Secret values are never returned, only whether they are set.
/// </summary>
public class EnvSettings(IConfiguration cfg)
{
    public record Field(string Key, string Group, string Label, bool Secret);

    public static readonly Field[] Fields =
    [
        new("ECOM_DAILY_TARGET", "Pipeline", "Daily lead target", false),
        new("ECOM_WORKERS", "Pipeline", "Parallel workers", false),
        new("PIPELINE_ALERTS_ENABLED", "Pipeline", "Send alerts (Slack/email)", false),
        new("PLACES_MONTHLY_CALL_CAP", "Google Places", "Free-tier monthly call cap", false),
        new("GOOGLE_MAPS_API_KEY", "Google Places", "API key", true),
        new("PAID_TOTAL_CAP_INR", "Paid sources", "Total monthly cap (₹)", false),
        new("PAID_SERPER_CAP_INR", "Paid sources", "Serper cap (₹)", false),
        new("PAID_STORELEADS_CAP_INR", "Paid sources", "Store Leads cap (₹)", false),
        new("PAID_EASYLEADZ_CAP_INR", "Paid sources", "EasyLeadz cap (₹)", false),
        new("PAID_GOOGLE_PLACES_CAP_INR", "Paid sources", "Places overflow cap (₹)", false),
        new("SERPER_API_KEY", "Paid sources", "Serper API key", true),
        new("STORELEADS_API_KEY", "Paid sources", "Store Leads API key", true),
        new("STORELEADS_SUBSCRIPTION_INR", "Paid sources", "Store Leads subscription (₹/month)", false),
        new("WHATSAPP_ACCESS_TOKEN", "WhatsApp", "Access token", true),
        new("WHATSAPP_PHONE_NUMBER_ID", "WhatsApp", "Phone number ID", false),
        new("SMTP_HOST", "Email", "SMTP host", false),
        new("SMTP_PORT", "Email", "SMTP port", false),
        new("SMTP_USER", "Email", "SMTP user", false),
        new("SMTP_PASSWORD", "Email", "SMTP password", true),
        new("ALERT_EMAIL_TO", "Email", "Alert recipients", false),
        new("SLACK_WEBHOOK_URL", "Alerts", "Slack webhook", true),
        new("HUBSPOT_API_KEY", "CRM", "HubSpot token", true),
        new("OUTREACH_DAILY_LIMIT", "Outreach", "Daily send limit", false),
        new("OUTREACH_COOLDOWN_DAYS", "Outreach", "Cooldown days", false),
    ];

    string EnvPath => cfg["Python:EnvFile"] ?? Path.Combine(cfg["Python:WorkDir"] ?? ".", ".env");

    Dictionary<string, string> Read()
    {
        var d = new Dictionary<string, string>();
        if (!File.Exists(EnvPath)) return d;
        foreach (var line in File.ReadAllLines(EnvPath))
        {
            var i = line.IndexOf('=');
            if (i > 0 && !line.TrimStart().StartsWith('#')) d[line[..i].Trim()] = line[(i + 1)..];
        }
        return d;
    }

    public object Get()
    {
        var env = Read();
        return Fields.Select(f =>
        {
            env.TryGetValue(f.Key, out var v);
            return new { f.Key, f.Group, f.Label, f.Secret, isSet = !string.IsNullOrEmpty(v),
                         value = f.Secret ? null : v };
        });
    }

    public void Save(Dictionary<string, string?> changes)
    {
        var allowed = Fields.ToDictionary(f => f.Key);
        var lines = File.Exists(EnvPath) ? File.ReadAllLines(EnvPath).ToList() : [];
        foreach (var (key, value) in changes)
        {
            if (!allowed.TryGetValue(key, out var field)) throw new ArgumentException($"{key} not editable");
            if (field.Secret && string.IsNullOrEmpty(value)) continue;   // blank secret = keep existing
            var clean = (value ?? "").Replace("\r", "").Replace("\n", "");
            var idx = lines.FindIndex(l => l.StartsWith(key + "="));
            if (idx >= 0) lines[idx] = $"{key}={clean}"; else lines.Add($"{key}={clean}");
        }
        File.WriteAllLines(EnvPath, lines);
    }
}
