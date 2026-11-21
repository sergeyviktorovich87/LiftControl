import 'dart:async';

import 'package:flutter/material.dart';

import '../core/controller.dart';
import '../core/api.dart';
import '../core/device_bridge.dart';
import 'common.dart';
import 'tickets.dart';
import 'elevators.dart';
import 'duty.dart';
import 'extras.dart';
import 'chat.dart';
import 'tasks.dart';
import 'sync_queue.dart';
import 'commissioning.dart';
import 'notifications.dart';
import 'staff.dart';
import 'media_library.dart';
import 'adaptive_drawer.dart';

class LiftShell extends StatefulWidget {
  const LiftShell({super.key, required this.controller});
  final LiftController controller;
  @override
  State<LiftShell> createState() => _LiftShellState();
}

class _LiftShellState extends State<LiftShell> with WidgetsBindingObserver {
  int _index = 0;
  int? _presentedUpdate;
  int _minimumUpdateCheck = 1;
  bool _updateDialogOpen = false, _installingUpdate = false;
  LiftController get c => widget.controller;
  @override
  void initState() {
    super.initState();
    _minimumUpdateCheck = c.updateCheckSerial + 1;
    WidgetsBinding.instance.addObserver(this);
    c.addListener(_updatesChanged);
    DeviceBridge.channel.setMethodCallHandler((call) async {
      if (call.method == 'networkChanged') {
        await c.refresh();
        await c.syncDevice(forceUpdates: true);
      }
      if (call.method == 'pushTokenChanged') await c.syncDevice();
      if (call.method == 'notification' && call.arguments is Map) {
        await _notification(Map<String, dynamic>.from(call.arguments));
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      unawaited(_checkForUpdate());
      unawaited(c.syncDevice());
      try {
        final data = await DeviceBridge.consumeNotification();
        if (data != null) await _notification(data);
      } catch (_) {
        /* Android only. */
      }
    });
  }

  @override
  void dispose() {
    c.removeListener(_updatesChanged);
    WidgetsBinding.instance.removeObserver(this);
    DeviceBridge.channel.setMethodCallHandler(null);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed &&
        !_updateDialogOpen &&
        !_installingUpdate) {
      _presentedUpdate = null;
      _minimumUpdateCheck = c.updateCheckSerial + 1;
      unawaited(_checkForUpdate());
    }
  }

  Future<void> _checkForUpdate() async {
    try {
      await c.checkUpdates(force: true);
      _updatesChanged();
    } catch (_) {
      c.log.record('update_check_failed');
    }
  }

