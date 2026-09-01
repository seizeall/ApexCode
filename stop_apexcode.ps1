[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [ValidateRange(0, 65535)]
    [int]$Port = 0,

    [switch]$Force
)

$ErrorActionPreference = "Stop"

if ($Force -and $Port -eq 0) {
    throw "-Force requires an explicit -Port value to protect unrelated services."
}

$whatIfRequested = $WhatIfPreference
$WhatIfPreference = $false
try {
    $connections = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue)
} finally {
    $WhatIfPreference = $whatIfRequested
}
if ($Port -gt 0) {
    $connections = @($connections | Where-Object { $_.LocalPort -eq $Port })
} else {
    $connections = @($connections | Where-Object { $_.LocalPort -ge 8000 -and $_.LocalPort -le 8099 })
}

if ($connections.Count -eq 0) {
    $scope = if ($Port -gt 0) { "Port $Port" } else { "Ports 8000-8099" }
    Write-Host "$scope has no listening process." -ForegroundColor Yellow
    exit 0
}

$stopped = 0
$skipped = 0
$owners = @($connections | Group-Object OwningProcess)

foreach ($owner in $owners) {
    $processId = [int]$owner.Name
    $WhatIfPreference = $false
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
    } finally {
        $WhatIfPreference = $whatIfRequested
    }
    if (-not $process) {
        Write-Warning "Cannot inspect PID $processId; it may have already exited."
        continue
    }

    $listeningPorts = @($owner.Group | Select-Object -ExpandProperty LocalPort -Unique | Sort-Object)
    $identity = "$($process.Name) $($process.ExecutablePath) $($process.CommandLine)"
    $isApexCode = $identity -match "(?i)(ApexCode(?:\.exe)?|desktop_launcher\.py|app\.web\.app)"

    if (-not $isApexCode -and -not $Force) {
        Write-Warning "Skipped non-ApexCode process $($process.Name) (PID $processId) on port(s) $($listeningPorts -join ', '). Use an explicit -Port with -Force only if this is intentional."
        $skipped++
        continue
    }

    $target = "$($process.Name) (PID $processId, port(s) $($listeningPorts -join ', '))"
    if ($PSCmdlet.ShouldProcess($target, "Stop ApexCode listener")) {
        Stop-Process -Id $processId -ErrorAction Stop
        Write-Host "Stopped $target" -ForegroundColor Green
        $stopped++
    }
}

if ($stopped -eq 0 -and $skipped -eq 0 -and -not $WhatIfPreference) {
    Write-Host "No ApexCode listener needed to be stopped." -ForegroundColor Yellow
}
