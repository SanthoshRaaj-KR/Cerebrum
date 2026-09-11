<#
    Start Cerebrum. One command, everything up.

        .\start.ps1            bridge + web console, opens the browser
        .\start.ps1 -Check     verify keys, then exit
        .\start.ps1 -NoWeb     bridge only (the console is already running)
        .\start.ps1 -Force     start even though the checks failed

    First run creates the virtualenv and installs both dependency sets, so it
    takes a few minutes. After that it is a few seconds.

    Ctrl-C stops everything, including the Node processes npm spawns.
#>

param([switch]$Check, [switch]$NoWeb, [switch]$Force)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
$backend = Join-Path $root 'backend'
$web = Join-Path $root 'web'

function Say($text, $colour = 'Gray') { Write-Host "  $text" -ForegroundColor $colour }

function Wait-Port([int]$port, [int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $client = New-Object Net.Sockets.TcpClient
            $client.Connect('127.0.0.1', $port)
            $client.Close()
            return $true
        } catch {
            Start-Sleep -Milliseconds 400
        }
    }
    return $false
}

# ---------------------------------------------------------------- python

if (-not (Test-Path $py)) {
    Say "No virtualenv here yet. Building one - this takes a few minutes." Cyan
    python -m venv (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0) {
        Say "Could not create the virtualenv. Is Python on your PATH?" Yellow
        exit 1
    }
    & $py -m pip install --upgrade pip --quiet
    & $py -m pip install -r (Join-Path $root 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { Say "pip install failed." Yellow; exit 1 }
}

# ------------------------------------------------------------------ keys

$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $root '.env.example') $envFile
    Say ""
    Say "Created .env from the template. Put your keys in it, then run again:" Yellow
    Say "  CEREBRAS_API_KEY   cloud.cerebras.ai"
    Say "  DEEPGRAM_API_KEY   console.deepgram.com"
    Say "  TAVILY_API_KEY     tavily.com"
    Say ""
    exit 1
}

$env:PYTHONPATH = $backend
if ($Check) { & $py -m interview_agent.doctor; exit $LASTEXITCODE }

# --------------------------------------------------------------- console

$wantWeb = -not $NoWeb
if ($wantWeb -and -not (Test-Path (Join-Path $web 'node_modules'))) {
    Say ""
    Say "Installing the console's dependencies - once only." Cyan
    Push-Location $web
    try {
        & npm.cmd install
        if ($LASTEXITCODE -ne 0) {
            Say "npm install failed. Starting without the console." Yellow
            $wantWeb = $false
        }
    } finally { Pop-Location }
}

# ----------------------------------------------------------- pre-flight

# Credentials are checked before anything starts, so a bad key surfaces here
# rather than as a dead mic mid-interview.
Say ""
Say "Checking setup..." Cyan
& $py -m interview_agent.doctor
$healthy = $LASTEXITCODE -eq 0

if (-not $healthy) {
    if (-not $Force) {
        Say ""
        Say "Not starting - the checks above failed." Yellow
        Say "Fix them, or run with -Force to bring up the console anyway."
        Say ""
        exit 1
    }
    Say ""
    Say "Checks failed; starting anyway because you asked (-Force)." Yellow
    Say "The interviewer cannot hold a session until they pass."
}

# ------------------------------------------------------------------ up

$procs = @()
try {
    Say ""
    Say "Bridge   http://127.0.0.1:7332" Cyan
    # -u so the bridge's log lines appear here as they happen, rather than
    # sitting in a buffer because stdout is not a terminal.
    # $env:PYTHONPATH was set above (before -Check); Start-Process inherits
    # the parent process's environment, so the child sees it too.
    $procs += Start-Process -FilePath $py -ArgumentList '-u', '-m', 'interview_agent.bridge' `
        -WorkingDirectory $root -PassThru -NoNewWindow

    if (-not (Wait-Port 7332 20)) { throw "The bridge did not come up on 7332." }

    if ($wantWeb) {
        Say "Console  http://localhost:3000" Cyan
        $procs += Start-Process -FilePath 'npm.cmd' -ArgumentList 'run', 'dev' `
            -WorkingDirectory $web -PassThru -NoNewWindow

        if (Wait-Port 3000 90) {
            Start-Process 'http://localhost:3000'
        } else {
            Say "The console is taking its time; open http://localhost:3000 yourself." Yellow
        }
    }

    Say ""
    Say "Cerebrum is up. Ctrl-C to stop." Green
    Say ""

    while ($true) {
        Start-Sleep -Seconds 1
        foreach ($p in $procs) {
            if ($p.HasExited) { throw "A process exited (code $($p.ExitCode))." }
        }
    }
}
finally {
    Say ""
    Say "Stopping..." Cyan
    foreach ($p in $procs) {
        if (-not $p.HasExited) {
            # /T because npm spawns the Next server as a child; killing only
            # npm leaves node holding port 3000.
            & taskkill /T /F /PID $p.Id 2>&1 | Out-Null
        }
    }
}
