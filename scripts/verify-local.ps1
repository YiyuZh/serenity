param(
    [switch]$DockerBuild,
    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Body
    )
    Write-Host "==> $Name"
    & $Body
}

function Assert-NativeSuccess {
    param([string]$CommandName)
    if ($LASTEXITCODE -ne 0) {
        throw "$CommandName failed with exit code $LASTEXITCODE"
    }
}

function Set-DefaultEnv {
    param([string]$Name, [string]$Value)
    if (-not [Environment]::GetEnvironmentVariable($Name, "Process")) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

function Remove-GeneratedArtifacts {
    $targets = @(
        "frontend\node_modules",
        "frontend\dist",
        "backend\.pytest_cache"
    )
    $pycache = Get-ChildItem -Path (Join-Path $Root "backend") -Recurse -Force -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        ForEach-Object { $_.FullName }
    $allTargets = @($targets | ForEach-Object { Join-Path $Root $_ }) + $pycache

    foreach ($path in $allTargets) {
        $resolved = Resolve-Path -Path $path -ErrorAction SilentlyContinue
        if ($resolved -and $resolved.Path.StartsWith($Root.Path)) {
            Remove-Item -Path $resolved.Path -Recurse -Force
            Write-Host "removed $($resolved.Path)"
        }
    }
}

Push-Location $Root
try {
    if (-not $env:POSTGRES_PASSWORD) {
        $env:POSTGRES_PASSWORD = "local-verify-postgres-password"
    }
    if (-not $env:ADMIN_PASSWORD) {
        $env:ADMIN_PASSWORD = "local-verify-admin-password"
    }
    if (-not $env:JWT_SECRET) {
        $env:JWT_SECRET = "local-verify-jwt-secret-value-with-more-than-32-characters"
    }
    if ($DockerBuild) {
        Set-DefaultEnv "PYTHON_IMAGE" "docker.m.daocloud.io/library/python:3.11-slim"
        Set-DefaultEnv "NODE_IMAGE" "docker.m.daocloud.io/library/node:22-alpine"
        Set-DefaultEnv "NGINX_IMAGE" "docker.m.daocloud.io/library/nginx:1.27-alpine"
        Set-DefaultEnv "APT_MIRROR_HOST" "mirrors.tuna.tsinghua.edu.cn"
        Set-DefaultEnv "PIP_INDEX_URL" "https://pypi.tuna.tsinghua.edu.cn/simple"
        Set-DefaultEnv "PIP_TRUSTED_HOST" "pypi.tuna.tsinghua.edu.cn"
        Set-DefaultEnv "NPM_REGISTRY" "https://registry.npmmirror.com"
    }

    Invoke-Step "Backend tests" {
        Push-Location (Join-Path $Root "backend")
        try {
            python -m pytest -q
            Assert-NativeSuccess "python -m pytest -q"
            python -m compileall -q app
            Assert-NativeSuccess "python -m compileall -q app"
        } finally {
            Pop-Location
        }
    }

    Invoke-Step "Frontend typecheck and build" {
        Push-Location (Join-Path $Root "frontend")
        try {
            npm ci --legacy-peer-deps
            Assert-NativeSuccess "npm ci --legacy-peer-deps"
            npm run typecheck
            Assert-NativeSuccess "npm run typecheck"
            npm run build
            Assert-NativeSuccess "npm run build"
        } finally {
            Pop-Location
        }
    }

    Invoke-Step "Docker Compose config" {
        docker compose config | Out-Null
        Assert-NativeSuccess "docker compose config"
    }

    if ($DockerBuild) {
        Invoke-Step "Docker image build" {
            docker compose build backend frontend
            Assert-NativeSuccess "docker compose build backend frontend"
        }
    } else {
        Write-Host "==> Docker image build skipped. Run scripts\verify-local.ps1 -DockerBuild when Docker Hub or mirror access is ready."
    }

    Invoke-Step "Secret-like scan" {
        $rg = Get-Command rg -ErrorAction SilentlyContinue
        if (-not $rg) {
            Write-Warning "ripgrep is not installed; secret-like scan skipped"
            return
        }
        $pattern = 'sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|xox[baprs]-[0-9A-Za-z-]+|Bearer [A-Za-z0-9._-]{20,}|secret_id\s*=\s*["''][^"'']+|secret_key\s*=\s*["''][^"'']+'
        & rg -n --hidden --glob '!frontend/node_modules/**' --glob '!frontend/dist/**' --glob '!backend/.pytest_cache/**' --glob '!**/__pycache__/**' $pattern $Root
        if ($LASTEXITCODE -eq 0) {
            throw "Secret-like values were found. Review the output before committing."
        }
        if ($LASTEXITCODE -gt 1) {
            throw "Secret-like scan failed with exit code $LASTEXITCODE."
        }
        Write-Host "no secret-like matches"
    }
} finally {
    if (-not $KeepArtifacts) {
        Invoke-Step "Cleanup generated artifacts" {
            Remove-GeneratedArtifacts
        }
    }
    Pop-Location
}

Write-Host "All local verification steps passed."
