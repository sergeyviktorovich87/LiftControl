import 'dart:async';
import 'package:flutter/material.dart';
import '../core/api.dart';
import '../core/controller.dart';
import '../core/device_bridge.dart';
import 'common.dart';

class NotificationSettings extends StatefulWidget {
  const NotificationSettings({super.key, required this.controller});
  final LiftController controller;
  @override
  State<NotificationSettings> createState() => _NotificationSettingsState();
}

class _NotificationSettingsState extends State<NotificationSettings>
    with WidgetsBindingObserver {
  Json _status = {};
  bool _ready = false, _busy = false;
  String _error = '';
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_load());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final status = await DeviceBridge.status();
      final config = await widget.controller.request('mobile/push/');
      if (mounted) {
        setState(() {
          _status = status;
          _ready = config['enabled'] == true;
          _error = '';
        });
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => _error =
              'Не удалось проверить уведомления. Обновите сервер и повторите проверку.',
        );
      }
    }
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
      await _load();
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Sheet(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Системные уведомления',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 8),
        Text(
          _ready
              ? 'Доставка с сервера FCM настроена.'
              : 'Доставка с сервера ещё не настроена. Администратору нужно подключить Firebase.',
        ),
        Text(
          _status['notifications_allowed'] == true
              ? 'Android разрешает системные уведомления.'
              : 'Уведомления Android отключены или разрешение ещё не выдано.',
        ),
        Text(
          _status['active'] == true
              ? 'Этот телефон подписан на заявки ваших организаций.'
              : 'Этот телефон пока не подписан.',
        ),
        if (_error.isNotEmpty) Text(_error),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            FilledButton(
              onPressed:
                  !_busy &&
                      widget.controller.canWrite &&
                      (_ready || _status['active'] == true)
                  ? () => _run(
                      () => _status['active'] == true
                          ? widget.controller.disablePush()
                          : widget.controller.enablePush(),
                    )
                  : null,
              child: Text(_status['active'] == true ? 'Отключить' : 'Включить'),
            ),
            OutlinedButton(
              onPressed: !_busy ? () => _run(DeviceBridge.testPush) : null,
              child: const Text('Проверить звук'),
            ),
            TextButton(
              onPressed: !_busy
                  ? () => _run(DeviceBridge.notificationSettings)
                  : null,
              child: const Text('Настройки Android'),
            ),
            TextButton(
              onPressed: !_busy && widget.controller.canWrite ? _load : null,
              child: const Text('Проверить подключение'),
            ),
          ],
        ),
        const Text(
          '«Проверить звук» проверяет уведомление на телефоне. Доставку с сервера проверяют новой заявкой.',
          style: TextStyle(fontSize: 12),
        ),
        if (widget.controller.me['field_ops_api'] == 1)
          NotificationCategorySettings(controller: widget.controller),
      ],
    ),
  );
}

class NotificationCategorySettings extends StatefulWidget {
  const NotificationCategorySettings({super.key, required this.controller});
  final LiftController controller;
  @override
  State<NotificationCategorySettings> createState() =>
      _NotificationCategorySettingsState();
}

