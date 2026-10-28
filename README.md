# LiftControl

LiftControl — система управления лифтовой организацией: лифты, объекты, механики, заявки, ТО, диспетчеризация и мобильное приложение механика.

## Архитектура

```text
LiftControl/
├── backend/   # Django REST API + SQLite для локальной разработки
├── mobile/    # Flutter Android-приложение механика
├── web/       # React/Vite панель руководителя и диспетчера
└── docs/      # архитектура и план развития
```

## MVP

Первая версия включает:

- реестр лифтов;
- механиков;
- заявки/неисправности;
- плановое ТО;
- статусы и приоритеты заявок;
- REST API;
- веб-панель;
- Android-клиент механика.

## Быстрый запуск backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations core
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

API после запуска: `http://127.0.0.1:8000/api/`

## Быстрый запуск web

```powershell
cd web
npm install
npm run dev
```

## Быстрый запуск mobile

```powershell
cd mobile
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api
```

Для реального Android-телефона вместо `10.0.2.2` укажите локальный IP компьютера, например `http://192.168.1.50:8000/api`.

## Важно

Проект пишется как самостоятельная кодовая база. Идеи сторонних open-source/учебных проектов могут использоваться только как архитектурные ориентиры; чужой код без подходящей лицензии сюда не переносится.
