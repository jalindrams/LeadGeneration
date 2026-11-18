# Lead engine: separate IIS site + nightly worker on a shared Windows VM.
# Run once as Administrator. Prereqs: portable Python in C:\LeadEngine\python, ODBC Driver 18,
# .NET 10 Hosting Bundle, SQL Server (default instance, Windows login = sysadmin).
# Safe to re-run: it only touches C:\LeadEngine, the "LeadEngine" app pool/site and task.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = 'Tls12'
$ProgressPreference = 'SilentlyContinue'
$root = 'C:\LeadEngine'; $py = "$root\python\python.exe"; $app = "$root\app"; $site = "$root\site"
$data = "$root\data"; $port = 8090
$branch = 'claude/shiplystic-lead-generation-plan-a6442f'
$repo = 'https://github.com/jalindrams/LeadGeneration'
New-Item -ItemType Directory -Force $app, $site, $data, "$data\keys" | Out-Null

Write-Host '1/7 download code + API build'
$tmp = "$root\setup\dl"; Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue; New-Item -ItemType Directory $tmp | Out-Null
Invoke-WebRequest "$repo/archive/refs/heads/$branch.zip" -OutFile "$tmp\code.zip"
Expand-Archive "$tmp\code.zip" "$tmp\code" -Force
$src = (Get-ChildItem "$tmp\code" | Select-Object -First 1).FullName
$keep = if (Test-Path "$app\.env") { Get-Content "$app\.env" -Raw } else { $null }
robocopy $src $app /E /XD web .git /NFL /NDL /NJH /NJS | Out-Null
if ($keep) { Set-Content "$app\.env" $keep }
Invoke-WebRequest "$repo/raw/lead-engine-deploy/api.zip" -OutFile "$tmp\api.zip"
Stop-WebAppPool LeadEngine -ErrorAction SilentlyContinue; Start-Sleep 3
Add-Type -AssemblyName System.IO.Compression.FileSystem
$z = [IO.Compression.ZipFile]::OpenRead("$tmp\api.zip")   # entries use backslashes: normalise them
foreach ($e in $z.Entries) { $n = $e.FullName -replace '\\', '/'; if ($n.EndsWith('/')) { continue }
  $t = Join-Path $site $n; New-Item -ItemType Directory -Force (Split-Path $t) | Out-Null
  [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $t, $true) }
$z.Dispose()

Write-Host '2/7 python packages'
& $py -m pip install -q --no-warn-script-location -r "$app\requirements.txt" -r "$app\requirements-scrape.txt"
if ($LASTEXITCODE) { throw 'pip failed' }
$env:PLAYWRIGHT_BROWSERS_PATH = "$root\browsers"
[Environment]::SetEnvironmentVariable('PLAYWRIGHT_BROWSERS_PATH', "$root\browsers", 'Machine')
& $py -m playwright install chromium

Write-Host '3/7 database'
$secretFile = "$data\secrets.txt"
if (Test-Path $secretFile) { $sqlPw = (Get-Content $secretFile | Select-String '^SQL=').Line.Substring(4) }
else {
  $sqlPw = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
  Set-Content $secretFile "SQL=$sqlPw"
}
$setup = @"
import pyodbc, sys
pw = sys.argv[1]
c = pyodbc.connect('Driver={ODBC Driver 18 for SQL Server};Server=localhost;Trusted_Connection=yes;TrustServerCertificate=yes', autocommit=True)
q = c.cursor()
if not q.execute("select 1 from sys.databases where name='MicraftLeads'").fetchone():
    q.execute('CREATE DATABASE MicraftLeads')
q.execute('ALTER DATABASE MicraftLeads SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE')
if not q.execute("select 1 from sys.server_principals where name='leadengine'").fetchone():
    q.execute("CREATE LOGIN leadengine WITH PASSWORD='%s', CHECK_POLICY=OFF" % pw)
else:
    q.execute("ALTER LOGIN leadengine WITH PASSWORD='%s'" % pw)
q.execute('USE MicraftLeads')
if not q.execute("select 1 from sys.database_principals where name='leadengine'").fetchone():
    q.execute('CREATE USER leadengine FOR LOGIN leadengine')
q.execute("ALTER ROLE db_owner ADD MEMBER leadengine")
print('db ready')
"@
Set-Content "$root\setup\dbsetup.py" $setup
& $py "$root\setup\dbsetup.py" $sqlPw
if ($LASTEXITCODE) { throw 'db setup failed' }

