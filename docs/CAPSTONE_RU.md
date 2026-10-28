# Capstone-RU — тест оригинального второго проекта

Эта ветка не заменяет текущий LiftControl. Она помогает скачать оригинальный публичный проект `Genkyu9988/Capstone` в отдельную локальную папку, русифицировать основные интерфейсные подписи и запустить его для сравнения.

## 1. Обновить LiftControl и перейти на тестовую ветку

```powershell
git pull
git switch capstone-ru-test
```

## 2. Скачать и русифицировать Capstone

Из корня LiftControl:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\setup_capstone_ru.ps1
```

Будет создана папка:

```text
C:\Users\<USER>\Capstone-RU
```

Оригинальный репозиторий автора при этом не меняется.

## 3. Запуск панели руководителя

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_capstone_ru.ps1 -Mode supervisor
```

## 4. Запуск панели администратора

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_capstone_ru.ps1 -Mode admin
```

## 5. Запуск приложения механика

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_capstone_ru.ps1 -Mode mobile
```

## Что требуется

- Git
- Python 3.11+
- Flutter SDK
- Chrome для Flutter Web

Google Maps для первого просмотра не обязателен: проект умеет работать с отключённым Google Maps и упрощёнными маршрутами.

## Важно

У исходного Capstone на GitHub не указана лицензия. Поэтому используем его как отдельный тестовый/референсный проект и не смешиваем исходный код с нашим LiftControl до решения вопроса с лицензированием.
