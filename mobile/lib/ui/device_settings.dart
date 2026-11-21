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
  bool _busy = false, _fcmReady = false, _fcmRegistered = false, _ownReady = false;
  String _error = '';
  String? _probeResult;
  int _statusRequest = 0;
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

  Future<void> _load({bool probe = false}) async {
    final serial = ++_statusRequest;
    final controller = widget.controller;
    final organization = controller.organization;
    try {
      final status = await DeviceBridge.status();
      final config = await controller.request('mobile/push/',
        expectedOrganization: organization);
      if (!mounted || serial != _statusRequest) return;
      setState(() {
        _status = status;
        _fcmReady = config['enabled'] == true;
        _fcmRegistered = config['registered'] == true ||
            (!config.containsKey('registered') && status['active'] == true);
        _ownReady = config['self_hosted'] == true;
        _error = '';
      });
      if (!probe) return;
      if (!_ownReady) {
        setState(() => _probeResult = 'Канал Лифт Контроля выключен.');
        return;
      }
      final result = await controller.request('mobile/push/self/?bootstrap=1',
        expectedOrganization: organization);
      if (result['provider'] != 'LIFTCONTROL') {
        throw const ApiError('Не получено подтверждение от сервера.');
      }
      controller.log.record('self_push_probe_ok');
      if (mounted && serial == _statusRequest) {
        setState(() => _probeResult = 'Свой канал отвечает.');
      }
    } catch (_) {
      controller.log.record(probe ? 'self_push_probe_failed' : 'push_status_load_failed');
      if (mounted && serial == _statusRequest) {
        setState(() {
          if (probe) {
            _probeResult = 'Свой канал не ответил.';
          } else {
            _error = 'Статус каналов недоступен.';
          }
        });
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

  Widget _sound(String category, String label) => ListTile(
    contentPadding: EdgeInsets.zero,
    title: Text(label),
    onTap: _busy ? null : () => _run(() async {
      await DeviceBridge.categorySettings(category);
      widget.controller.log.record(
        'notification_sound_settings_opened', route: category,
      );
    }),
    trailing: IconButton(
      tooltip: 'Проверить звук: $label',
      icon: const Icon(Icons.volume_up_outlined),
      onPressed: _busy ? null : () => _run(() async {
        await DeviceBridge.testCategory(category);
        widget.controller.log.record('notification_sound_tested', route: category);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Тестовое уведомление показано')),
          );
        }
      }),
    ),
  );

  @override
  Widget build(BuildContext context) => Sheet(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Звуки уведомлений', style: Theme.of(context).textTheme.titleMedium),
        if (_status['supports_notification_channels'] == true) ...[
          _sound('ordinary', _categories['ordinary']!),
          _sound('entrapment', _categories['entrapment']!),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text('Другие звуки'),
            children: [
              for (final entry in _categories.entries)
                if (entry.key != 'ordinary' && entry.key != 'entrapment')
                  _sound(entry.key, entry.value),
            ],
          ),
        ] else if (_status.isNotEmpty)
          OutlinedButton(
            onPressed: _busy ? null : () => _run(DeviceBridge.testPush),
            child: const Text('Проверить звук'),
          ),
        if (_status['notifications_allowed'] == false)
          TextButton(
            onPressed: _busy ? null : () => _run(DeviceBridge.notificationSettings),
            child: const Text('Разрешить уведомления Android'),
          ),
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: const Text('Проверка доставки'),
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (_error.isNotEmpty)
                    Text(_error)
                  else if (_status.isNotEmpty) ...[
                    Text('Google FCM: ${!_fcmReady ? 'выключен' :
                        _fcmRegistered ? 'устройство зарегистрировано' : 'устройство не зарегистрировано'}'),
                    Text('Лифт Контроль: ${_ownReady ? 'активен при открытом приложении' : 'выключен'}'),
                  ],
                  if (_probeResult case final String result) Text(result),
                  TextButton(
                    onPressed: _busy ? null : () => _run(() => _load(probe: true)),
                    child: const Text('Проверить связь'),
                  ),
                ],
              ),
            ),
          ],
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
      ],
    ),
  );
}
