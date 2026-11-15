# Build Keyglot: language data, tests, PyInstaller bundle, Inno Setup installer, SHA256SUMS.
#   ./build.ps1 [-Version 0.2.0]
param([string]$Version)
$ErrorActionPreference = "Stop"
if (Test-Path "$PSScriptRoot\.venv\Scripts\python.exe") { $env:PATH = "$PSScriptRoot\.venv\Scripts;" + $env:PATH }
Set-Location $PSScriptRoot
if (-not $Version) { $Version = (python -c "import keyglot; print(keyglot.__version__)").Trim() }
$pkgVersion = (python -c "import keyglot; print(keyglot.__version__)").Trim()
if ($Version -ne $pkgVersion) { throw "Version $Version does not match keyglot/__init__.py ($pkgVersion)" }

python tools/build_data.py
if (-not (Test-Path assets/keyglot.ico)) { python tools/make_icon.py }
python -c "import comtypes.client as c; c.GetModule('UIAutomationCore.dll')"
python -m pytest -q tests
if ($LASTEXITCODE) { throw "tests failed" }

$v = $Version.Split('.') + @('0')
New-Item -ItemType Directory -Force build | Out-Null
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($($v[0]), $($v[1]), $($v[2]), 0), prodvers=($($v[0]), $($v[1]), $($v[2]), 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Roman Petrov'),
    StringStruct('FileDescription', 'Keyglot - context-aware keyboard layout switcher'),
    StringStruct('FileVersion', '$Version'),
    StringStruct('ProductName', 'Keyglot'),
    StringStruct('ProductVersion', '$Version'),
    StringStruct('LegalCopyright', 'MIT License')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"@ | Out-File build/version.txt -Encoding utf8

python -m PyInstaller --noconfirm --clean --windowed --name Keyglot --icon assets/keyglot.ico `
  --version-file build/version.txt `
  --add-data "keyglot/data;keyglot/data" --add-data "assets/keyglot.ico;assets" `
  --hidden-import comtypes.gen.UIAutomationClient --collect-submodules comtypes.gen `
  --hidden-import pystray._win32 `
  run_keyglot.py
if ($LASTEXITCODE) { throw "PyInstaller failed" }

$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
foreach ($p in "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") {
  if (-not $iscc -and (Test-Path $p)) { $iscc = $p }
}
if (-not $iscc) { throw "Inno Setup (ISCC.exe) not found" }
& $iscc "/DAppVersion=$Version" installer\keyglot.iss
if ($LASTEXITCODE) { throw "ISCC failed" }

$setup = "Keyglot-Setup-$Version.exe"
$hash = (Get-FileHash "dist\$setup" -Algorithm SHA256).Hash.ToLower()
"$hash *$setup" | Out-File dist\SHA256SUMS.txt -Encoding ascii
Write-Host "built dist\$setup ($hash)"

