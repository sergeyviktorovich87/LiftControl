param(
    [ValidateSet('supervisor','admin','mobile')]
    [string]$Mode = 'supervisor',
    [string]$ProjectPath = "$HOME\Capstone-RU"
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $ProjectPath)) {
    throw "Capstone-RU not found. Run tools\setup_capstone_ru.ps1 first."
}

$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $python = 'py'
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = 'python'
} else {
    throw "Python not found."
}

if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
    throw "Flutter not found. Install Flutter SDK and add it to PATH."
}

Push-Location $ProjectPath
try {
    if (-not (Test-Path '.venv')) {
        & $python -m venv .venv
    }

    $venvPython = Join-Path $ProjectPath '.venv\Scripts\python.exe'

    if (-not (Test-Path '.venv\.liftcontrol_deps_ok')) {
        & $venvPython -m pip install --upgrade pip
        & $venvPython -m pip install -r requirements.txt
        New-Item '.venv\.liftcontrol_deps_ok' -ItemType File -Force | Out-Null
    }

    & $venvPython manage.py migrate

    if (-not (Test-Path '.liftcontrol_seeded')) {
        & $venvPython seed.py
        New-Item '.liftcontrol_seeded' -ItemType File -Force | Out-Null
    }

    flutter pub get

    Write-Host "Starting Django on port 8000..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList '-NoExit','-Command',"cd '$ProjectPath'; & '$venvPython' manage.py runserver 0.0.0.0:8000"

    Start-Sleep -Seconds 2

    switch ($Mode) {
        'supervisor' {
            Write-Host "Starting supervisor dashboard..." -ForegroundColor Green
            flutter run -d chrome -t lib/web/supervisor_dashboard.dart
        }
        'admin' {
            Write-Host "Starting admin dashboard..." -ForegroundColor Green
            flutter run -d chrome -t lib/web/admin_dashboard.dart
        }
        'mobile' {
            Write-Host "Starting technician mobile app..." -ForegroundColor Green
            flutter run -t lib/mobile/main.dart
        }
    }
}
finally {
    Pop-Location
}
