param(
    [string]$BlenderPath = ""
)

$ErrorActionPreference = "Stop"
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SourceDir = Join-Path $RootDir "bpm_timeline_audio_visualizer"
$OutputDir = Join-Path $RootDir "build"
$Package = Join-Path $OutputDir "bpm_timeline_audio_visualizer.zip"

if (-not $BlenderPath) {
    $BlenderCommand = Get-Command blender.exe -ErrorAction SilentlyContinue
    if ($BlenderCommand) {
        $BlenderPath = $BlenderCommand.Source
    } else {
        $InstallRoot = Join-Path $env:ProgramFiles "Blender Foundation"
        $Candidates = @()
        if (Test-Path $InstallRoot) {
            $Candidates = Get-ChildItem $InstallRoot -Directory |
                Sort-Object Name -Descending |
                ForEach-Object { Join-Path $_.FullName "blender.exe" } |
                Where-Object { Test-Path $_ }
        }
        if ($Candidates.Count -gt 0) {
            $BlenderPath = $Candidates[0]
        }
    }
}

if (-not $BlenderPath -or -not (Test-Path $BlenderPath)) {
    throw "No se encontró Blender. Usa -BlenderPath 'C:\ruta\blender.exe' o añade blender.exe al PATH."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
& $BlenderPath --command extension build `
    --source-dir $SourceDir `
    --output-filepath $Package
if ($LASTEXITCODE -ne 0) {
    throw "Falló la creación del paquete de extensión."
}

& $BlenderPath --command extension install-file `
    -r user_default `
    --enable `
    $Package
if ($LASTEXITCODE -ne 0) {
    throw "Falló la instalación/activación de la extensión."
}

Write-Host "Extensión instalada y activada."
Write-Host "Paquete: $Package"
