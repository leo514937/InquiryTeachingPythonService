[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8010,

    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 5173,

    [string]$ListenAddress = "127.0.0.1",

    [switch]$Install,
    [switch]$Restart,
    [switch]$NoReload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:RootDir = if ($PSScriptRoot) {
    $PSScriptRoot
} else {
    Split-Path -Parent $MyInvocation.MyCommand.Path
}
$script:FrontendDir = Join-Path $script:RootDir "frontend"
$script:LogDir = Join-Path $script:RootDir ".logs"
$script:StartedProcesses = [System.Collections.Generic.List[System.Diagnostics.Process]]::new()

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-ListenerPids {
    param([int]$Port)

    try {
        return @(
            Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
                Select-Object -ExpandProperty OwningProcess -Unique
        )
    } catch {
        $pids = @()
        foreach ($line in (netstat -ano -p tcp | Select-String "LISTENING")) {
            $parts = ($line.Line -split "\s+") | Where-Object { $_ }
            if ($parts.Count -ge 5 -and $parts[1] -match ":$Port$" -and $parts[-1] -match "^\d+$") {
                $pids += [int]$parts[-1]
            }
        }
        return @($pids | Select-Object -Unique)
    }
}

function Test-HttpEndpoint {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 2
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $TimeoutSeconds
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Wait-HttpEndpoint {
    param(
        [string]$Name,
        [string]$Url,
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSeconds = 45
    )

    for ($attempt = 0; $attempt -lt $TimeoutSeconds; $attempt++) {
        if (Test-HttpEndpoint -Url $Url) {
            return $true
        }
        if ($null -ne $Process -and $Process.HasExited) {
            return $false
        }
        Start-Sleep -Seconds 1
    }

    Write-Warning "$Name 未在 $TimeoutSeconds 秒内就绪：$Url"
    return $false
}

function Stop-Listeners {
    param([int]$Port)

    $pids = @(Get-ListenerPids -Port $Port)
    foreach ($processId in $pids) {
        Write-Step "停止端口 $Port 上的进程 PID=$processId"
        Stop-Process -Id $processId -Force -ErrorAction Stop
    }

    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        if (@(Get-ListenerPids -Port $Port).Count -eq 0) {
            return
        }
        Start-Sleep -Seconds 1
    }

    throw "端口 $Port 未能释放。"
}

function Resolve-SystemPython {
    foreach ($name in @("python", "python3", "py")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source) {
            return $command.Source
        }
    }
    throw "未找到 Python。请安装 Python 3.11+，或先手动创建 .venv。"
}

function Resolve-ProjectPython {
    $venvPython = Join-Path $script:RootDir ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }

    if (-not $Install) {
        throw "未找到 .venv。请先执行 .\start-dev.ps1 -Install 创建环境并安装依赖。"
    }

    $systemPython = Resolve-SystemPython
    Write-Step "创建 Python 虚拟环境"
    if ([System.IO.Path]::GetFileName($systemPython) -eq "py.exe") {
        & $systemPython -3 -m venv (Join-Path $script:RootDir ".venv")
    } else {
        & $systemPython -m venv (Join-Path $script:RootDir ".venv")
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        throw "Python 虚拟环境创建失败。"
    }
    return $venvPython
}

function Resolve-Npm {
    $command = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        return $command.Source
    }

    $node = Get-Command "node.exe" -ErrorAction SilentlyContinue
    if ($node -and $node.Source) {
        $besideNode = Join-Path (Split-Path -Parent $node.Source) "npm.cmd"
        if (Test-Path -LiteralPath $besideNode) {
            return $besideNode
        }
    }

    throw "未找到 npm.cmd。请安装 Node.js 并将其加入 PATH。"
}

function Assert-Dependencies {
    param(
        [string]$PythonExe,
        [string]$NpmExe
    )

    & $PythonExe -c "import fastapi, uvicorn" 2>$null
    if ($LASTEXITCODE -ne 0) {
        if (-not $Install) {
            throw "Python 依赖不完整。请执行 .\start-dev.ps1 -Install。"
        }
        Write-Step "安装 Python 依赖"
        & $PythonExe -m pip install -r (Join-Path $script:RootDir "requirements.txt")
        if ($LASTEXITCODE -ne 0) {
            throw "Python 依赖安装失败。"
        }
    }

    $nodeModules = Join-Path $script:FrontendDir "node_modules"
    if (-not (Test-Path -LiteralPath $nodeModules)) {
        if (-not $Install) {
            throw "前端依赖未安装。请执行 .\start-dev.ps1 -Install。"
        }
        Write-Step "安装前端依赖"
        & $NpmExe --prefix $script:FrontendDir ci
        if ($LASTEXITCODE -ne 0) {
            throw "前端依赖安装失败。"
        }
    }
}

