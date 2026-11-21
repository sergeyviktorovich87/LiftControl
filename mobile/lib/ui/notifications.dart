import 'dart:async';
import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';
import 'tickets.dart';
import 'tasks.dart';
import 'chat.dart';
import 'commissioning.dart';
import 'extras.dart';
import 'elevators.dart';
import 'device_settings.dart';

/// Server-persisted history, independent of OS push delivery and ticket acceptance.
class NotificationsPage extends StatefulWidget {
  const NotificationsPage({super.key, required this.controller});
  final LiftController controller;
  @override
  State<NotificationsPage> createState() => _NotificationsPageState();
}

class _NotificationsPageState extends State<NotificationsPage> {
  List<Json> _entries = [];
  int _unread = 0;
  final _unreadByCategory = <String, int>{};
  bool _entrapment = false;
  bool _unreadOnly = false, _loading = false, _opening = false;
  Timer? _poll;
  int _loadRequest = 0;
  String _error = '';
  LiftController get c => widget.controller;
  late final int organization;

  @override
  void initState() {
    super.initState();
    organization = c.organization!;
    _entrapment = c.unreadNotifications('entrapment') > 0;
    unawaited(_load());
    _poll = Timer.periodic(const Duration(seconds: 15), (_) {
      if (!mounted || _opening || ModalRoute.of(context)?.isCurrent != true ||
          WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) {
        return;
      }
      unawaited(_load(quiet: true));
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _load({bool quiet = false}) async {
    if (!mounted || c.organization != organization ||
        (quiet && (_loading || _opening))) {
      return;
    }
    final request = ++_loadRequest;
    if (!quiet) {
      setState(() {
        _loading = true;
        _error = '';
      });
    }
    try {
      final category = _entrapment ? 'entrapment' : 'ordinary';
      final filter = c.me['lift_documents_api'] == 1 ? '&category=$category' : '';
      final data = await c.request(
        'notifications/?unread=${_unreadOnly ? 1 : 0}&limit=100$filter',
        expectedOrganization: organization,
      );
      if (!mounted || request != _loadRequest || c.organization != organization) {
        return;
      }
      setState(() {
        _entries = records(data['results']);
        _error = '';
        _unread = data['unread'] is int ? data['unread'] as int : 0;
        final counts = data['unread_by_category'];
        for (final category in ['ordinary', 'entrapment']) {
          final count = counts is Map ? counts[category] : null;
          _unreadByCategory[category] = count is int ? count : 0;
        }
      });
    } catch (e) {
      c.log.record('notification_inbox_load_failed');
      if (!quiet && mounted && request == _loadRequest) {
        setState(() => _error = '$e');
      }
    } finally {
      if (!quiet && mounted && request == _loadRequest) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _open(Json item) async {
    if (c.organization != organization || !mounted || _opening) return;
    setState(() => _opening = true);
    try {
      if (item['read_at'] == null && c.canWrite) {
        await c.request(
          'notifications/${item['id']}/read/',
          method: 'POST',
          data: {},
          expectedOrganization: organization,
        );
        unawaited(c.refreshNotificationCounts());
      }
      if (!mounted || c.organization != organization) return;
      final target = item['target_type'], id = item['target_id'];
      if (id is int) {
        if (target == 'ticket') {
          openTicket(context, c, id);
        } else if (target == 'inspection') {
          openElevator(context, c, {'id': id}, inspection: true);
        } else if (target == 'task') {
          openTask(context, c, id);
        } else if (target == 'chat' || target == 'commissioning_chat') {
          Navigator.push(
            context,
            MaterialPageRoute<void>(
              builder: (_) => ChatPage(controller: c, messageId: id,
                commissioning: target == 'commissioning_chat'),
            ),
          );
        } else if (target == 'part') {
          final row = await c.resource('parts/$id/', expectedOrganization: organization);
          if (!mounted) return;
          Navigator.push(context, MaterialPageRoute<void>(
            builder: (_) => PartForm(controller: c, item: Map<String, dynamic>.from(row as Map)),
          ));
        } else if (target == 'commissioning') {
          Navigator.push(
            context,
            MaterialPageRoute<void>(
              builder: (_) => CommissioningPage(
                key: ValueKey(organization),
                controller: c,
                initialProject: id,
              ),
            ),
          );
        }
      }
      unawaited(_load());
    } catch (e) {
      c.log.record('notification_inbox_mark_read_failed');
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: c,
    organization: organization,
    builder: (context) => Scaffold(
      appBar: AppBar(
        title: const Text('Центр уведомлений'),
        actions: [
          IconButton(
            tooltip: 'Звуки уведомлений',
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute<void>(
                builder: (context) => Scaffold(
                  appBar: AppBar(title: const Text('Звуки уведомлений')),
                  body: ListView(
                    padding: const EdgeInsets.all(16),
                    children: [NotificationSettings(controller: c)],
                  ),
                ),
              ),
            ),
          ),
          IconButton(
            tooltip: 'Обновить',
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          physics: const AlwaysScrollableScrollPhysics(),
          children: [
            if (c.me['lift_documents_api'] == 1)
              Wrap(spacing: 8, children: [
                for (final emergency in [false, true])
                  ChoiceChip(
                    avatar: emergency ? const Icon(Icons.warning_amber_rounded) : null,
                    label: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(emergency ? 'Застревания' : 'Обычные'),
                        if (_unreadByCategory[emergency ? 'entrapment' : 'ordinary']
                            case final int count when count > 0)
                          Padding(
                            padding: const EdgeInsets.only(left: 10),
                            child: unreadBadge(count),
                          ),
                      ],
                    ),
                    selected: _entrapment == emergency,
                    onSelected: _loading || _opening ? null : (_) {
                      if (_entrapment == emergency) return;
                      setState(() { _entrapment = emergency; _entries = []; });
                      unawaited(_load());
                    },
                  ),
              ]),
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Непрочитанных: $_unread',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                FilterChip(
                  label: const Text('Только новые'),
                  selected: _unreadOnly,
                  onSelected: _loading || _opening ? null : (value) {
                    setState(() => _unreadOnly = value);
                    unawaited(_load());
                  },
                ),
              ],
            ),
            if (_error.isNotEmpty)
              Text(
                _error,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            if (_loading) const LinearProgressIndicator(),
            if (_entries.isEmpty && !_loading)
              const EmptyState(
                'Уведомлений нет',
                'История появится здесь после новых событий.',
              ),
            for (final item in _entries)
              Card(
                child: ListTile(
                  leading: Icon(
                    item['category'] == 'entrapment' ? Icons.warning_amber_rounded :
                    item['read_at'] == null
                        ? Icons.notifications_active_outlined
                        : Icons.notifications_none_outlined,
                    color: item['category'] == 'entrapment' ? Theme.of(context).colorScheme.error : null,
                  ),
                  title: Text(text(item, 'title')),
                  subtitle: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (text(item, 'preview', '').isNotEmpty)
                        Text(text(item, 'preview')),
                      Text(dateLabel(
                      item['created_at'],
                      (c.me['utc_offset_minutes'] is int
                          ? c.me['utc_offset_minutes'] as int
                          : 0),
                      )),
                    ],
                  ),
                  trailing: item['read_at'] == null
                      ? const Icon(Icons.circle, size: 9, color: green)
                      : const Icon(Icons.chevron_right),
                  onTap: _opening ? null : () => _open(item),
                ),
              ),
          ],
        ),
      ),
    ),
  );
}