Write-Host '4/7 config + tables + admin user'
$odbcConn = "mssql+pyodbc://leadengine:$sqlPw@localhost/MicraftLeads?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
if (-not (Test-Path "$app\.env")) {
  Set-Content "$app\.env" "DATABASE_URL=$odbcConn`r`nPLACES_MONTHLY_CALL_CAP=4000`r`nCSV_EXPORT_DIR=$app\exports"
}
(Get-Content "$app\.env") | Where-Object { $_ -notmatch '^PLAYWRIGHT' } | Set-Content "$app\.env"
New-Item -ItemType Directory -Force "$app\exports", "$app\logs" | Out-Null
Push-Location $app
& $py scripts\run_pipeline.py init
if ($LASTEXITCODE) { throw 'pipeline init failed' }
if (-not (Select-String $secretFile -Pattern '^ADMIN=' -Quiet)) {
  $adPw = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 14 | ForEach-Object { [char]$_ })
  Add-Content $secretFile "ADMIN=admin / $adPw"
  $mk = @"
import sys, bcrypt
sys.path.insert(0, '.')
from app.database import SessionLocal
from app.models import User
with SessionLocal() as db:
    if not db.query(User).filter(User.username == 'admin').first():
        db.add(User(username='admin', password_hash=bcrypt.hashpw(sys.argv[1].encode(), bcrypt.gensalt()).decode(), full_name='Administrator', role='admin'))
        db.commit()
print('admin ok')
"@
  Set-Content "$root\setup\mkadmin.py" $mk
  & $py "$root\setup\mkadmin.py" $adPw
}
Pop-Location

Write-Host '5/7 API settings'
$prod = @{
  ConnectionStrings = @{ Leads = "Server=localhost;Database=MicraftLeads;User Id=leadengine;Password=$sqlPw;TrustServerCertificate=True;MultipleActiveResultSets=True" }
  Python = @{ Exe = $py.Replace('\', '/'); WorkDir = $app.Replace('\', '/') }
  DataProtection = @{ KeyDir = "$data\keys" }
  Auth = @{ SecureCookie = $false }
} | ConvertTo-Json -Depth 4
Set-Content "$site\appsettings.Production.json" $prod

Write-Host '6/7 IIS site on port' $port
Import-Module WebAdministration
if (-not (Test-Path IIS:\AppPools\LeadEngine)) { New-WebAppPool LeadEngine | Out-Null }
Set-ItemProperty IIS:\AppPools\LeadEngine managedRuntimeVersion ''
Set-ItemProperty IIS:\AppPools\LeadEngine processModel.loadUserProfile $true
if (-not (Get-Website -Name LeadEngine)) { New-Website -Name LeadEngine -PhysicalPath $site -ApplicationPool LeadEngine -Port $port | Out-Null }
else { Set-ItemProperty IIS:\Sites\LeadEngine physicalPath $site }
$id = 'IIS AppPool\LeadEngine'
icacls $site /grant "${id}:(OI)(CI)RX" /T | Out-Null
icacls $data /grant "${id}:(OI)(CI)M" /T | Out-Null
icacls $app /grant "${id}:(OI)(CI)M" /T | Out-Null
icacls "$root\python" /grant "${id}:(OI)(CI)RX" /T | Out-Null
icacls "$root\browsers" /grant "${id}:(OI)(CI)RX" /T 2>$null | Out-Null
if (-not (Get-NetFirewallRule -DisplayName 'LeadEngine 8090' -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -DisplayName 'LeadEngine 8090' -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow | Out-Null
}
Start-WebAppPool LeadEngine -ErrorAction SilentlyContinue
Start-Website LeadEngine -ErrorAction SilentlyContinue

Write-Host '7/7 nightly worker task'
$bat = "$root\run_worker.bat"
Set-Content $bat "@echo off`r`ncd /d $app`r`nset PYTHONIOENCODING=utf-8`r`nset PLAYWRIGHT_BROWSERS_PATH=$root\browsers`r`n`"$py`" scripts\pipeline_worker.py >> exports\pipeline_worker.log 2>&1"
$act = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $app
$trg = New-ScheduledTaskTrigger -AtStartup
$set = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
Register-ScheduledTask -TaskName 'LeadEngine Worker' -Action $act -Trigger $trg -Settings $set -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
Start-ScheduledTask 'LeadEngine Worker'

Start-Sleep 5
try { (Invoke-WebRequest "http://localhost:$port/health" -UseBasicParsing).Content } catch { "health check failed: $_" }
Write-Host 'DEPLOY FINISHED'
