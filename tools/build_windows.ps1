<#
.SYNOPSIS
Construit un exécutable Windows de PressVisual.

.DESCRIPTION
Le script crée un environnement virtuel dédié dans build\windows\, y installe
PyQt6, pynput et PyInstaller, compile les traductions, dessine l'icône .ico avec
l'application elle-même, puis empaquette PressVisual.

Deux formats sont possibles :
  - par défaut, un dossier autonome compressé (démarrage rapide, moins de faux
    positifs antivirus) : dist\PressVisual-<version>-win64.zip ;
  - avec -OneFile, un exécutable unique : dist\PressVisual-<version>-win64.exe.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1

.EXAMPLE
powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1 -OneFile -Version 1.0.0
#>
#Requires -Version 5.1
[CmdletBinding()]
param(
    # Exécutable unique au lieu du dossier autonome.
    [switch]$OneFile,
    # Réutilise l'environnement virtuel déjà installé.
    [switch]$SkipInstall,
    # Interpréteur utilisé pour créer l'environnement virtuel.
    [string]$Python = "python",
    # Version inscrite dans le nom du fichier (défaut : git describe).
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "Ce script ne fonctionne que sous Windows."
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$AppName = "PressVisual"
$BuildDir = Join-Path $Root "build\windows"
$VenvDir = Join-Path $BuildDir "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$DistDir = Join-Path $Root "dist"
$IconPath = Join-Path $BuildDir "$AppName.ico"

function Write-Step {
    param([string]$Message)
    Write-Host "[PressVisual] $Message" -ForegroundColor Cyan
}

if (-not $Version) {
    try {
        $Version = (git describe --tags --always --dirty 2>$null)
    }
    catch {
        $Version = $null
    }
    if (-not $Version) { $Version = "0.0.0" }
    $Version = $Version.TrimStart("v")
}

Write-Step "PressVisual $Version"

# ---------------------------------------------------------------------------
# Environnement virtuel et dépendances
# ---------------------------------------------------------------------------

New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

if (-not (Test-Path $VenvPython)) {
    Write-Step "création de l'environnement virtuel dans $VenvDir"
    & $Python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "Impossible de créer l'environnement virtuel." }
}

# L'empreinte de requirements.txt évite de réinstaller à chaque build tout en
# réagissant si les dépendances changent.
$StampPath = Join-Path $VenvDir ".requirements-hash"
$Hash = (Get-FileHash (Join-Path $Root "requirements.txt") -Algorithm SHA256).Hash
$KnownHash = if (Test-Path $StampPath) { (Get-Content $StampPath -Raw).Trim() } else { "" }

if ($SkipInstall) {
    Write-Step "installation des dépendances ignorée (-SkipInstall)"
    & $VenvPython -m PyInstaller --version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller est absent de l'environnement ; relancez sans -SkipInstall."
    }
}
elseif ($KnownHash -ne $Hash) {
    Write-Step "installation des dépendances (PyQt6, pynput, PyInstaller)"
    & $VenvPython -m pip install --quiet --upgrade pip
    & $VenvPython -m pip install --quiet -r requirements.txt pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "Installation des dépendances impossible." }
    Set-Content -Path $StampPath -Value $Hash -NoNewline
}

# Les catalogues .qm sont générés depuis les .ts, sans dépendre de lrelease.
Write-Step "compilation des traductions"
& $VenvPython tools\compile_translations.py | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Compilation des traductions impossible." }

# L'icône est dessinée par l'application elle-même : aucun binaire à stocker
# dans le dépôt, et l'exécutable porte exactement l'icône de la zone de
# notification.
Write-Step "génération de l'icône .ico"
$iconScript = @'
import sys

from PyQt6.QtWidgets import QApplication

from pressvisual_app.icon import _icon_pixmap

app = QApplication([])  # requis pour dessiner avec QPainter
if not _icon_pixmap(256).save(sys.argv[1], "ICO"):
    raise SystemExit("impossible d'enregistrer l'icône")
'@
$iconScript | & $VenvPython - $IconPath
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $IconPath)) {
    Write-Warning "Icône non générée : l'exécutable sera construit sans icône."
}

# ---------------------------------------------------------------------------
# Empaquetage PyInstaller
# ---------------------------------------------------------------------------

Write-Step "empaquetage PyInstaller (quelques minutes la première fois)"
$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    $(if ($OneFile) { "--onefile" } else { "--onedir" }),
    "--windowed",
    "--name", $AppName,
    "--distpath", (Join-Path $BuildDir "dist"),
    "--workpath", (Join-Path $BuildDir "work"),
    "--specpath", $BuildDir,
    # Chemin absolu : --specpath change le dossier de référence des chemins
    # relatifs. Séparateur « ; » sous Windows.
    "--add-data", "$Root\translations;translations",
    # Les backends de pynput sont choisis à l'exécution : sans ces imports, la
    # capture resterait muette dans l'exécutable figé.
    "--hidden-import", "pynput.keyboard._win32",
    "--hidden-import", "pynput.mouse._win32",
    "pressvisual.py"
)
if (Test-Path $IconPath) {
    $PyInstallerArgs = @("--icon", $IconPath) + $PyInstallerArgs
}

& $VenvPython -m PyInstaller @PyInstallerArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller a échoué." }

$BundleDir = Join-Path $BuildDir "dist\$AppName"
if ($OneFile) {
    $BuiltExe = Join-Path $BuildDir "dist\$AppName.exe"
    if (-not (Test-Path $BuiltExe)) { throw "Exécutable introuvable : $BuiltExe" }
}
else {
    $BuiltExe = Join-Path $BundleDir "$AppName.exe"
    if (-not (Test-Path $BuiltExe)) { throw "Exécutable introuvable : $BuiltExe" }
}

# ---------------------------------------------------------------------------
# Livraison
# ---------------------------------------------------------------------------

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

if ($OneFile) {
    $Target = Join-Path $DistDir "$AppName-$Version-win64.exe"
    Copy-Item -Path $BuiltExe -Destination $Target -Force
}
else {
    $Target = Join-Path $DistDir "$AppName-$Version-win64.zip"
    if (Test-Path $Target) { Remove-Item $Target -Force }
    Write-Step "compression du dossier autonome"
    Compress-Archive -Path $BundleDir -DestinationPath $Target -CompressionLevel Optimal
}

$SizeMb = [math]::Round((Get-Item $Target).Length / 1MB, 1)
Write-Step "terminé : $Target ($SizeMb Mo)"
Write-Step "placez config.json à côté de $AppName.exe pour une configuration persistante."