function Start-LoggedProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$LogPrefix
    )

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $stdout = Join-Path $script:LogDir "$LogPrefix-$timestamp.log"
    $stderr = Join-Path $script:LogDir "$LogPrefix-$timestamp.error.log"
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden `
        -PassThru

    $script:StartedProcesses.Add($process)
    return @{
        Process = $process
        Stdout = $stdout
        Stderr = $stderr
    }
}

function Show-LogTail {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        Write-Host "---- $Path"
        Get-Content -LiteralPath $Path -Tail 30 -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $script:FrontendDir "package.json"))) {
    throw "未找到 frontend\package.json，请从项目根目录运行此脚本。"
}

New-Item -ItemType Directory -Force -Path $script:LogDir | Out-Null
$pythonExe = Resolve-ProjectPython
$npmExe = Resolve-Npm
Assert-Dependencies -PythonExe $pythonExe -NpmExe $npmExe

if ($Restart) {
    Stop-Listeners -Port $BackendPort
    Stop-Listeners -Port $FrontendPort
}

$backendHealth = "http://127.0.0.1:$BackendPort/health"
$frontendHealth = "http://127.0.0.1:$FrontendPort/"
$backendRunning = @(Get-ListenerPids -Port $BackendPort).Count -gt 0
$frontendRunning = @(Get-ListenerPids -Port $FrontendPort).Count -gt 0

if ($backendRunning -and -not (Test-HttpEndpoint -Url $backendHealth)) {
    throw "端口 $BackendPort 已被其他进程占用。请更换 -BackendPort，或确认后使用 -Restart。"
}
if ($frontendRunning -and -not (Test-HttpEndpoint -Url $frontendHealth)) {
    throw "端口 $FrontendPort 已被其他进程占用。请更换 -FrontendPort，或确认后使用 -Restart。"
}

if (-not $backendRunning) {
    Write-Step "初始化数据库和本地配置"
    & $pythonExe (Join-Path $script:RootDir "bootstrap.py") | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "项目初始化失败。"
    }
}

$env:FRONTEND_ORIGIN = "http://127.0.0.1:$FrontendPort,http://localhost:$FrontendPort"
$env:VITE_API_BASE = "http://127.0.0.1:$BackendPort"

$backendLaunch = $null
$frontendLaunch = $null

try {
    if ($backendRunning) {
        Write-Step "后端已经运行，直接复用"
    } else {
        Write-Step "启动 FastAPI 后端"
        $backendArgs = @(
            "-m", "uvicorn", "app.main:app",
            "--host", $ListenAddress,
            "--port", $BackendPort.ToString()
        )
        if (-not $NoReload) {
            $backendArgs += "--reload"
        }
        $backendLaunch = Start-LoggedProcess `
            -FilePath $pythonExe `
            -ArgumentList $backendArgs `
            -WorkingDirectory $script:RootDir `
            -LogPrefix "backend"
    }

    if ($frontendRunning) {
        Write-Step "前端已经运行，直接复用"
    } else {
        Write-Step "启动 Vue/Vite 前端"
        $frontendLaunch = Start-LoggedProcess `
            -FilePath $npmExe `
            -ArgumentList @(
                "run", "dev", "--",
                "--host", $ListenAddress,
                "--port", $FrontendPort.ToString(),
                "--strictPort"
            ) `
            -WorkingDirectory $script:FrontendDir `
            -LogPrefix "frontend"
    }

    $backendProcess = if ($null -ne $backendLaunch) { $backendLaunch.Process } else { $null }
    $frontendProcess = if ($null -ne $frontendLaunch) { $frontendLaunch.Process } else { $null }
    $backendReady = Wait-HttpEndpoint -Name "后端" -Url $backendHealth -Process $backendProcess
    $frontendReady = Wait-HttpEndpoint -Name "前端" -Url $frontendHealth -Process $frontendProcess

    if (-not $backendReady -or -not $frontendReady) {
        if ($null -ne $backendLaunch) {
            Show-LogTail -Path $backendLaunch.Stdout
            Show-LogTail -Path $backendLaunch.Stderr
        }
        if ($null -ne $frontendLaunch) {
            Show-LogTail -Path $frontendLaunch.Stdout
            Show-LogTail -Path $frontendLaunch.Stderr
        }
        throw "项目启动失败，已输出最近的错误日志。"
    }

    $state = @{
        started_at = (Get-Date).ToString("o")
        backend_port = $BackendPort
        frontend_port = $FrontendPort
        backend_pids = @(Get-ListenerPids -Port $BackendPort)
        frontend_pids = @(Get-ListenerPids -Port $FrontendPort)
    }
    $state | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:LogDir "dev-processes.json") -Encoding UTF8

    Write-Host ""
    Write-Host "项目启动成功" -ForegroundColor Green
    Write-Host "前端地址： http://127.0.0.1:$FrontendPort"
    Write-Host "后端地址： http://127.0.0.1:$BackendPort"
    Write-Host "接口文档： http://127.0.0.1:$BackendPort/docs"
    if ($null -ne $backendLaunch) {
        Write-Host "后端日志： $($backendLaunch.Stdout)"
        Write-Host "后端错误： $($backendLaunch.Stderr)"
    }
    if ($null -ne $frontendLaunch) {
        Write-Host "前端日志： $($frontendLaunch.Stdout)"
        Write-Host "前端错误： $($frontendLaunch.Stderr)"
    }
} catch {
    foreach ($process in $script:StartedProcesses) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    throw
}
