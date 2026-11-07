import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../core/api.dart';
import '../core/controller.dart';
import '../core/diagnostics.dart';
import '../core/device_bridge.dart';
import 'common.dart';
import 'journal.dart';
import 'platform_bridge.dart';
import 'tickets.dart';
import 'staff.dart';
import 'device_settings.dart';

class MorePage extends StatelessWidget {
  const MorePage({super.key, required this.controller});
  final LiftController controller;
  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(18),
    children: [
      const SectionTitle('Рабочие разделы'),
      _link(
        context,
        Icons.build_outlined,
        'Журнал ТО',
        'Обслуживание, осмотры и ремонт',
        MaintenancePage(controller: controller),
      ),
      const SizedBox(height: 12),
      _link(
        context,
        Icons.chat_bubble_outline,
        'Чат бригады',
        'Сообщения выбранной организации',
        ChatPage(controller: controller),
      ),
      const SizedBox(height: 12),
      _link(
        context,
        Icons.inventory_2_outlined,
        'Запчасти',
        'Заявки на материалы',
        PartsPage(controller: controller),
      ),
      const SizedBox(height: 22),
      if (controller.organization != null) ...[
        _link(context, Icons.people_outline, 'Сотрудники', 'Команда, аккаунты и приглашения', StaffPage(controller: controller)),
        const SizedBox(height: 12),
      ],
      const SectionTitle('Аккаунт'),
      _link(
        context,
        Icons.settings_outlined,
        'Профиль и настройки',
        'Тема, устройства и диагностические логи',
        SettingsPage(controller: controller),
      ),
    ],
  );
  Widget _link(
    BuildContext context,
    IconData icon,
    String title,
    String subtitle,
    Widget page,
  ) => Card(
    child: ListTile(
      contentPadding: const EdgeInsets.all(16),
      leading: Icon(icon, color: Theme.of(context).colorScheme.primary),
      title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
      subtitle: Text(subtitle),
      trailing: const Icon(Icons.chevron_right),
      onTap: () => Navigator.push(
        context,
        MaterialPageRoute<void>(builder: (_) => page),
      ),
    ),
  );
}