  void _updatesChanged() {
    if (!mounted ||
        c.updateCheckSerial < _minimumUpdateCheck ||
        !c.hasUpdate ||
        !c.canWrite ||
        _updateDialogOpen ||
        _installingUpdate) {
      return;
    }
    final release = Map<String, dynamic>.from(c.updates!['android']);
    if (release['version_code'] == _presentedUpdate) return;
    _presentedUpdate = release['version_code'] as int;
    _updateDialogOpen = true;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      final notes = text(release, 'notes', '').trim();
      c.log.record('update_prompt_shown');
      final install = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Доступно обновление'),
          content: SingleChildScrollView(
            child: Text(
              'Новая версия LiftControl ${release['version']}. Обновить приложение?'
              '${notes.isEmpty ? '' : '\n\n$notes'}',
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Позже'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Обновить'),
            ),
          ],
        ),
      );
      _updateDialogOpen = false;
      if (install != true || !mounted || !c.loggedIn) return;
      _installingUpdate = true;
      final navigator = Navigator.of(context, rootNavigator: true);
      unawaited(
        showDialog<void>(
          context: context,
          barrierDismissible: false,
          builder: (_) => const PopScope(
            canPop: false,
            child: AlertDialog(
              content: Row(
                children: [
                  CircularProgressIndicator(),
                  SizedBox(width: 20),
                  Expanded(child: Text('Загрузка обновления…')),
                ],
              ),
            ),
          ),
        ),
      );
      Object? error;
      try {
        await c.installUpdate(release);
      } catch (e) {
        error = e;
      } finally {
        _installingUpdate = false;
        if (navigator.mounted) navigator.pop();
      }
      if (mounted && error != null) showError(context, error);
    });
    // A network response can arrive between frames. A post-frame callback by
    // itself does not request a frame, so explicitly schedule presentation.
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  Future<void> _notification(Json data) async {
    if (data['target'] == 'app_update') {
      c.log.record('update_notification_opened');
      await _checkForUpdate();
      return;
    }
    final target = data['target'];
    final org = data['organization'],
        ticket = data[target == 'task' || target == 'commissioning' ||
            target == 'commissioning_chat' ? target : 'ticket'];
    if (org is! int ||
        ticket is! int ||
        ticket <= 0 ||
        !c.organizations.any((o) => o['id'] == org)) {
      return;
    }
    try {
      if (c.organization != org) {
        await c.selectOrganization(org);
        if (mounted) Navigator.popUntil(context, (r) => r.isFirst);
      }
      if (mounted && c.organization == org) {
        if (target == 'commissioning_chat') {
          if (c.me['can_commissioning'] != true) return;
          Navigator.push(context, MaterialPageRoute<void>(
            builder: (_) => ChatPage(controller: c, commissioning: true, messageId: ticket),
          ));
        } else if (target == 'commissioning') {
          if (c.me['can_commissioning'] != true) return;
          Navigator.push(context, MaterialPageRoute<void>(
            builder: (_) => NotificationsPage(controller: c),
          ));
        } else if (target == 'task') {
          openTask(context, c, ticket);
        } else {
          openTicket(context, c, ticket);
        }
      }
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  void _openDrawerSection(
    BuildContext drawerContext,
    LiftMenuSection section,
  ) {
    Scaffold.of(drawerContext).closeDrawer();
    c.log.record('drawer_section_opened', route: section.name);
    final commissioningOnly = c.me['commissioning_only'] == true;
    final tab = commissioningOnly
        ? (section == LiftMenuSection.commissioning ? 0 : null)
        : switch (section) {
            LiftMenuSection.home => 0,
            LiftMenuSection.tickets => 1,
            LiftMenuSection.elevators => 2,
            LiftMenuSection.duty => 3,
            _ => null,
          };
    if (tab != null) {
      setState(() => _index = tab);
      return;
    }
    final page = switch (section) {
      LiftMenuSection.tasks => TasksPage(controller: c),
      LiftMenuSection.commissioning => CommissioningPage(
        key: ValueKey(c.organization),
        controller: c,
      ),
      LiftMenuSection.parts => PartsPage(controller: c),
      LiftMenuSection.media => MediaPage(controller: c),
      LiftMenuSection.staff => StaffPage(controller: c),
      LiftMenuSection.chat => ChatPage(controller: c),
      LiftMenuSection.settings => SettingsPage(controller: c),
      _ => null,
    };
    if (page != null && mounted) {
      Navigator.of(context).push(
        MaterialPageRoute<void>(builder: (_) => page),
      );
    }
  }
  Future<void> _organization() async {
    final selected = await showModalBottomSheet<int>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SectionTitle('Организации'),
                for (final o in c.organizations)
                  ListTile(
                    leading: const Icon(Icons.business_outlined),
                    title: Text(text(o, 'name')),
                    subtitle: Text(roleNames[o['role']] ?? ''),
                    trailing: o['id'] == c.organization
                        ? const Icon(Icons.check_circle, color: green)
                        : null,
                    onTap: () => Navigator.pop(context, o['id'] as int),
                  ),
                if (!c.demo)
                  ListTile(
                    leading: const Icon(Icons.add_circle_outline),
                    title: const Text('Присоединиться по приглашению'),
                    onTap: () => Navigator.pop(context, -1),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
    if (selected == null || !mounted) return;
    if (selected == -1) {
      await joinOrganizationDialog(context, c);
      return;
    }
    try {
      await c.selectOrganization(selected);
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: c,
    builder: (context, _) => _shell(context),
  );

  Widget _shell(BuildContext context) => LayoutBuilder(
    builder: (context, box) {
      final commissionedOnly = c.me['commissioning_only'] == true;
      final hasCommissioning = c.me['can_commissioning'] == true;
      final menuItems = <LiftMenuItem>[
        if (!commissionedOnly) ...[
          const LiftMenuItem(
            LiftMenuSection.home, 'Главная', Icons.dashboard_outlined,
          ),
          const LiftMenuItem(
            LiftMenuSection.tickets, 'Заявки', Icons.assignment_outlined,
          ),
          const LiftMenuItem(
            LiftMenuSection.elevators, 'Объекты', Icons.elevator_outlined,
          ),
          const LiftMenuItem(
            LiftMenuSection.duty, 'Дежурство', Icons.calendar_month_outlined,
          ),
        ],
        if (commissionedOnly && hasCommissioning)
          const LiftMenuItem(
            LiftMenuSection.commissioning,
            'Пусконаладка',
            Icons.precision_manufacturing_outlined,
          ),
        if (!commissionedOnly && c.organization != null) ...[
          const LiftMenuItem(
            LiftMenuSection.tasks, 'Личные задания',
            Icons.assignment_ind_outlined,
          ),
          if (hasCommissioning)
            const LiftMenuItem(
              LiftMenuSection.commissioning, 'Пусконаладка',
              Icons.precision_manufacturing_outlined,
            ),
          const LiftMenuItem(
            LiftMenuSection.parts, 'Запчасти', Icons.inventory_2_outlined,
          ),
          const LiftMenuItem(
            LiftMenuSection.media, 'Медиаматериалы',
            Icons.photo_library_outlined,
          ),
          const LiftMenuItem(
            LiftMenuSection.staff, 'Сотрудники', Icons.people_outline,
          ),
          const LiftMenuItem(
            LiftMenuSection.chat, 'Чат бригады', Icons.chat_bubble_outline,
          ),
        ],
        const LiftMenuItem(
          LiftMenuSection.settings, 'Профиль и настройки',
          Icons.settings_outlined,
        ),
      ];
      final selectedSection = commissionedOnly
          ? (hasCommissioning ? LiftMenuSection.commissioning : null)
          : switch (_index) {
              0 => LiftMenuSection.home,
              1 => LiftMenuSection.tickets,
              2 => LiftMenuSection.elevators,
              3 => LiftMenuSection.duty,
              _ => null,
            };
      final page = c.organization == null
          ? _NoOrganization(c: c, onSelect: _organization)
          : commissionedOnly
          ? (_index == 0 && hasCommissioning
                ? CommissioningPage(
                    key: ValueKey(c.organization),
                    controller: c,
                  )
                : MorePage(controller: c))
          : switch (_index) {
              0 => HomePage(
                controller: c,
                onSection: (i) => setState(() => _index = i),
              ),
              1 => TicketsPage(controller: c),
              2 => ElevatorsPage(controller: c),
              3 => DutyPage(controller: c),
              _ => MorePage(controller: c),
            };
      return Scaffold(
        drawer: Builder(
          builder: (drawerContext) => AdaptiveNavigationDrawer(
            items: menuItems,
            selectedSection: selectedSection,
            unread: {for (final item in menuItems)
              item.section: c.unreadNotifications(item.section.name)},
            onSelected: (section) =>
                _openDrawerSection(drawerContext, section),
          ),
        ),
        appBar: AppBar(
          leadingWidth: 48,
          titleSpacing: 0,
          leading: Builder(
            builder: (scaffoldContext) => IconButton(
              tooltip: 'Открыть боковое меню',
              icon: const Icon(Icons.menu),
              onPressed: () => Scaffold.of(scaffoldContext).openDrawer(),
            ),
          ),
          title: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'LiftControl',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: box.maxWidth < 360 ? 17 : 20,
                ),
              ),
              InkWell(
                key: const Key('organization-switch'),
                onTap: _organization,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Flexible(
                      child: Text(
                        text(
                          c.organizations.firstWhere(
                            (o) => o['id'] == c.organization,
                            orElse: () => {},
                          ),
                          'name',
                          'Выбрать организацию',
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                    const Icon(Icons.expand_more, size: 17),
                  ],
                ),
              ),
            ],
          ),
          actions: [
            IconButton(
              tooltip: 'Центр уведомлений',
              onPressed: c.organization == null
                  ? null
                  : () => Navigator.push(
                      context,
                      MaterialPageRoute<void>(
                        builder: (_) => NotificationsPage(controller: c),
                      ),
                    ),
              icon: unreadBadge(c.unreadNotifications(),
                child: const Icon(Icons.notifications_outlined)),
            ),
            if (!commissionedOnly)
              IconButton(
                tooltip: 'Чат бригады',
                onPressed: c.organization == null
                    ? null
                    : () => Navigator.push(
                        context,
                        MaterialPageRoute<void>(
                          builder: (_) => ChatPage(controller: c),
                        ),
                      ),
                icon: unreadBadge(c.unreadNotifications('chat'),
                  child: const Icon(Icons.chat_bubble_outline)),
              ),
            IconButton(
              tooltip: 'Обновить',
              onPressed: c.refreshing ? null : c.refresh,
              icon: c.refreshing
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.sync),
            ),
            IconButton(
              tooltip: 'Профиль и настройки',
              onPressed: () => Navigator.push(
                context,
                MaterialPageRoute<void>(
                  builder: (_) => SettingsPage(controller: c),
                ),
              ),
              icon: const Icon(Icons.account_circle_outlined),
            ),
          ],
        ),
        body: Column(
          children: [
            if (c.hasUpdate)
              _Banner(
                color: const Color(0xFFE8F1E5),
                text: 'Доступно обновление приложения',
                action: 'Открыть',
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute<void>(
                    builder: (_) => SettingsPage(controller: c),
                  ),
                ),
              ),
            if (c.pendingCount > 0)
              _Banner(
                color: const Color(0xFFE9DBBC),
                text: c.failedCount > 0
                    ? 'Требуют внимания: ${c.failedCount} · сохранено на телефоне'
                    : 'Ожидает отправки: ${c.pendingCount}',
                action: 'Очередь',
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute<void>(
                    builder: (_) => SyncQueuePage(controller: c),
                  ),
                ),
              ),
            if (c.demo)
              _Banner(
                color: const Color(0xFFE9DBBC),
                text: 'Демо · пример данных, без подключения к серверу',
                action: 'Выйти',
                onTap: c.logout,
              ),
            if (!c.demo && !c.online && c.loggedIn)
              _Banner(
                color: const Color(0xFFE9DBBC),
                text: c.snapshot.isEmpty
                    ? 'Подключение к серверу…'
                    : 'Нет связи · сохранённые данные',
                action: 'Обновить',
                onTap: c.refresh,
              ),
            if (!c.demo && c.error.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 6,
                ),
                child: Text(
                  c.error,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                  textAlign: TextAlign.center,
                ),
              ),
            Expanded(
              child: SafeArea(
                top: false,
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 1040),
                    child: page,
                  ),
                ),
              ),
            ),
          ],
        ),
      );
    },
  );
}

