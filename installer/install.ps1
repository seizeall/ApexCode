$ErrorActionPreference = "Stop"
$target = Join-Path $env:LOCALAPPDATA "ApexCode"
New-Item -ItemType Directory -Force -Path $target | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $target "workspace") | Out-Null
$demo = Join-Path $target "workspace\apex_flowboard"
$demoAssets = Join-Path $demo "assets"
New-Item -ItemType Directory -Force -Path $demoAssets | Out-Null

Copy-Item (Join-Path $PSScriptRoot "ApexCode.exe") (Join-Path $target "ApexCode.exe") -Force
Copy-Item (Join-Path $PSScriptRoot "README.txt") (Join-Path $target "README.txt") -Force
Copy-Item (Join-Path $PSScriptRoot "API_CONFIG.md") (Join-Path $target "API_CONFIG.md") -Force
Copy-Item (Join-Path $PSScriptRoot "DEMO_GUIDE.md") (Join-Path $target "DEMO_GUIDE.md") -Force
Copy-Item (Join-Path $PSScriptRoot "stop_apexcode.ps1") (Join-Path $target "stop_apexcode.ps1") -Force
Copy-Item (Join-Path $PSScriptRoot "Stop-ApexCode.cmd") (Join-Path $target "Stop-ApexCode.cmd") -Force
Copy-Item (Join-Path $PSScriptRoot "PLAN.md") (Join-Path $demo "PLAN.md") -Force
Copy-Item (Join-Path $PSScriptRoot "app.js") (Join-Path $demo "app.js") -Force
Copy-Item (Join-Path $PSScriptRoot "index.html") (Join-Path $demo "index.html") -Force
Copy-Item (Join-Path $PSScriptRoot "styles.css") (Join-Path $demo "styles.css") -Force
Copy-Item (Join-Path $PSScriptRoot "workflow-map.svg") (Join-Path $demoAssets "workflow-map.svg") -Force

$example = Join-Path $target ".env.example"
Copy-Item (Join-Path $PSScriptRoot ".env.example") $example -Force
$config = Join-Path $target ".env"
if (-not (Test-Path -LiteralPath $config)) {
  Copy-Item $example $config
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "ApexCode.lnk"))
$shortcut.TargetPath = Join-Path $target "ApexCode.exe"
$shortcut.WorkingDirectory = $target
$shortcut.Description = "ApexCode local coding agent"
$shortcut.Save()

$stopShortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Stop ApexCode.lnk"))
$stopShortcut.TargetPath = Join-Path $target "Stop-ApexCode.cmd"
$stopShortcut.WorkingDirectory = $target
$stopShortcut.Description = "Stop local ApexCode server"
$stopShortcut.Save()

Start-Process -FilePath (Join-Path $target "ApexCode.exe") -WorkingDirectory $target
Start-Process -FilePath "notepad.exe" -ArgumentList $config
