using System.Collections.Concurrent;
using System.Diagnostics;

namespace Api.Services;

/// <summary>
/// Starts whitelisted Python worker commands (scrapers, pipeline, outreach) as
/// background processes. Only the commands in Allowed can run; arguments are
/// validated, never passed through a shell.
/// </summary>
public class JobRunner(IConfiguration cfg, ILogger<JobRunner> log)
{
    public record Job(string Id, string Name, string[] Args, DateTime StartedAt)
    {
        public string Status { get; set; } = "running";
        public int? ExitCode { get; set; }
        public DateTime? FinishedAt { get; set; }
        public string LogPath { get; set; } = "";
    }

    // name -> (script, fixed leading args, allowed extra flags)
    static readonly Dictionary<string, (string Script, string[] Fixed)> Allowed = new()
    {
        ["pipeline_daily"] = ("scripts/run_pipeline.py", ["daily"]),
        ["pipeline_process"] = ("scripts/run_pipeline.py", ["process"]),
        ["pipeline_batch"] = ("scripts/run_pipeline.py", ["batch"]),
        ["pipeline_discover"] = ("scripts/run_pipeline.py", ["discover"]),
        ["pipeline_rank"] = ("scripts/run_pipeline.py", ["rank"]),
        ["scraper"] = ("scripts/run_scraper.py", []),
        ["outreach_send"] = ("scripts/run_outreach.py", []),
        ["rescore"] = ("scripts/rescore_leads.py", []),
    };
    static readonly HashSet<string> Sources =
    [
        "shopify_app_reviews", "tranco_in", "tranco_com", "commoncrawl", "new_domains",
        "amazon_sellers", "serper_search", "storeleads",
        "indiamart", "google_maps", "tradeindia", "nabl", "aipma", "iba", "oem_dealers",
    ];

    readonly ConcurrentDictionary<string, Job> _jobs = new();
    readonly ConcurrentDictionary<string, Process> _procs = new();

    public IEnumerable<Job> List() => _jobs.Values.OrderByDescending(j => j.StartedAt).Take(30);

    public Job Start(string name, Dictionary<string, string>? options = null)
    {
        if (!Allowed.TryGetValue(name, out var spec))
            throw new ArgumentException($"job '{name}' is not allowed");
        if (_jobs.Values.Any(j => j.Name == name && j.Status == "running"))
            throw new InvalidOperationException($"job '{name}' is already running");

        var args = new List<string> { spec.Script };
        args.AddRange(spec.Fixed);
        foreach (var (k, v) in options ?? [])
        {
            switch (k)
            {
                case "source" when Sources.Contains(v): args.AddRange(["--source", v]); break;
                case "limit" or "target" when int.TryParse(v, out var n) && n is > 0 and <= 100000:
                    args.AddRange([$"--{k}", n.ToString()]); break;
                case "product" when System.Text.RegularExpressions.Regex.IsMatch(v, "^[a-z]{2,20}$"):
                    args.AddRange(["--product", v]); break;
                case "yes" when v == "true": args.Add("--yes"); break;
                case "dry_run" when v == "true": args.Add("--dry-run"); break;
                case "preview" when v == "true": args.Add("--preview-templates"); break;
                case "tier" when v is "hot" or "warm" or "all": args.AddRange(["--tier", v]); break;
                default: throw new ArgumentException($"option '{k}' not allowed");
            }
        }

        var root = cfg["Python:WorkDir"] ?? Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../.."));
        var exe = cfg["Python:Exe"] ?? "python";
        var id = $"{DateTime.Now:yyyyMMdd-HHmmss}-{name}";
        var logDir = Path.Combine(root, "exports", "jobs");
        Directory.CreateDirectory(logDir);
        var job = new Job(id, name, args.ToArray(), DateTime.Now) { LogPath = Path.Combine(logDir, id + ".log") };

        var psi = new ProcessStartInfo(exe) { WorkingDirectory = root, UseShellExecute = false,
            RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true };
        foreach (var a in args) psi.ArgumentList.Add(a);
        psi.Environment["PYTHONIOENCODING"] = "utf-8";

        var p = new Process { StartInfo = psi, EnableRaisingEvents = true };
        var writer = new StreamWriter(job.LogPath) { AutoFlush = true };
        p.OutputDataReceived += (_, e) => { if (e.Data != null) lock (writer) writer.WriteLine(e.Data); };
        p.ErrorDataReceived += (_, e) => { if (e.Data != null) lock (writer) writer.WriteLine(e.Data); };
        p.Exited += (_, _) =>
        {
            job.ExitCode = p.ExitCode;
            job.Status = p.ExitCode == 0 ? "ok" : "failed";
            job.FinishedAt = DateTime.Now;
            lock (writer) writer.Dispose();
            _procs.TryRemove(id, out _);
        };
        p.Start();
        p.BeginOutputReadLine();
        p.BeginErrorReadLine();
        _jobs[id] = job;
        _procs[id] = p;
        log.LogInformation("job started {Id} {Args}", id, string.Join(' ', args));
        return job;
    }

    public bool Stop(string id)
    {
        if (!_procs.TryGetValue(id, out var p)) return false;
        p.Kill(entireProcessTree: true);
        if (_jobs.TryGetValue(id, out var j)) j.Status = "halted";
        return true;
    }

    public string Tail(string id, int lines = 80)
    {
        if (!_jobs.TryGetValue(id, out var j) || !File.Exists(j.LogPath)) return "";
        using var fs = new FileStream(j.LogPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        using var sr = new StreamReader(fs);
        var all = sr.ReadToEnd().Split('\n');
        return string.Join('\n', all.TakeLast(lines));
    }
}