class _Banner extends StatelessWidget {
  const _Banner({
    required this.color,
    required this.text,
    required this.action,
    required this.onTap,
  });
  final Color color;
  final String text, action;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Container(
    color: color,
    padding: const EdgeInsets.only(left: 16, right: 8),
    child: Row(
      children: [
        Expanded(
          child: Text(
            text,
            style: const TextStyle(color: forest, fontSize: 12),
          ),
        ),
        TextButton(
          onPressed: onTap,
          child: Text(action, style: const TextStyle(color: forest)),
        ),
      ],
    ),
  );
}

class _NoOrganization extends StatelessWidget {
  const _NoOrganization({required this.c, required this.onSelect});
  final LiftController c;
  final VoidCallback onSelect;
  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(24),
    children: [
      const EmptyState(
        'Организация не выбрана',
        'Руководитель выдаёт приглашение и связывает аккаунт с карточкой механика.',
        icon: Icons.business_outlined,
      ),
      if (c.organizations.isNotEmpty)
        FilledButton(
          onPressed: onSelect,
          child: const Text('Выбрать организацию'),
        ),
      const SizedBox(height: 12),
      OutlinedButton(
        onPressed: c.online ? () => joinOrganizationDialog(context, c) : null,
        child: const Text('Ввести код приглашения'),
      ),
    ],
  );
}

