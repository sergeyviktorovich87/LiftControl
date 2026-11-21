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
  bool _ready = false, _busy = false, _fcmReady = false, _ownReady = false;
  String _error = '';
  static const _categories = {
    'ordinary': 'Обычные заявки',
    'urgent': 'Высокие и аварийные заявки',
    'entrapment': 'Застревание — люди в кабине',
    'updates': 'Изменения статусов',
    'tasks': 'Личные задания',
    'commissioning': 'Пусконаладка',
    'commissioning_chat': 'Чат наладчиков',
    'inspection': 'Освидетельствование',
    'app_update': 'Обновления приложения',
  };

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
      if (!mounted) return;
      setState(() => _status = status);
      final config = await widget.controller.request('mobile/push/');
      if (mounted) {
        setState(() {
          _fcmReady = config['enabled'] == true;
          _ownReady = config['self_hosted'] == true;
          _ready = _fcmReady || _ownReady;
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
              ? 'Уведомления подключаются автоматически после входа.'
              : 'Доставка уведомлений ещё не подключена. Сообщите администратору.',
        ),
        Text(
          _status.isEmpty
              ? 'Проверяем разрешение на уведомления Android…'
              : _status['notifications_allowed'] == true
              ? 'Android разрешает системные уведомления.'
              : 'Уведомления Android отключены или разрешение ещё не выдано.',
        ),
        Text(
          'Google FCM: ${_fcmReady ? 'настроен' : 'не настроен'}. '
          'LiftControl Push: ${_ownReady ? 'включён' : 'выключен'}.',
        ),
        Text(
          _ownReady
              ? 'Наш канал получает уведомления напрямую, пока приложение активно. Фоновая служба ещё разрабатывается.'
              : (_status['active'] == true
                    ? 'Уведомления FCM подключены.'
                    : 'Подключение FCM будет выполнено автоматически при доступной связи.'),
        ),
        if (_error.isNotEmpty) Text(_error),
        const SizedBox(height: 16),
        Text('Звуки уведомлений', style: Theme.of(context).textTheme.titleMedium),
        if (_status['supports_notification_channels'] == true) ...[
          const Text('Нажмите на категорию и выберите «Звук» в настройках Android.'),
          for (final entry in _categories.entries)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(entry.value),
              onTap: _busy ? null : () => _run(() async {
                await DeviceBridge.categorySettings(entry.key);
                widget.controller.log.record(
                  'notification_sound_settings_opened', route: entry.key,
                );
              }),
              trailing: IconButton(
                tooltip: 'Проверить звук: ${entry.value}',
                icon: const Icon(Icons.volume_up_outlined),
                onPressed: _busy ? null : () => _run(() async {
                  await DeviceBridge.testCategory(entry.key);
                  widget.controller.log.record(
                    'notification_sound_tested', route: entry.key,
                  );
                }),
              ),
            ),
        ] else if (_status.isNotEmpty) ...[
          const Text('Выбор звука по категориям доступен с Android 8.'),
          OutlinedButton(
            onPressed: _busy ? null : () => _run(DeviceBridge.testPush),
            child: const Text('Проверить звук'),
          ),
        ],
        TextButton(
          onPressed: _busy ? null : () => _run(DeviceBridge.notificationSettings),
          child: const Text('Все настройки уведомлений Android'),
        ),
      ],
    ),
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
      await c.installUpdate(release);
    } catch (e) {
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
            'Android ${_device['version'] ?? 'не определена'} · сборка ${_device['version_code'] ?? '—'}',
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

class PushPreferencesSettings extends StatefulWidget {
  const PushPreferencesSettings({super.key, required this.controller});

  final LiftController controller;

  @override
  State<PushPreferencesSettings> createState() => _PushPreferencesSettingsState();
}

class _PushPreferencesSettingsState extends State<PushPreferencesSettings> {
  static const _path = 'notification-preferences/';
  static const _days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
  late final int _organization;
  Json? _settings;
  bool _busy = false, _saved = false;
  String _error = '';
  LiftController get c => widget.controller;

  @override
  void initState() {
    super.initState();
    _organization = c.organization!;
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final data = await c.request(_path, expectedOrganization: _organization);
      if (!mounted) return;
      if (data is! Map || !data.containsKey('quiet_enabled')) {
        throw const ApiError('Обновите сервер, чтобы настроить тихие часы.');
      }
      setState(() {
        _settings = Map<String, dynamic>.from(data);
        _error = '';
      });
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
      c.log.record('push_preferences_load_failed');
    }
  }

  void _change(String key, dynamic value) {
    setState(() {
      _settings![key] = value;
      _saved = false;
      _error = '';
    });
  }

  Future<void> _pick(String key, String label) async {
    final parts = (_settings![key] as String).split(':').map(int.parse).toList();
    final chosen = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: parts[0], minute: parts[1]),
      helpText: label,
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(alwaysUse24HourFormat: true),
        child: child!,
      ),
    );
    if (chosen != null && mounted) {
      final hour = chosen.hour.toString().padLeft(2, '0');
      final minute = chosen.minute.toString().padLeft(2, '0');
      _change(key, '$hour:$minute');
    }
  }

  Future<void> _save() async {
    if (_busy || c.organization != _organization) return;
    setState(() {
      _busy = true;
      _error = '';
      _saved = false;
    });
    try {
      final data = await c.request(
        _path,
        method: 'PATCH',
        data: {
          for (final key in const [
            'only_mine',
            'quiet_enabled',
            'quiet_start',
            'quiet_end',
            'muted_weekdays',
          ])
            key: _settings![key],
        },
        expectedOrganization: _organization,
      );
      if (mounted) {
        setState(() {
          _settings = Map<String, dynamic>.from(data as Map);
          _saved = true;
        });
      }
      c.log.record('push_preferences_saved');
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
      c.log.record('push_preferences_save_failed');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Sheet(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Настройки push', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Text('${text(c.me, 'organization')}. Время — по часовому поясу организации.'),
        if (_settings == null && _error.isEmpty)
          const LinearProgressIndicator(),
        if (_settings == null && _error.isNotEmpty)
          TextButton(onPressed: _load, child: const Text('Повторить')),
        if (_settings case final settings?) ...[
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Только мои push'),
            subtitle: const Text('Мои заявки и задания, заявки дежурной смены и моя пусконаладка.'),
            value: settings['only_mine'] == true,
            onChanged: _busy ? null : (value) => _change('only_mine', value),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Тихие часы'),
            subtitle: const Text('Ежедневный интервал без push.'),
            value: settings['quiet_enabled'] == true,
            onChanged: _busy ? null : (value) => _change('quiet_enabled', value),
          ),
          if (settings['quiet_enabled'] == true)
            Wrap(
              spacing: 8,
              children: [
                OutlinedButton(
                  onPressed: _busy ? null : () => _pick('quiet_start', 'Начало тихих часов'),
                  child: Text("С ${settings['quiet_start']}"),
                ),
                OutlinedButton(
                  onPressed: _busy ? null : () => _pick('quiet_end', 'Конец тихих часов'),
                  child: Text("До ${settings['quiet_end']}"),
                ),
              ],
            ),
          const SizedBox(height: 8),
          const Text('Дни без push целиком'),
          Wrap(
            spacing: 6,
            children: [
              for (final (index, title) in _days.indexed)
                FilterChip(
                  label: Text(title),
                  selected: (settings['muted_weekdays'] as List).contains(index),
                  onSelected: _busy ? null : (selected) {
                    final days = List<int>.from(settings['muted_weekdays'] as List);
                    if (selected) {
                      days.add(index);
                    } else {
                      days.remove(index);
                    }
                    _change('muted_weekdays', days);
                  },
                ),
            ],
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: !_busy && c.canWrite ? _save : null,
            child: Text(_busy ? 'Сохранение…' : 'Сохранить настройки push'),
          ),
          if (_saved) const Text('Настройки сохранены.'),
        ],
        if (_error.isNotEmpty) Text(_error),
        const SizedBox(height: 8),
        const Text('Все доступные события сохраняются в центре уведомлений.'),
      ],
    ),
  );
}
