param(
    [ValidateSet('supervisor','admin','mobile')]
    [string]$Mode = 'supervisor',
    [string]$ProjectPath = "$HOME\Capstone-RU"
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $ProjectPath)) {
    throw "Capstone-RU не найден. Сначала запустите tools\setup_capstone_ru.ps1"
}

if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python не найден."
}

if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
    throw "Flutter не найден. Установите Flutter SDK и добавьте его в PATH."
}

$python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }

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

    Write-Host "Запускаю Django на 8000..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList '-NoExit','-Command',"cd '$ProjectPath'; & '$venvPython' manage.py runserver 0.0.0.0:8000"

    Start-Sleep -Seconds 2

    switch ($Mode) {
        'supervisor' {
            Write-Host "Запускаю русскую панель руководителя..." -ForegroundColor Green
            flutter run -d chrome -t lib/web/supervisor_dashboard.dart
        }
        'admin' {
            Write-Host "Запускаю русскую панель администратора..." -ForegroundColor Green
            flutter run -d chrome -t lib/web/admin_dashboard.dart
        }
        'mobile' {
            Write-Host "Запускаю приложение механика..." -ForegroundColor Green
            flutter run -t lib/mobile/main.dart
        }
    }
}
finally {
    Pop-Location
}
