from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve()

REPLACEMENTS = {
    "Admin Console": "Панель администратора",
    "Generate all schedules · observe every HQ": "Создание расписаний · контроль всех участков",
    "Admin username": "Логин администратора",
    "Password": "Пароль",
    "Sign in": "Войти",
    "Sign In": "Войти",
    "Generate": "Планирование",
    "Observe": "Контроль",
    "Generate full schedule": "Сформировать полное расписание",
    "Generate for all": "Сформировать для всех",
    "Generating…": "Формирование…",
    "Cancel": "Отмена",
    "Progress": "Ход выполнения",
    "Start": "Начало",
    "End": "Окончание",
    "Clean slate (--init)": "Создать с нуля",
    "Supervisor Portal": "Панель руководителя",
    "Sign in to manage your group": "Войдите для управления участком",
    "Username": "Логин",
    "Supervisor Dashboard": "Панель руководителя",
    "Dashboard": "Обзор",
    "Live Map": "Карта",
    "Map": "Карта",
    "Technicians": "Механики",
    "Technician": "Механик",
    "Add Technician": "Добавить механика",
    "Add technician": "Добавить механика",
    "Maintenance": "ТО",
    "Maintenance Tasks": "Плановое ТО",
    "Callbacks": "Аварийные заявки",
    "Callback": "Аварийная заявка",
    "Repairs": "Ремонты",
    "Repair": "Ремонт",
    "Dispatch": "Назначить заявку",
    "Daily Report": "Дневной отчёт",
    "Daily Reports": "Дневные отчёты",
    "Monthly Log": "Месячный журнал",
    "Monthly Logs": "Месячные журналы",
    "Unit History": "История лифта",
    "Units": "Лифты",
    "Unit": "Лифт",
    "Elevator": "Лифт",
    "Elevators": "Лифты",
    "Schedule": "Расписание",
    "Schedules": "Расписания",
    "Generate Schedule": "Сформировать расписание",
    "Full Schedule": "Полное расписание",
    "Today": "Сегодня",
    "Tomorrow": "Завтра",
    "Date": "Дата",
    "Time": "Время",
    "Status": "Статус",
    "Priority": "Приоритет",
    "Address": "Адрес",
    "City": "Город",
    "Name": "Название",
    "Task": "Задача",
    "Tasks": "Задачи",
    "Route": "Маршрут",
    "Routes": "Маршруты",
    "Workload": "Загрузка",
    "Available": "Свободен",
    "On Site": "На объекте",
    "En Route": "В пути",
    "Done": "Выполнено",
    "Completed": "Выполнено",
    "Upcoming": "Предстоит",
    "Current": "Текущая",
    "Emergency": "Аварийная",
    "Urgent": "Срочная",
    "Normal": "Обычная",
    "High": "Высокий",
    "Low": "Низкий",
    "Save": "Сохранить",
    "Close": "Закрыть",
    "Open": "Открыть",
    "Search": "Поиск",
    "Filter": "Фильтр",
    "Refresh": "Обновить",
    "Loading...": "Загрузка...",
    "Loading…": "Загрузка…",
    "No data": "Нет данных",
    "No tasks": "Нет задач",
    "Technician Portal": "Приложение механика",
    "Sign in to view your optimized route": "Войдите, чтобы увидеть задания и маршрут",
    "Technician Route": "Маршрут механика",
    "My Route": "Мой маршрут",
    "My Tasks": "Мои задания",
    "Task Details": "Карточка задания",
    "Start Task": "Взять в работу",
    "Complete Task": "Завершить работу",
    "Leave": "Отпуск / отсутствие",
    "On Leave": "Отсутствует",
    "Location": "Местоположение",
    "Last update": "Последнее обновление",
    "Logout": "Выйти",
    "Log out": "Выйти",
}

changed = 0
for path in ROOT.rglob("*.dart"):
    text = path.read_text(encoding="utf-8")
    original = text
    for src, dst in REPLACEMENTS.items():
        text = text.replace(f"'{src}'", f"'{dst}'")
        text = text.replace(f'"{src}"', f'"{dst}"')
    if text != original:
        path.write_text(text, encoding="utf-8")
        changed += 1

settings = ROOT / "capstone" / "settings.py"
if settings.exists():
    text = settings.read_text(encoding="utf-8")
    text = text.replace("LANGUAGE_CODE = 'en-us'", "LANGUAGE_CODE = 'ru-ru'")
    settings.write_text(text, encoding="utf-8")

print(f"Translation complete. Changed Dart files: {changed}")
print(f"Project: {ROOT}")