class HomePage extends StatelessWidget {
  const HomePage({
    super.key,
    required this.controller,
    required this.onSection,
  });
  final LiftController controller;
  final ValueChanged<int> onSection;
  @override
  Widget build(BuildContext context) {
    final c = controller,
        open = c
            .list('tickets')
            .where((t) => !['DONE', 'CANCELED'].contains(t['status']))
            .toList();
    final mine = open
        .where((t) => t['assigned_to'] == c.me['technician'])
        .length;
    return RefreshIndicator(
      onRefresh: c.refresh,
      child: ListView(
        padding: const EdgeInsets.all(18),
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          Text('Рабочий день', style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 5),
          Text(
            'Здравствуйте, ${text(c.me, 'name', 'коллега')}',
            style: Theme.of(
              context,
            ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 20),
          DutyCard(controller: c),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton.icon(
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute<void>(
                    builder: (_) => TasksPage(controller: c),
                  ),
                ),
                icon: const Icon(Icons.assignment_ind_outlined),
                label: Text(
                  'Личные задания · ${c.list('tasks').where((row) => !['DONE', 'CANCELED'].contains(row['status'])).length}',
                ),
              ),
              if (c.me['can_manage'] == true && c.me['field_ops_api'] == 1)
                FilledButton.icon(
                  onPressed: c.canWrite
                      ? () => Navigator.push(
                          context,
                          MaterialPageRoute<void>(
                            builder: (_) =>
                                TasksPage(controller: c, create: true),
                          ),
                        )
                      : null,
                  icon: const Icon(Icons.add),
                  label: const Text('Доп. задание'),
                ),
            ],
          ),
          const SizedBox(height: 16),
          LayoutBuilder(
            builder: (context, box) => Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                _Metric(
                  title: 'Активных заявок',
                  value: '${open.length}',
                  icon: Icons.assignment_outlined,
                  width: (box.maxWidth - 12) / 2,
                  onTap: () => onSection(1),
                ),
                _Metric(
                  title: 'Назначено мне',
                  value: '$mine',
                  icon: Icons.person_outline,
                  width: (box.maxWidth - 12) / 2,
                  onTap: () => onSection(1),
                ),
                _Metric(
                  title: 'Лифтов в работе',
                  value: '${c.list('elevators').length}',
                  icon: Icons.elevator_outlined,
                  width: (box.maxWidth - 12) / 2,
                  onTap: () => onSection(2),
                ),
                _Metric(
                  title: 'Плановое ТО',
                  value:
                      '${c.list('maintenance').where((m) => m['completed_at'] == null).length}',
                  icon: Icons.build_outlined,
                  width: (box.maxWidth - 12) / 2,
                  onTap: () => onSection(2),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          if (c.me['can_create_ticket'] == true)
            FilledButton.icon(
              onPressed: c.canCreateTicket
                  ? () => Navigator.push(
                      context,
                      MaterialPageRoute<void>(
                        builder: (_) => CreateTicketPage(controller: c),
                      ),
                    )
                  : null,
              icon: const Icon(Icons.add),
              label: const Text('Создать заявку'),
            ),
          SectionTitle(
            'Последние заявки',
            trailing: TextButton(
              onPressed: () => onSection(1),
              child: const Text('Все'),
            ),
          ),
          if (open.isEmpty)
            const Sheet(
              child: EmptyState(
                'Активных заявок нет',
                'Новые обращения появятся здесь.',
              ),
            ),
          for (final t in open.reversed.take(4))
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: TicketTile(
                t,
                controller: c,
                onTap: () => openTicket(context, c, t['id'] as int),
              ),
            ),
          if (c.syncedAt != null)
            Text(
              'Обновлено ${dateLabel(c.syncedAt!.toIso8601String(), c.utcOffset)} · ${text(c.me, 'timezone', 'время организации')}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({
    required this.title,
    required this.value,
    required this.icon,
    required this.width,
    required this.onTap,
  });
  final String title, value;
  final IconData icon;
  final double width;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => SizedBox(
    width: width,
    child: Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(icon, color: Theme.of(context).colorScheme.primary),
                  const Spacer(),
                  const Icon(Icons.north_east, size: 16),
                ],
              ),
              const SizedBox(height: 14),
              Text(
                value,
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 4),
              Text(title, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
      ),
    ),
  );
}

Future<void> joinOrganizationDialog(
  BuildContext context,
  LiftController c,
) async {
  final code = await askText(
    context,
    title: 'Присоединиться к организации',
    label: 'Код приглашения',
    minimum: 20,
    maximum: 100,
    action: 'Присоединиться',
  );
  if (code == null) return;
  try {
    await c.join(code);
  } catch (e) {
    if (context.mounted) showError(context, e);
  }
}
