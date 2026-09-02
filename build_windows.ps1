$ErrorActionPreference = "Stop"

Write-Host "[1/6] Installing dependencies and PyInstaller..."
python -m pip install -r requirements.txt pyinstaller

Write-Host "[2/6] Building the single-file Windows executable..."
python -m PyInstaller --noconfirm --onefile --name ApexCode `
  --add-data "app\web\static;app\web\static" desktop_launcher.py

Write-Host "[3/6] Preparing the release folder..."
$release = Join-Path (Get-Location) "release\ApexCode"
New-Item -ItemType Directory -Force -Path $release | Out-Null
Copy-Item "dist\ApexCode.exe" (Join-Path $release "ApexCode.exe") -Force
Copy-Item ".env.example" (Join-Path $release ".env.example") -Force
Copy-Item "README.txt" (Join-Path $release "README.txt") -Force
Copy-Item "API_CONFIG.md" (Join-Path $release "API_CONFIG.md") -Force
Copy-Item "DEMO_GUIDE.md" (Join-Path $release "DEMO_GUIDE.md") -Force
Copy-Item "ASSESSMENT_REPORT.md" (Join-Path $release "ASSESSMENT_REPORT.md") -Force
Copy-Item "stop_apexcode.ps1" (Join-Path $release "stop_apexcode.ps1") -Force
Copy-Item "Stop-ApexCode.cmd" (Join-Path $release "Stop-ApexCode.cmd") -Force
New-Item -ItemType Directory -Force -Path (Join-Path $release "workspace") | Out-Null
$demoTarget = Join-Path $release "workspace\apex_flowboard"
New-Item -ItemType Directory -Force -Path $demoTarget | Out-Null
Copy-Item "examples\demo_project\apex_flowboard\*" $demoTarget -Recurse -Force

Write-Host "[4/6] Building the click-to-install package..."
$root = (Get-Location).Path
$setupTarget = Join-Path $root "release\ApexCode-Setup.exe"
if (Test-Path -LiteralPath $setupTarget) {
  Remove-Item -LiteralPath $setupTarget -Force
}
$template = Get-Content "installer\ApexCode-Setup.sed.template" -Raw
$sed = $template.Replace("{{TARGET}}", $setupTarget)
$sed = $sed.Replace("{{RELEASE}}", $release)
$sed = $sed.Replace("{{INSTALLER}}", (Join-Path $root "installer"))
$sedPath = Join-Path $root "build\ApexCode-Setup.sed"
[System.IO.File]::WriteAllText($sedPath, $sed, [System.Text.Encoding]::Default)
Start-Process -FilePath "$env:SystemRoot\System32\iexpress.exe" -ArgumentList "/N", "/Q", $sedPath -Wait -WindowStyle Hidden

Write-Host "[5/6] Creating the portable ZIP..."
$zipCreated = $false
for ($attempt = 1; $attempt -le 5; $attempt++) {
  try {
    Compress-Archive -Path "$release\*", "$release\.env.example" -DestinationPath "release\ApexCode-Windows.zip" -Force
    $zipCreated = $true
    break
  } catch [System.IO.IOException] {
    Start-Sleep -Seconds 1
  }
}
if (-not $zipCreated) { throw "Could not create the portable ZIP because a build file remained locked." }

Write-Host "[6/6] Creating the source ZIP..."
& tar.exe -a -c -f "release\ApexCode-Source.zip" `
  --exclude="*/__pycache__/*" --exclude="*.pyc" --exclude=".pytest_cache/*" `
  app examples tests installer .env.example .gitignore pyproject.toml requirements.txt `
  README.txt run_web.ps1 stop_apexcode.ps1 Stop-ApexCode.cmd API_CONFIG.md DEMO_GUIDE.md ASSESSMENT_REPORT.md desktop_launcher.py build_windows.ps1
if ($LASTEXITCODE -ne 0) { throw "Could not create the source ZIP." }

Write-Host "Portable app: $release\ApexCode.exe"
Write-Host "Installer: $root\release\ApexCode-Setup.exe"
Write-Host "Portable ZIP: $root\release\ApexCode-Windows.zip"
Write-Host "Source ZIP: $root\release\ApexCode-Source.zip"
Write-Host "First run: copy .env.example to .env, fill in the API key, then double-click ApexCode.exe."