class ChatPage extends StatefulWidget {
  const ChatPage({super.key, required this.controller});
  final LiftController controller;
  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final _input = TextEditingController();
  late int _org;
  bool _busy = false;
  @override
  void initState() {
    super.initState();
    _org = widget.controller.organization!;
  }

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    if (_busy || _input.text.trim().isEmpty) return;
    setState(() => _busy = true);
    try {
      await widget.controller.request(
        'chat/',
        method: 'POST',
        data: {'body': _input.text.trim()},
        expectedOrganization: _org,
      );
      _input.clear();
      await widget.controller.refresh();
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: widget.controller,
    organization: _org,
    builder: (context) {
      final c = widget.controller, rows = c.list('chat');
      return Scaffold(
        appBar: AppBar(
          title: const Text('Чат бригады'),
          actions: [
            IconButton(
              tooltip: 'Обновить',
              onPressed: c.refresh,
              icon: const Icon(Icons.sync),
            ),
          ],
        ),
        body: SafeArea(
          child: Column(
            children: [
              Expanded(
                child: rows.isEmpty
                    ? const EmptyState(
                        'Сообщений пока нет',
                        'Чат видят сотрудники этой организации.',
                        icon: Icons.chat_bubble_outline,
                      )
                    : ListView.builder(
                        reverse: true,
                        padding: const EdgeInsets.all(18),
                        itemCount: rows.length,
                        itemBuilder: (context, i) {
                          final m = rows[rows.length - 1 - i],
                              own = m['author'] == c.me['id'];
                          return Align(
                            alignment: own
                                ? Alignment.centerRight
                                : Alignment.centerLeft,
                            child: Container(
                              constraints: const BoxConstraints(maxWidth: 560),
                              margin: const EdgeInsets.only(bottom: 12),
                              padding: const EdgeInsets.all(15),
                              decoration: BoxDecoration(
                                color: own
                                    ? Theme.of(context).colorScheme.primary
                                          .withValues(alpha: 0.12)
                                    : Theme.of(context).colorScheme.surface,
                                borderRadius: BorderRadius.circular(18),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    text(m, 'author_name'),
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w700,
                                      fontSize: 12,
                                    ),
                                  ),
                                  const SizedBox(height: 6),
                                  SelectableText(text(m, 'body')),
                                  const SizedBox(height: 6),
                                  Text(
                                    dateLabel(m['created_at'], c.utcOffset),
                                    style: Theme.of(
                                      context,
                                    ).textTheme.bodySmall,
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 8, 10, 12),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Expanded(
                      child: TextField(
                        key: const Key('chat_message'),
                        controller: _input,
                        minLines: 1,
                        maxLines: 5,
                        maxLength: 4000,
                        decoration: const InputDecoration(
                          hintText: 'Сообщение',
                          counterText: '',
                        ),
                      ),
                    ),
                    const SizedBox(width: 7),
                    IconButton.filled(
                      tooltip: 'Отправить',
                      onPressed: c.canWrite && !_busy ? _send : null,
                      icon: _busy
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.send_outlined),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    },
  );
}

const partNames = {
  'NEW': 'Новая',
  'APPROVED': 'Одобрена',
  'ORDERED': 'Заказана',
  'RECEIVED': 'Получена',
  'ISSUED': 'Выдана',
  'CANCELED': 'Отменена',
};

class PartsPage extends StatelessWidget {
  const PartsPage({super.key, required this.controller});
  final LiftController controller;
  @override
  Widget build(BuildContext context) {
    final org = controller.organization!;
    return ScopePage(
      controller: controller,
      organization: org,
      builder: (context) => Scaffold(
        appBar: AppBar(
          title: const Text('Запчасти'),
          actions: [
            IconButton(
              tooltip: 'Новая заявка на запчасть',
              onPressed: controller.canWrite
                  ? () => Navigator.push(
                      context,
                      MaterialPageRoute<void>(
                        builder: (_) => PartForm(controller: controller),
                      ),
                    )
                  : null,
              icon: const Icon(Icons.add),
            ),
          ],
        ),
        body: RefreshIndicator(
          onRefresh: controller.refresh,
          child: ListView(
            padding: const EdgeInsets.all(18),
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              if (controller.list('parts').isEmpty)
                const EmptyState(
                  'Запросов пока нет',
                  'Механик может запросить запчасть для конкретного лифта.',
                  icon: Icons.inventory_2_outlined,
                ),
              for (final p in controller.list('parts').reversed)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Sheet(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${text(p, 'part')} · ${p['quantity']} шт.',
                          style: const TextStyle(fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 8),
                        Text(text(p, 'address')),
                        Text('Лифт ${text(p, 'elevator_label')}'),
                        const SizedBox(height: 8),
                        Text(partNames[p['status']] ?? text(p, 'status')),
                        if (text(p, 'notes', '').isNotEmpty) ...[
                          const SizedBox(height: 6),
                          Text(text(p, 'notes')),
                        ],
                        if (controller.me['can_manage'] == true)
                          TextButton(
                            onPressed: controller.canWrite
                                ? () async {
                                    final status = await showDialog<String>(
                                      context: context,
                                      builder: (context) => SimpleDialog(
                                        title: const Text('Статус запчасти'),
                                        children: [
                                          for (final entry in partNames.entries)
                                            SimpleDialogOption(
                                              onPressed: () => Navigator.pop(
                                                context,
                                                entry.key,
                                              ),
                                              child: Text(entry.value),
                                            ),
                                        ],
                                      ),
                                    );
                                    if (status == null) return;
                                    try {
                                      await controller.request(
                                        'parts/${p['id']}/',
                                        method: 'PATCH',
                                        data: {'status': status},
                                        expectedOrganization: org,
                                      );
                                      await controller.refresh();
                                    } catch (e) {
                                      if (context.mounted) {
                                        showError(context, e);
                                      }
                                    }
                                  }
                                : null,
                            child: const Text('Изменить статус'),
                          ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class PartForm extends StatefulWidget {
  const PartForm({super.key, required this.controller});
  final LiftController controller;
  @override
  State<PartForm> createState() => _PartFormState();
}

class _PartFormState extends State<PartForm> {
  final _form = GlobalKey<FormState>();
  final _part = TextEditingController(),
      _quantity = TextEditingController(text: '1'),
      _notes = TextEditingController();
  Json? _elevator;
  late int _org;
  bool _busy = false;
  @override
  void initState() {
    super.initState();
    _org = widget.controller.organization!;
  }

  @override
  void dispose() {
    _part.dispose();
    _quantity.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_busy || !_form.currentState!.validate()) return;
    if (_elevator == null) {
      showError(context, const ApiError('Выберите лифт.'));
      return;
    }
    setState(() => _busy = true);
    try {
      await widget.controller.request(
        'parts/',
        method: 'POST',
        data: {
          'elevator': _elevator!['id'],
          'part': _part.text.trim(),
          'quantity': int.parse(_quantity.text),
          'notes': _notes.text.trim(),
        },
        expectedOrganization: _org,
      );
      await widget.controller.refresh();
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: widget.controller,
    organization: _org,
    builder: (context) => Scaffold(
      appBar: AppBar(title: const Text('Запросить запчасть')),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.all(18),
          children: [
            OutlinedButton.icon(
              onPressed: _busy
                  ? null
                  : () async {
                      final e = await pickElevator(context, widget.controller);
                      if (e != null && mounted) setState(() => _elevator = e);
                    },
              icon: const Icon(Icons.elevator_outlined),
              label: Text(
                _elevator == null
                    ? 'Выбрать лифт'
                    : '${text(_elevator!, 'address')} · ${liftLabel(_elevator!)}',
              ),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _part,
              maxLength: 250,
              decoration: const InputDecoration(labelText: 'Название запчасти'),
              validator: (v) =>
                  (v?.trim().length ?? 0) < 2 ? 'Укажите запчасть' : null,
            ),
            const SizedBox(height: 14),
            TextFormField(
              controller: _quantity,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(labelText: 'Количество'),
              validator: (v) {
                final n = int.tryParse(v ?? '');
                return n == null || n < 1 || n > 32767
                    ? 'Количество от 1 до 32767'
                    : null;
              },
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _notes,
              minLines: 3,
              maxLines: 6,
              maxLength: 4000,
              decoration: const InputDecoration(
                labelText: 'Артикул, размеры, примечание',
              ),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: widget.controller.canWrite && !_busy ? _save : null,
              child: Text(_busy ? 'Отправка…' : 'Отправить запрос'),
            ),
          ],
        ),
      ),
    ),
  );
}

class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key, required this.controller});
  final LiftController controller;
  Future<void> _logout(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Выйти из аккаунта?'),
        content: const Text(
          'Данные и черновики этого аккаунта будут удалены с телефона.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Остаться'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Выйти'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    final revoked = await controller.logout();
    try {
      await PlatformBridge.clearPrivateFiles();
    } catch (_) {
      controller.log.record('private_file_cleanup_failed');
    }
    if (context.mounted) {
      Navigator.popUntil(context, (r) => r.isFirst);
      if (!revoked) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Выход на телефоне выполнен. Сервер не подтвердил отзыв сеанса.',
            ),
          ),
        );
      }
    }
  }

  Future<void> _logs(BuildContext context) async {
    await controller.log.flush();
    Json? device;
    List<dynamic>? nativeEvents;
    try {
      device = await DeviceBridge.status();
      nativeEvents = jsonDecode(await DeviceBridge.channel.invokeMethod<String>('nativeDiagnostics') ?? '[]') as List;
    } catch (_) { /* Older clients and non-Android test hosts have no native bridge. */ }
    final report = controller.log.export(device: device, nativeEvents: nativeEvents);
    if (!context.mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Диагностический отчёт'),
        content: SizedBox(
          width: 560,
          child: SingleChildScrollView(
            child: SelectableText(
              report,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 11),
            ),
          ),
        ),
        actions: [
          TextButton.icon(
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: report));
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Отчёт скопирован')),
                );
              }
            },
            icon: const Icon(Icons.copy),
            label: const Text('Копировать'),
          ),
          TextButton.icon(
            onPressed: () async {
              try {
                await PlatformBridge.shareReport(report);
              } catch (e) {
                if (context.mounted) showError(context, e);
              }
            },
            icon: const Icon(Icons.share_outlined),
            label: const Text('Поделиться'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Закрыть'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: controller,
    builder: (context, _) => Scaffold(
      appBar: AppBar(title: const Text('Профиль и настройки')),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          Sheet(
            child: Row(
              children: [
                CircleAvatar(
                  radius: 27,
                  backgroundColor: pale,
                  foregroundColor: forest,
                  child: Text(
                    text(controller.me, 'name', 'П').substring(0, 1),
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        text(controller.me, 'name'),
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      Text(
                        '${roleNames[controller.me['role']] ?? ''} · ${text(controller.me, 'organization', 'Организация не выбрана')}',
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Sheet(
            child: SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Тёмная тема'),
              subtitle: const Text('Сохраняется на этом устройстве'),
              value: controller.dark,
              onChanged: controller.setDark,
              secondary: const Icon(Icons.dark_mode_outlined),
            ),
          ),
          const SizedBox(height: 16),
          if (controller.demo) const Sheet(child: Text('Системные уведомления')) else NotificationSettings(controller: controller),
          const SizedBox(height: 16),
          if (!controller.demo) UpdatesSettings(controller: controller),
          const SizedBox(height: 16),
          Sheet(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Подключение',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 8),
                SelectableText(
                  controller.demo
                      ? 'Демонстрационный режим'
                      : controller.serverText,
                ),
                const SizedBox(height: 8),
                if (controller.me['can_manage_access'] == true)
                  TextButton.icon(onPressed: () => Navigator.push(context, MaterialPageRoute<void>(builder: (_) => StaffPage(controller: controller))), icon: const Icon(Icons.people_outline), label: const Text('Управление сотрудниками')),
                if (!controller.demo)
                  TextButton.icon(
                    onPressed: () => Navigator.push(
                      context,
                      MaterialPageRoute<void>(
                        builder: (_) => SessionsPage(controller: controller),
                      ),
                    ),
                    icon: const Icon(Icons.devices_outlined),
                    label: const Text('Устройства и сеансы'),
                  ),
                if (!controller.demo)
                  TextButton.icon(
                    onPressed: controller.online
                        ? () async {
                            final code = await askText(
                              context,
                              title: 'Добавить организацию',
                              label: 'Код приглашения',
                              minimum: 20,
                              maximum: 100,
                              action: 'Присоединиться',
                            );
                            if (code != null) {
                              try {
                                await controller.join(code);
                                if (context.mounted) {
                                  Navigator.popUntil(context, (r) => r.isFirst);
                                }
                              } catch (e) {
                                if (context.mounted) showError(context, e);
                              }
                            }
                          }
                        : null,
                    icon: const Icon(Icons.business_outlined),
                    label: const Text('Добавить организацию по приглашению'),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Sheet(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Тестовая версия',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 8),
                Text(
                  'Android ${Diagnostics.version} · ${Diagnostics.build.substring(0, Diagnostics.build.length < 8 ? Diagnostics.build.length : 8)}',
                ),
                const SizedBox(height: 8),
                const Text(
                  'Диагностика хранится на телефоне. В отчёт не включаются пароли, ключи входа, фотографии и тексты заявок.',
                  style: TextStyle(fontSize: 12),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: () => _logs(context),
                  icon: const Icon(Icons.bug_report_outlined),
                  label: const Text('Диагностический отчёт'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          OutlinedButton.icon(
            onPressed: () => _logout(context),
            icon: const Icon(Icons.logout),
            label: Text(
              controller.demo ? 'Выйти из демо' : 'Выйти из аккаунта',
            ),
          ),
          const SizedBox(height: 20),
        ],
      ),
    ),
  );
}

class SessionsPage extends StatefulWidget {
  const SessionsPage({super.key, required this.controller});
  final LiftController controller;
  @override
  State<SessionsPage> createState() => _SessionsPageState();
}

class _SessionsPageState extends State<SessionsPage> {
  List<Json> _rows = [];
  String _error = '';
  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final rows = await widget.controller.request('mobile/sessions/');
      if (mounted) {
        setState(() {
          _rows = records(rows);
          _error = '';
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Устройства и сеансы')),
    body: ListView(
      padding: const EdgeInsets.all(18),
      children: [
        if (_error.isNotEmpty) Text(_error),
        for (final row in _rows)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Sheet(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${text(row, 'device_name')}${row['current'] == true ? ' · это устройство' : ''}',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Последняя активность: ${dateLabel(row['last_seen_at'], widget.controller.utcOffset)}',
                  ),
                  if (row['current'] != true)
                    TextButton(
                      onPressed: () async {
                        try {
                          await widget.controller.request(
                            'mobile/sessions/${row['id']}/revoke/',
                            method: 'POST',
                            data: {},
                          );
                          await _load();
                        } catch (e) {
                          if (context.mounted) showError(context, e);
                        }
                      },
                      child: const Text('Завершить этот сеанс'),
                    ),
                ],
              ),
            ),
          ),
        const SizedBox(height: 12),
        const Text(
          'Сеанс действует до 30 дней. Смена пароля завершает вход во всех Android-устройствах.',
          style: TextStyle(fontSize: 12),
        ),
      ],
    ),
  );
}
