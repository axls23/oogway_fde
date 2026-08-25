Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

function Log([string]$Message) {
    Write-Host "==> $Message"
}

function Warn([string]$Message) {
    Write-Warning "launch-system: warning: $Message"
}

function Fail([string]$Message) {
    throw "launch-system: $Message"
}

function Set-EnvFromDotEnv([string]$Path) {
    if (-not (Test-Path $Path)) { return }

    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }

        $separatorIndex = $trimmed.IndexOf('=')
        if ($separatorIndex -lt 0) { continue }

        $key = $trimmed.Substring(0, $separatorIndex).Trim()
        $value = $trimmed.Substring($separatorIndex + 1).Trim()
        $value = $value.Trim('"').Trim("'")

        if (-not [string]::IsNullOrWhiteSpace($key)) {
            [System.Environment]::SetEnvironmentVariable($key, $value)
            Set-Item -Path "Env:$key" -Value $value
        }
    }
}

function Invoke-HealthCheck([string]$Url, [int]$TimeoutSeconds = 2) {
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec $TimeoutSeconds -UseBasicParsing -ErrorAction Stop
        return $response.Content
    }
    catch {
        return '{}'
    }
}

if (-not (Test-Path '.env')) {
    Log 'No .env — copying .env.example (defaults work as-is, no API key required)'
    Copy-Item '.env.example' '.env'
}

Set-EnvFromDotEnv '.env'

if (-not (Test-Path 'ingest/corpus/episodes')) {
    Log 'Cloning transcript corpus (not vendored, ~10MB)'
    git clone --depth 1 https://github.com/ChatPRD/lennys-podcast-transcripts.git ingest/corpus
}

$compose = @()
if (Get-Command docker -ErrorAction SilentlyContinue) {
    try {
        & docker info *> $null
        & docker compose version *> $null
        $compose = @('docker', 'compose')
    }
    catch {
        $compose = @()
    }
}

if (-not $compose) {
    if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
        $compose = @('docker-compose')
        if (-not (Test-Path env:DOCKER_HOST)) {
            $sock = "/run/user/$([System.Environment]::GetEnvironmentVariable('UID','Process'))/podman/podman.sock"
            if (-not (Test-Path $sock)) {
                if (Get-Command podman -ErrorAction SilentlyContinue) {
                    Log 'Enabling rootless podman Docker API socket'
                    & podman system service --time=0 unix:///run/user/$([System.Environment]::GetEnvironmentVariable('UID','Process'))/podman/podman.sock > $null 2>&1 &
                }
            }
            if (Test-Path $sock) {
                $env:DOCKER_HOST = "unix://$sock"
            }
        }
    }
}

if (-not $compose) {
    Fail "Neither the 'docker compose' plugin nor the standalone 'docker-compose' binary is available."
}

Log "Compose: $($compose -join ' ') (DOCKER_HOST=$($env:DOCKER_HOST ?? 'default'))"

$ollamaReady = $false
try {
    $null = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    $ollamaReady = $true
    Log 'Ollama already running — if api/agent later report ollama:down, it is almost certainly bound to 127.0.0.1 only. Restart it with: OLLAMA_HOST=0.0.0.0:11434 ollama serve'
}
catch {
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Fail 'Ollama is not installed. Install it from https://ollama.com, then re-run.'
    }

    Log 'Starting Ollama, bound to 0.0.0.0 so containers can reach it via host.docker.internal'
    $env:OLLAMA_HOST = '0.0.0.0:11434'
    Start-Process -FilePath 'ollama' -ArgumentList 'serve' -WindowStyle Hidden

    for ($i = 0; $i -lt 30; $i++) {
        try {
            $null = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
            $ollamaReady = $true
            break
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    if (-not $ollamaReady) {
        Fail 'Ollama did not come up in time. Check the Ollama logs and ensure the service is reachable on :11434.'
    }
}

function Ensure-Model([string]$ModelName) {
    try {
        $tagsJson = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -UseBasicParsing | Select-Object -ExpandProperty Content
        $tags = $tagsJson | ConvertFrom-Json
        $names = @($tags.models | ForEach-Object { $_.name })
        if ($names -contains $ModelName) { return }
    }
    catch {
        # ignore and pull the model
    }

    Log "Pulling $ModelName (first run only — several GB, can take a few minutes)"
    & ollama pull $ModelName
}

$llmModel = if ($env:LLM_MODEL) { $env:LLM_MODEL } else { 'qwen2.5:7b-instruct' }
$embedModel = if ($env:EMBED_MODEL) { $env:EMBED_MODEL } else { 'nomic-embed-text' }
Ensure-Model $llmModel
Ensure-Model $embedModel

if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue) -and [int]($env:MODEL_TIMEOUT_S ?? 60) -lt 120) {
    Warn "No GPU detected and MODEL_TIMEOUT_S=$($env:MODEL_TIMEOUT_S ?? 60) — CPU-only inference of a 7B model routinely needs 120-200s for a full turn. Consider raising MODEL_TIMEOUT_S in .env."
}

Log 'Building and starting db, api, agent, web'
if ($compose.Count -eq 1) {
    & $compose[0] up --build -d
}
else {
    & $compose[0] $compose[1] up --build -d
}

$deps = '{}'
for ($i = 0; $i -lt 60; $i++) {
    $deps = Invoke-HealthCheck 'http://localhost:8000/health/deps' 2
    if ($deps -match '"db":"ok"' -and $deps -match '"ollama":"ok"' -and $deps -match '"agent":"ok"') {
        break
    }
    Start-Sleep -Seconds 2
}

Write-Host $deps
if ($deps -notmatch '"db":"ok"' -or $deps -notmatch '"ollama":"ok"' -or $deps -notmatch '"agent":"ok"') {
    Fail "Services did not all report healthy in time. Check: $($compose -join ' ') logs"
}

$config = Invoke-HealthCheck 'http://localhost:8000/config' 2
$episodeMatch = [regex]::Match($config, '"episode_count"\s*:\s*(\d+)')
if (-not $episodeMatch.Success -or [int]$episodeMatch.Groups[1].Value -eq 0) {
    Log '0 episodes ingested — every question will abstain until you run one of:'
    Log '  make ingest-subset      # curated topics, faster'
    Log '  make ingest             # full corpus (303 episodes, ~8,531 chunks; 1 currently fails to parse)'
}

Log 'Up: http://localhost:5173  (api http://localhost:8000, agent http://localhost:8100)'
Log "Logs:  $($compose -join ' ') logs -f"
Log "Stop:  $($compose -join ' ') down"
