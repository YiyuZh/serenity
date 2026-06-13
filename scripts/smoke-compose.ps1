param(
    [string]$ProjectName = "serenity_smoke",
    [int]$BackendPort = 18000,
    [int]$FrontendPort = 15173,
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

function Set-DefaultEnv {
    param([string]$Name, [string]$Value)
    if (-not [Environment]::GetEnvironmentVariable($Name, "Process")) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

function Remove-SmokeResources {
    param([string]$Project)
    docker compose -p $Project down --remove-orphans
    $volumes = docker volume ls --filter "label=com.docker.compose.project=$Project" -q
    foreach ($volume in $volumes) {
        docker volume rm $volume | Out-Null
        Write-Host "removed temp volume $volume"
    }
}

Push-Location $Root
try {
    $existing = docker ps -a --format "{{.Names}}" | Where-Object { $_ -in @("serenity-backend", "serenity-frontend") }
    if ($existing) {
        throw "Refusing to run smoke test because these containers already exist: $($existing -join ', ')"
    }

    Set-DefaultEnv "APP_ENV" "production"
    Set-DefaultEnv "POSTGRES_PASSWORD" "smoke-postgres-password-123456"
    Set-DefaultEnv "ADMIN_PASSWORD" "smoke-admin-password-123456"
    Set-DefaultEnv "JWT_SECRET" "smoke-jwt-secret-value-with-more-than-32-characters"
    Set-DefaultEnv "CORS_ORIGINS" "http://127.0.0.1:$FrontendPort"
    Set-DefaultEnv "SERENITY_BACKEND_PORT" "$BackendPort"
    Set-DefaultEnv "SERENITY_FRONTEND_PORT" "$FrontendPort"
    Set-DefaultEnv "PYTHON_IMAGE" "docker.m.daocloud.io/library/python:3.11-slim"
    Set-DefaultEnv "NODE_IMAGE" "docker.m.daocloud.io/library/node:22-alpine"
    Set-DefaultEnv "NGINX_IMAGE" "docker.m.daocloud.io/library/nginx:1.27-alpine"
    Set-DefaultEnv "APT_MIRROR_HOST" "mirrors.tuna.tsinghua.edu.cn"
    Set-DefaultEnv "PIP_INDEX_URL" "https://pypi.tuna.tsinghua.edu.cn/simple"
    Set-DefaultEnv "PIP_TRUSTED_HOST" "pypi.tuna.tsinghua.edu.cn"
    Set-DefaultEnv "NPM_REGISTRY" "https://registry.npmmirror.com"

    $networkExists = docker network ls --format "{{.Name}}" | Where-Object { $_ -eq "shared_gateway" }
    if (-not $networkExists) {
        docker network create shared_gateway | Out-Null
    }

    docker compose -p $ProjectName up -d --build

    $backendOk = $false
    for ($i = 0; $i -lt 40; $i++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$BackendPort/api/health" -TimeoutSec 3
            if ($response.StatusCode -eq 200 -and $response.Content -match '"status"\s*:\s*"ok"') {
                $backendOk = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $backendOk) {
        docker compose -p $ProjectName ps
        docker compose -p $ProjectName logs --tail=160 backend
        docker compose -p $ProjectName logs --tail=160 init-db
        throw "Backend smoke healthcheck failed"
    }

    $frontend = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$FrontendPort" -TimeoutSec 5
    if ($frontend.StatusCode -ne 200 -or $frontend.Content -notmatch '<div id="app"></div>') {
        throw "Frontend smoke check failed"
    }

    docker compose -p $ProjectName ps
    Write-Host "Compose smoke test passed."
} finally {
    if (-not $KeepRunning) {
        Remove-SmokeResources -Project $ProjectName
    } else {
        Write-Host "Smoke stack kept running as requested. Stop it with: docker compose -p $ProjectName down --remove-orphans"
    }
    Pop-Location
}
