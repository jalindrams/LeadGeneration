namespace Api.Domain;

/// <summary>
/// Shiplystic call outcome codes. Mirror of app/pipeline/outcomes.py — keep both in sync.
/// </summary>
public record Outcome(string Code, string Label, bool Reached, string? ResponseStatus,
                      string? SuppressReason, string LeadCallStatus);

public static class Outcomes
{
    public static readonly Outcome[] All =
    [
        new("no_answer", "No answer", false, "no_response", null, "no_answer"),
        new("wrong_number", "Wrong number", false, "wrong_contact", "wrong_number", "closed"),
        new("not_owner", "Reached, not decision maker", true, null, null, "follow_up"),
        new("call_back", "Asked to call back", true, null, null, "follow_up"),
        new("already_with_competitor", "Happy with current shipper", true, "not_interested", null, "not_interested"),
        new("not_interested", "Not interested", true, "not_interested", null, "not_interested"),
        new("interested", "Interested", true, "interested", null, "interested"),
        new("demo_booked", "Demo booked", true, "interested", null, "interested"),
        new("signed_up", "Signed up", true, "converted", null, "closed"),
        new("do_not_call", "Asked not to be called", true, "not_interested", "do_not_call", "closed"),
    ];

    static readonly Dictionary<string, string> Legacy = new()
    {
        ["closed"] = "wrong_number", ["follow_up"] = "call_back",
    };

    public static Outcome? Find(string? code)
    {
        var c = (code ?? "").Trim().ToLowerInvariant();
        if (Legacy.TryGetValue(c, out var mapped)) c = mapped;
        return All.FirstOrDefault(o => o.Code == c);
    }

    public static readonly HashSet<string> Positive = ["interested", "demo_booked", "signed_up"];
}
