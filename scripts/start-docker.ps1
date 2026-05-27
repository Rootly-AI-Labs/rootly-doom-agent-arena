param(
    [int]$Port = $(if ($env:DOOM_ARENA_PORT) { [int]$env:DOOM_ARENA_PORT } else { 8001 }),
    [switch]$Dev,
    [switch]$NoOpenBrowser,
    [int]$TimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Fail($Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function EnsureFile($Path, $DefaultContent) {
    if (Test-Path -LiteralPath $Path -PathType Container) {
        $Children = @(Get-ChildItem -LiteralPath $Path -Force)
        if ($Children.Count -gt 0) {
            Fail "$Path is a directory and is not empty. Remove it or move its contents before starting Docker."
        }
        Remove-Item -LiteralPath $Path -Force
    }

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Set-Content -LiteralPath $Path -Value $DefaultContent -Encoding UTF8 -NoNewline
    }
}

function EnsureDirectory($Path) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        Fail "$Path is a file, but Docker needs it to be a directory."
    }

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker CLI was not found. Install Docker Desktop, then rerun this script."
}

try {
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Fail "Docker is installed, but the Docker daemon is not reachable. Start Docker Desktop and try again."
    }
}
catch {
    Fail "Docker is installed, but the Docker daemon is not reachable. Start Docker Desktop and try again."
}

$env:DOOM_ARENA_PORT = [string]$Port
$ComposeFiles = @("-f", "docker/docker-compose.yml")
if ($Dev) {
    $ComposeFiles += @("-f", "docker/docker-compose.dev.yml")
}

$ControllerTokensPath = Join-Path $RepoRoot "src/arena_controller_tokens.local.json"
$BenchmarkResultsPath = Join-Path $RepoRoot "benchmarks/results"
EnsureFile $ControllerTokensPath "{}"
EnsureDirectory $BenchmarkResultsPath

Write-Host "Starting Doom Arena Docker backend on http://127.0.0.1:$Port ..."
try {
    & docker compose @ComposeFiles up -d --build
    if ($LASTEXITCODE -ne 0) {
        Fail "docker compose up failed."
    }
}
catch {
    Fail "docker compose up failed. Confirm Docker Compose is available with 'docker compose version'."
}

$BaseUrl = "http://127.0.0.1:$Port"
$HealthUrl = "$BaseUrl/api/arena/health"
$Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$Ready = $false
$LastError = ""

while ((Get-Date) -lt $Deadline) {
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 2
        if ($Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500) {
            $Ready = $true
            break
        }
    }
    catch {
        $LastError = $_.Exception.Message
    }
    Start-Sleep -Milliseconds 500
}

if (-not $Ready) {
    Write-Host "Doom Arena did not become ready at $HealthUrl within $TimeoutSeconds seconds." -ForegroundColor Red
    if ($LastError) {
        Write-Host "Last readiness error: $LastError" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "Recent arena logs:"
    & docker compose @ComposeFiles logs --tail=80 arena
    exit 1
}

Write-Host "Doom Arena is ready: $BaseUrl/"
Write-Host "Host-side MCP env: DOOM_ARENA_BASE_URL=$BaseUrl"

if (-not $NoOpenBrowser) {
    try {
        Start-Process "$BaseUrl/"
    }
    catch {
        Write-Host "Could not open the browser automatically. Open $BaseUrl/ manually." -ForegroundColor Yellow
    }
}
