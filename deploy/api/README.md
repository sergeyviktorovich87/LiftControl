# Обновление 0.4

Для существующего сервера используйте [инструкцию обновления](UPDATE-v04.md) и дополнительный compose.v04.yaml. Следующий текст описывает первоначальную установку 0.1.

# LiftControl Django API — закрытый пилот на существующем VPS

Этот модуль **дополняет** существующий `/opt/liftcontrol/compose.yaml`. Он не переустанавливает PostgreSQL, не меняет SSH и не публикует PostgreSQL в интернет.

## Предпосылки

- PostgreSQL 18 в существующем Docker Compose работает в сети `backend`.
- БД `liftcontrol` и схема `app` существуют.
- Роль `liftapp` существует; пароль в `/opt/liftcontrol/secrets/postgres_app_password`.
- Последний локальный резервный архив проверен, зашифрованная копия сохранена вне VPS.
- Сервер работает без домена. Django API будет доступен **только на `127.0.0.1:18080` VPS** (в дальнейшем — через SSH-туннель).

## Файлы

- `backend/Dockerfile` — Docker-образ Django с Gunicorn под непривилегированным UID 10001.
- `backend/core/migrations/0001_initial.py` — зафиксированная начальная миграция.
- `deploy/api/compose.api.yaml` — дополнительный Compose-файл; основной `compose.yaml` остаётся нетронутым.
- `.github/workflows/backend-tests.yml` — тесты защиты API, миграций, сборки Docker.

## Подготовка к развертыванию (только с проверенной копией кода)

Перед реальным запуском скопируйте содержимое `backend/` в `/opt/liftcontrol/src/backend`,
а `deploy/api/compose.api.yaml` — в `/opt/liftcontrol/compose.api.yaml`.
Приватный репозиторий можно скачать на компьютер через GitHub и перенести в ServerBox по SFTP.
Не размещайте приватный ключ GitHub, токены или пароли в Dockerfile и ZIP.

Секрет `django_secret_key` создаётся на самом VPS:
```bash
sudo sh -c 'umask 077; openssl rand -hex 48 > /opt/liftcontrol/secrets/django_secret_key'
sudo chgrp 10001 /opt/liftcontrol/secrets/django_secret_key /opt/liftcontrol/secrets/postgres_app_password
sudo chmod 0640 /opt/liftcontrol/secrets/django_secret_key /opt/liftcontrol/secrets/postgres_app_password
```
Это разрешает чтение только системному root и группе UID/GID 10001 контейнера Django; доступ по SFTP к файлам секретов не нужен.

## Перед миграциями

Сначала создайте новую резервную копию и проверьте последнюю.

Приложению с ролью `liftapp` нужны разрешения на последовательности Django:
```sql
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO liftapp;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA app
GRANT USAGE, SELECT ON SEQUENCES TO liftapp;
```

**Не добавляйте** административный пароль PostgreSQL в постоянный контейнер API. Сервис `migrate`
предназначен только для одноразовых миграций, работает с `postgres_admin_password`;
после успешного выполнения он не остаётся запущенным.
В будущей версии рекомендуется выделить специальную роль для миграций.

## Запуск (после проверки файлов и секретов)

Рабочий каталог: `/opt/liftcontrol`.

```bash
sudo docker compose -f compose.yaml -f compose.api.yaml config -q
sudo docker compose -f compose.yaml -f compose.api.yaml build api
sudo docker compose -f compose.yaml -f compose.api.yaml --profile maintenance run --rm migrate
sudo docker compose -f compose.yaml -f compose.api.yaml up -d api
curl --fail http://127.0.0.1:18080/api/health/
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/api/elevators/
```

Ожидаемый ответ health: `{"status":"ok","service":"LiftControl API"}`. Второй запрос без авторизации должен вернуть `401` (либо `403`) — это защищённый API.

Данные пользователей и токены **нельзя** передавать по публичному HTTP. До TLS используйте SSH-туннель. В Docker Compose опубликован только loopback-порт `127.0.0.1:18080`, PostgreSQL не публикуется.

## Логи и диагностика

```bash
sudo docker compose -f /opt/liftcontrol/compose.yaml -f /opt/liftcontrol/compose.api.yaml ps
sudo docker compose -f /opt/liftcontrol/compose.yaml -f /opt/liftcontrol/compose.api.yaml logs --tail=80 api
```

Тестовая версия использует stdout/stderr журналы Gunicorn с установленной на хосте ротацией Docker.
Не пишите в журналы пароли, токены или персональные данные заявок.

## Границы готовности

Это закрытый технический пилот, **не коммерческий релиз**. Перед рабочей эксплуатацией необходимы:
ролевые права на уровне объектов, аудит изменений, защита от каскадного удаления,
внешнее резервирование, домен/TLS (либо управляемая VPN-сеть), политика сессий,
обновления зависимостей и тесты восстановления полноценного сервера.

