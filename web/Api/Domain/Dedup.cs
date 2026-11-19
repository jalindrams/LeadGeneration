using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace Api.Domain;

/// <summary>Exact port of app/processing/dedup.py so C# and Python produce the same hashes.</summary>
public static class Dedup
{
    static readonly string[] Suffixes = ["pvt ltd", "pvt. ltd.", "private limited", "limited", "ltd", "ltd.",
                                         "llp", "inc", "inc.", "corporation", "corp", "corp."];

    public static string NormalizePhone(string? phone)
    {
        if (string.IsNullOrEmpty(phone)) return "";
        var d = Regex.Replace(phone, @"[^\d]", "");
        if (d.Length > 10 && d.StartsWith("91")) d = d[2..];
        if (d.Length > 10 && d.StartsWith('0')) d = d[1..];
        return d.Length >= 10 ? d[^10..] : d;
    }

    public static string NormalizeCompany(string? name)
    {
        if (string.IsNullOrEmpty(name)) return "";
        var n = name.ToLowerInvariant().Trim();
        foreach (var s in Suffixes)
            n = Regex.Replace(n, $@"\s*{Regex.Escape(s)}\s*$", "");
        return Regex.Replace(n, @"\s+", " ").Trim();
    }

    public static string Hash(string company, string? phone = null, string? gst = null, string? location = null)
    {
        string key;
        if (!string.IsNullOrWhiteSpace(gst)) key = $"gst:{gst.Trim().ToUpperInvariant()}";
        else if (!string.IsNullOrWhiteSpace(phone)) key = $"phone_company:{NormalizePhone(phone)}:{NormalizeCompany(company)}";
        else key = $"company_location:{NormalizeCompany(company)}:{(location ?? "").ToLowerInvariant().Trim()}";
        return Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(key)));
    }

    /// <summary>10-digit Indian mobile (starts 6-9) or null. Mirror of app/pipeline/verify.py.</summary>
    public static string? NormalizeMobile(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        var compact = raw.Replace(" ", "");
        if (Regex.IsMatch(raw, @"^\s*(\+?91[\s-]*)?1[89]00") || compact.StartsWith("1800") || compact.StartsWith("1860"))
            return null;
        var d = Regex.Replace(raw, @"\D", "");
        if (d.Length == 12 && d.StartsWith("91")) d = d[2..];
        else if (d.Length == 11 && d.StartsWith('0')) d = d[1..];
        else if (d.Length == 13 && d.StartsWith("091")) d = d[3..];
        if (d.Length != 10 || "6789".IndexOf(d[0]) < 0) return null;
        if (d.Distinct().Count() <= 2) return null;
        string[] placeholders = ["9876543210", "9123456789", "9000000000", "8888888888", "7777777777",
                                 "9012345678", "9898989898", "1234567890"];
        return placeholders.Contains(d) ? null : d;
    }
}
