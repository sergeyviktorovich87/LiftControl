# Первый запуск LiftControl на Windows

## 1. Backend

```powershell
git clone https://github.com/sergeyviktorovich87/LiftControl.git
cd LiftControl\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations core
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Проверка API:

- `http://127.0.0.1:8000/api/health/`
- `http://127.0.0.1:8000/api/dashboard/`
- `http://127.0.0.1:8000/admin/`

## 2. Web-панель

В новом PowerShell:

```powershell
cd LiftControl\web
npm install
npm run dev
```

Открой адрес, который покажет Vite (обычно `http://localhost:5173`).

## 3. Android

В папке `mobile` сначала один раз создайте платформенные файлы Flutter:

```powershell
cd LiftControl\mobile
flutter create .
flutter pub get
```

Эмулятор Android:

```powershell
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api
```

Реальный телефон в одной Wi-Fi сети с компьютером:

```powershell
flutter run --dart-define=API_BASE_URL=http://IP_КОМПЬЮТЕРА:8000/api
```

Например: `http://192.168.1.50:8000/api`.

## Что должно появиться

После `seed_demo` веб-панель покажет 4 лифта, 3 механиков, несколько заявок и план ТО. Это тестовые данные — их можно удалить через Django Admin.
