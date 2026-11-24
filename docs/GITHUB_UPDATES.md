# Автоматическое обновление PWA

Режим: только стабильные опубликованные GitHub Releases из фиксированного репозитория.
Тестовые releases, произвольные ветки, APK и откат к старой версии игнорируются.
Подтверждается SHA-256 и подписанная аттестация GitHub Actions: репозиторий, workflow offline-patch.yml, refs/heads/main, точный SHA тега, GitHub-hosted runner. GitHub и доступ к main остаются доверенной границей; включите 2FA и защиту main. Никакие GitHub write-токены не нужны на VPS. Не передавайте пароль или SSH ключ в GitHub.

## Однократная установка
Требуется Python 3.8+, Docker Compose, systemd, curl, unzip и актуальный официальный GitHub CLI с gh attestation verify, --bundle, --signer-workflow, --source-ref, --source-digest и --deny-self-hosted-runners. Проверьте gh --version. Установка CLI: https://github.com/cli/cli/blob/trunk/docs/install_linux.md .
Скачайте три файла релиза 0.13.16 (ZIP, .sha256, .intoto.jsonl) непосредственно на VPS, без передачи через телефон.
Проверьте контрольную сумму и аттестацию до распаковки/выполнения.
В качестве --source-digest укажите SHA коммита тега с официальной страницы релиза.

    sha256sum -c LiftControl-v0.13.16-update.zip.sha256
    gh attestation verify LiftControl-v0.13.16-update.zip --bundle LiftControl-v0.13.16-update.zip.intoto.jsonl --repo sergeyviktorovich87/LiftControl --signer-workflow sergeyviktorovich87/LiftControl/.github/workflows/offline-patch.yml --source-ref refs/heads/main --source-digest SHA_КОММИТА_ТЕГА --deny-self-hosted-runners
    unzip LiftControl-v0.13.16-update.zip
    cd LiftControl-v0.13.16-update
    sudo bash update-panel.sh
    sudo bash install-auto-update.sh

Не включайте таймер в эксплуатации до проверки на стенде и проверки резервного восстановления.
Таймер запускается в 04:30 по Чите (после штатного резервирования в 03:30), без запуска пропущенного ночного события днём. Перед остановкой API проверяются незавершённые заявки о застревании: если они есть, установка откладывается. Возможность поступления новой заявки во время короткого перерыва сохраняется; дежурная связь должна работать независимо от панели.
Проверить немедленно: sudo systemctl start liftcontrol-github-update.service
Журнал: sudo journalctl -u liftcontrol-github-update.service -n 100 --no-pager
Отключить: sudo systemctl disable --now liftcontrol-github-update.timer
Не останавливайте уже работающий сервис посреди установки.

При новом или изменённом файле миграции автоматическая установка не выполняется. После просмотра релиза и резервного копирования: sudo /usr/bin/python3 /usr/local/lib/liftcontrol/github-updater.py --allow-migrations
При неудачной установке конкретная версия блокируется; сначала изучите журнал и состояние базы/образа, затем осознанно примените --retry.
Установщик возвращает прежний образ в предусмотренных случаях; автоматического восстановления базы поверх новых записей нет. Резервные копии проверяются штатным установщиком; копия вне VPS остаётся обязательной задачей.

Web-приложение не может запускать обновление, не имеет доступа к root/Docker. Обновление активной PWA предлагает перезагрузить интерфейс после сохранения форм. Вход, данные, роли и push остаются на прежнем сервере.

## Управление из панели (с 0.13.17)
В настройках владельца сервера (глобального Django superuser, не администратора организации) доступны проверка и установка подписанного релиза. Браузер создаёт только запись аудита через защищённую CSRF-сессию. Host-only bridge читает авторизованный запрос раз в 20 секунд, исполняет только фиксированный updater, публикует статус через существующий read-only /updates. Docker socket, shell и ключи не предоставляются веб-процессу. Установщик автоматически обновляет уже настроенную службу. При отключённом ночном таймере сохраняется его состояние; ручные запросы через bridge остаются доступны. Журнал: sudo journalctl -u liftcontrol-github-bridge.service -n 100 --no-pager. Если bridge не активирован, sudo bash install-auto-update.sh из проверенного пакета. 