class _NotificationCategorySettingsState
    extends State<NotificationCategorySettings> {
  Json? _values;
  String _error = '';
  bool _busy = false;
  late final int _org;
  static const _groups = [
    ('entrapment', 'Застревание', 'Люди в кабине. Отдельный срочный сигнал.'),
    ('urgent', 'Высокие и аварийные заявки', 'Срочные обращения.'),
    ('ordinary', 'Обычные заявки', 'Обычный и низкий приоритет.'),
    (
      'updates',
      'Изменения статусов',
      'Принятие, остановка, продолжение и завершение.',
    ),
    ('tasks', 'Личные задания', 'Назначение и результат личной работы.'),
  ];
  @override
  void initState() {
    super.initState();
    _org = widget.controller.organization!;
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final values = await widget.controller.request(
        'notification-preferences/',
        expectedOrganization: _org,
      );
      if (mounted) setState(() => _values = Map<String, dynamic>.from(values));
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    }
  }

  Future<void> _change(String group, bool enabled) async {
    setState(() => _busy = true);
    try {
      final values = await widget.controller.request(
        'notification-preferences/',
        method: 'PATCH',
        data: {group: enabled},
        expectedOrganization: _org,
      );
      if (mounted) setState(() => _values = Map<String, dynamic>.from(values));
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _native(Future<void> Function() action) async {
    try {
      await action();
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Divider(height: 30),
      Text(
        'Категории уведомлений',
        style: Theme.of(context).textTheme.titleMedium,
      ),
      const Text(
        'Выбор действует на всех ваших устройствах в этой организации.',
      ),
      for (final group in _groups) ...[
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(group.$2),
          subtitle: Text(group.$3),
          value: _values?[group.$1] == true,
          onChanged: _values != null && !_busy && widget.controller.canWrite
              ? (enabled) => _change(group.$1, enabled)
              : null,
        ),
        TextButton(
          onPressed: () =>
              _native(() => DeviceBridge.categorySettings(group.$1)),
          child: Text('Звук и вибрация: ${group.$2.toLowerCase()}'),
        ),
      ],
      OutlinedButton.icon(
        onPressed: () => _native(() => DeviceBridge.testCategory('entrapment')),
        icon: const Icon(Icons.notification_important_outlined),
        label: const Text('Проверить сигнал застревания'),
      ),
      if (_error.isNotEmpty) Text(_error),
    ],
  );
}

class UpdatesSettings extends StatefulWidget {
  const UpdatesSettings({super.key, required this.controller});
  final LiftController controller;
  @override
  State<UpdatesSettings> createState() => _UpdatesSettingsState();
}

class _UpdatesSettingsState extends State<UpdatesSettings> {
  Json _device = {}, _catalogue = {};
  bool _busy = false;
  String _error = '';
  @override
  void initState() {
    super.initState();
    unawaited(_check());
  }

  Future<void> _check() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      final device = await DeviceBridge.status();
      final data = await widget.controller.checkUpdates(force: true);
      if (mounted) {
        setState(() {
          _device = device;
          _catalogue = data ?? {};
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _install(Json release) async {
    setState(() => _busy = true);
    final c = widget.controller;
    try {
      if (c.session == null || c.organization == null || !c.canWrite) {
        throw const ApiError('Нужна связь с сервером.');
      }
      await DeviceBridge.installUpdate({
        ...release,
        'server': c.session!['server'],
        'token': c.session!['token'],
        'organization': c.organization,
      });
      c.log.record('update_installer_opened');
    } catch (e) {
      c.log.record('update_install_failed');
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final release = _catalogue['android'] is Map
        ? Map<String, dynamic>.from(_catalogue['android'])
        : null;
    final available =
        release != null &&
        (release['version_code'] as int) >
            ((_device['version_code'] as num?)?.toInt() ?? 0);
    return Sheet(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Обновления', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(
            'Android ${_device['version'] ?? '0.2.0'} · сборка ${_device['version_code'] ?? '—'}',
          ),
          if (_catalogue['installed'] is Map)
            Text('Панель и сервер ${_catalogue['installed']['panel']}'),
          Text(
            available
                ? 'Доступна версия ${release['version']}'
                : 'Новых опубликованных обновлений приложения нет.',
          ),
          if (available && text(release, 'notes', '').isNotEmpty)
            Text(text(release, 'notes')),
          if (_error.isNotEmpty) Text(_error),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton(
                onPressed: !_busy && widget.controller.canWrite ? _check : null,
                child: Text(
                  _busy ? 'Проверка / загрузка…' : 'Проверить обновления',
                ),
              ),
              if (available)
                FilledButton(
                  onPressed: !_busy && widget.controller.canWrite
                      ? () => _install(release)
                      : null,
                  child: const Text('Скачать и установить'),
                ),
            ],
          ),
          const Text(
            'Перед установкой проверяются файл, номер версии и подпись приложения. Установку подтверждает Android.',
            style: TextStyle(fontSize: 12),
          ),
        ],
      ),
    );
  }
}
