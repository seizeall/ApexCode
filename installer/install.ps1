$ErrorActionPreference = "Stop"
$target = Join-Path $env:LOCALAPPDATA "ApexCode"
New-Item -ItemType Directory -Force -Path $target | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $target "workspace") | Out-Null

Copy-Item (Join-Path $PSScriptRoot "ApexCode.exe") (Join-Path $target "ApexCode.exe") -Force
Copy-Item (Join-Path $PSScriptRoot "README.txt") (Join-Path $target "README.txt") -Force
Copy-Item (Join-Path $PSScriptRoot "API_CONFIG.md") (Join-Path $target "API_CONFIG.md") -Force
Copy-Item (Join-Path $PSScriptRoot "DEMO_GUIDE.md") (Join-Path $target "DEMO_GUIDE.md") -Force

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

Start-Process -FilePath (Join-Path $target "ApexCode.exe") -WorkingDirectory $target
Start-Process -FilePath "notepad.exe" -ArgumentList $config
