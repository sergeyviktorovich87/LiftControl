# Локальный запуск

Команды предназначены для отдельной копии проекта с локальной SQLite-базой. Для установленного VPS используйте [обновление 0.11](../deploy/offline/UPDATE.md).

## Панель и API

Python 3.12, Node.js 22 и FFmpeg для сценариев с видео. Из корня проекта на Linux/macOS выполните:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix web ci
npm --prefix web run build -- --base=/static/web/
mkdir -p backend/static/web/assets
cp web/dist/index.html backend/templates/index.html
cp web/dist/assets/* backend/static/web/assets/
export DJANGO_DEBUG=True
.venv/bin/python backend/manage.py migrate
.venv/bin/python backend/manage.py createsuperuser
.venv/bin/python backend/manage.py runserver 127.0.0.1:8000
```

Откройте панель на `http://127.0.0.1:8000/`, проверку API на `http://127.0.0.1:8000/api/health/`. Команда `seed_demo` добавляет примерные данные в локальную базу по необходимости.

Для просмотра интерфейса с примерами можно запустить `VITE_PREVIEW=true npm --prefix web run dev`. Vite покажет адрес. Изменения в режиме примеров не записываются в рабочую базу.

## Android

Используйте Flutter 3.47.9 и Java 17. В репозитории уже есть файлы Android. В примере `adb reverse` направляет loopback-порт телефона или эмулятора к локальному API на компьютере.

```bash
adb reverse tcp:18081 tcp:8000
cd mobile
flutter pub get --enforce-lockfile
flutter run --dart-define=API_SERVER=http://127.0.0.1:18081
```

Для обычного входа на реальном телефоне укажите корневой HTTPS-адрес сервера. Инструкция тестовых сценариев и ограничения beta указаны в [документации Android](../mobile/README.md).

## Проверки

```bash
DJANGO_DEBUG=True .venv/bin/python backend/manage.py test core
python3 -m unittest discover -s tests
```

В `mobile/` запустите `flutter analyze --no-pub` и `flutter test --no-pub`. Сборка, тест Android с API и проверка установщика также выполняются в GitHub Actions.
