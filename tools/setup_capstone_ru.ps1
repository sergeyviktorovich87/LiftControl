param(
    [string]$Destination = "$HOME\Capstone-RU"
)

$ErrorActionPreference = "Stop"
$repo = "https://github.com/Genkyu9988/Capstone.git"
$translator = Join-Path $PSScriptRoot "translate_capstone_ru.py"

Write-Host "=== LiftControl: prepare Capstone-RU ===" -ForegroundColor Cyan

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git not found."
}

$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
} else {
    throw "Python not found."
}

if (-not (Test-Path $Destination)) {
    Write-Host "Cloning original Capstone..." -ForegroundColor Yellow
    git clone $repo $Destination
} else {
    Write-Host "Refreshing existing Capstone copy..." -ForegroundColor Yellow
    git -C $Destination fetch origin
    git -C $Destination checkout main
    git -C $Destination reset --hard origin/main
}

if (-not (Test-Path $translator)) {
    throw "Translator script not found: $translator"
}

& $python $translator $Destination
if ($LASTEXITCODE -ne 0) {
    throw "Translation failed."
}

Write-Host "Done. Russian test copy: $Destination" -ForegroundColor Green
Write-Host "Original upstream repository was not modified." -ForegroundColor DarkGray
