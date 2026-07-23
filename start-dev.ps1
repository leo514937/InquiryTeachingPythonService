$ErrorActionPreference = "Stop"

function Write-Info($message) {
  Write-Host $message
}

function Test-Port($port) {
  try {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
  } catch {
    return $false
  }
}

function Get-PortPids($port) {
  $lines = netstat -ano | Select-String ":$port"
  if (-not $lines) {
    return @()
  }
  $pids = @()
  foreach ($line in $lines) {
    $parts = ($line.Line -split "\s+") | Where-Object { $_ }
    if ($parts.Count -lt 5) {
      continue
    }
    $pidText = $parts[-1]
    if ($pidText -match '^\d+$') {
      $pids += [int]$pidText
    }
  }
  return $pids | Select-Object -Unique
}

function Stop-PortProcess($port) {
  $pids = Get-PortPids $port
  if (-not $pids -or $pids.Count -eq 0) {
    return
  }

  Write-Info "清理端口 $port 上的旧进程..."
  foreach ($processId in $pids) {
    try {
      Stop-Process -Id $processId -Force -ErrorAction Stop
      continue
    } catch {
    }

    try {
      & cmd.exe /c "taskkill /PID $processId /F /T" 2>$null | Out-Null
    } catch {
    }
  }
}

function Wait-PortFree($port, $timeoutSeconds = 15) {
  for ($i = 0; $i -lt $timeoutSeconds; $i++) {
    if (-not (Test-Port $port)) {
      return $true
    }
    Stop-PortProcess $port
    Start-Sleep -Seconds 1
  }
  return -not (Test-Port $port)
}

function Resolve-PythonExe {
  $candidates = @()

  if ($env:PYTHON_BIN) {
    $candidates += $env:PYTHON_BIN
  }

  $rootPython = Join-Path $script:RootDir ".venv\Scripts\python.exe"
  $candidates += $rootPython
  $candidates += "C:\Users\14011\AppData\Local\Programs\Python\Python311\python.exe"
  $candidates += "python"
  $candidates += "python3"

  foreach ($candidate in $candidates) {
    if ($candidate -eq "python" -or $candidate -eq "python3") {
      $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
      if ($cmd -and $cmd.Source) {
        return $cmd.Source
      }
      continue
    }

    if (Test-Path $candidate) {
      return $candidate
    }
  }

  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return "py -3"
  }

  throw "未找到可用的 Python。请先安装 Python，或设置环境变量 PYTHON_BIN 指向可执行文件。"
}

function Resolve-NpmCmd {
  $candidates = @(
    "C:\Program Files\nodejs\npm.cmd",
    "C:\Program Files (x86)\nodejs\npm.cmd"
  )

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }

  $cmd = Get-Command npm -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source) {
    return $cmd.Source
  }

  throw "未找到可用的 npm。请先安装 Node.js。"
}

function Start-DetachedCommand($workingDir, $commandLine, $logFile) {
  $parent = Split-Path -Parent $logFile
  if ($parent) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
  }
  "" | Out-File -FilePath $logFile -Encoding utf8

  $cmd = "cd /d `"$workingDir`" && $commandLine >> `"$logFile`" 2>&1"
  Start-Process -WindowStyle Hidden -FilePath "$env:SystemRoot\System32\cmd.exe" -ArgumentList "/c", $cmd | Out-Null
}

$script:RootDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$FrontendDir = Join-Path $script:RootDir "frontend"
$LogDir = Join-Path $script:RootDir ".logs"
$BackendLog = Join-Path $LogDir "backend.log"
$FrontendLog = Join-Path $LogDir "frontend.log"
$BackendPort = 8010
$FrontendPort = 5173

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Info "初始化项目环境..."

$pythonExe = Resolve-PythonExe
$npmCmd = Resolve-NpmCmd

Stop-PortProcess $BackendPort
Stop-PortProcess $FrontendPort

if (-not (Wait-PortFree $BackendPort 15)) {
  throw "端口 $BackendPort 仍被占用，后端无法启动。"
}

if (-not (Wait-PortFree $FrontendPort 15)) {
  throw "端口 $FrontendPort 仍被占用，前端无法启动。"
}

Write-Info "启动后端..."
if ($pythonExe -eq "py -3") {
  Start-DetachedCommand $script:RootDir "py -3 -m uvicorn app.main:app --host 0.0.0.0 --port $BackendPort --reload" $BackendLog
} else {
  Start-DetachedCommand $script:RootDir "`"$pythonExe`" -m uvicorn app.main:app --host 0.0.0.0 --port $BackendPort --reload" $BackendLog
}

Write-Info "启动前端..."
Start-DetachedCommand $FrontendDir "`"$npmCmd`" run dev" $FrontendLog

$backendReady = $false
$frontendReady = $false
for ($i = 0; $i -lt 20; $i++) {
  Start-Sleep -Seconds 1
  $backendReady = Test-Port $BackendPort
  $frontendReady = Test-Port $FrontendPort
  if ($backendReady -and $frontendReady) {
    break
  }
}

Write-Info "后端日志: $BackendLog"
Write-Info "前端日志: $FrontendLog"

if ($backendReady) {
  Write-Info "后端已启动: http://127.0.0.1:$BackendPort"
} else {
  Write-Info "后端未成功监听端口 $BackendPort，请查看日志。"
}

if ($frontendReady) {
  Write-Info "前端已启动: http://127.0.0.1:$FrontendPort"
} else {
  Write-Info "前端未成功监听端口 $FrontendPort，请查看日志。"
}

if (-not $backendReady -or -not $frontendReady) {
  exit 1
}
