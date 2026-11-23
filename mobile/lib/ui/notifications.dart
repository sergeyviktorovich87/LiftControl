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
  const NotificationsPage({
    super.key,
    required this.controller,
    this.commissioning = false,
  });
  final LiftController controller;
  final bool commissioning;
  @override
  State<NotificationsPage> createState() => _NotificationsPageState();
}

class _NotificationsPageState extends State<NotificationsPage> {
  List<Json> _entries = [];
  int? _nextBefore;
  bool _historyExtended = false;
  final _unreadByCategory = <String, int>{};
  late String _category;
  bool get _groupCommissioning =>
      c.me['commissioning_notification_tabs'] == 1 &&
      c.me['can_commissioning'] == true;
  bool _loading = false, _opening = false;
  Timer? _poll;
  int _loadRequest = 0;
  String _error = '';
  LiftController get c => widget.controller;
  late final int organization;

  @override
  void initState() {
    super.initState();
    organization = c.organization!;
    _category =
        (widget.commissioning || c.me['commissioning_only'] == true) &&
            _groupCommissioning
        ? 'commissioning'
        : c.unreadNotifications('entrapment') > 0
        ? 'entrapment'
        : 'ordinary';
    unawaited(_load());
    _poll = Timer.periodic(const Duration(seconds: 15), (_) {
      if (!mounted ||
          _opening ||
          ModalRoute.of(context)?.isCurrent != true ||
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

  Future<void> _load({bool quiet = false, bool older = false}) async {
    final before = older ? _nextBefore : null;
    if (!mounted ||
        c.organization != organization ||
        (older && before == null) ||
        (quiet && (_loading || _opening || _historyExtended))) {
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
      final category = _category == 'commissioning' && !_groupCommissioning
          ? 'ordinary'
          : _category;
      final filter = (c.me['lift_documents_api'] == 1 || _groupCommissioning)
          ? '&category=$category'
          : '';
      final grouping = _groupCommissioning ? '&group_commissioning=1' : '';
      final cursor = before == null ? '' : '&before=$before';
      final data = await c.request(
        'notifications/?limit=30$filter$grouping$cursor',
        expectedOrganization: organization,
      );
      if (!mounted ||
          request != _loadRequest ||
          c.organization != organization) {
        return;
      }
      setState(() {
        final rows = records(data['results']);
        _entries = older ? [..._entries, ...rows] : rows;
        _nextBefore = data['next_before'] is int
            ? data['next_before'] as int
            : null;
        _historyExtended = older;
        _error = '';
        final counts = data['unread_by_category'];
        for (final category in ['ordinary', 'entrapment', 'commissioning']) {
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
    if (c.organization != organization || !mounted || _opening || _loading) {
      return;
    }
    ++_loadRequest;
    setState(() => _opening = true);
    try {
      if (item['read_at'] == null && c.canWrite) {
        final result = await c.request(
          'notifications/${item['id']}/read/',
          method: 'POST',
          data: {},
          expectedOrganization: organization,
        );
        if (!mounted || c.organization != organization) return;
        setState(() {
          item['read_at'] = result['read_at'];
          final category = text(item, 'category', 'ordinary');
          final count = _unreadByCategory[category] ?? 0;
          if (count > 0) _unreadByCategory[category] = count - 1;
        });
        unawaited(c.refreshNotificationCounts());
      }
      if (!mounted || c.organization != organization) return;
      final target = item['target_type'], id = item['target_id'];
      if (id is int) {
        if (target == 'ticket' || target == 'ticket_delivery') {
          openTicket(context, c, id);
        } else if (target == 'inspection') {
          openElevator(context, c, {'id': id}, inspection: true);
        } else if (target == 'task') {
          openTask(context, c, id);
        } else if (target == 'chat' || target == 'commissioning_chat') {
          Navigator.push(
            context,
            MaterialPageRoute<void>(
              builder: (_) => ChatPage(
                controller: c,
                messageId: id,
                commissioning: target == 'commissioning_chat',
              ),
            ),
          );
        } else if (target == 'part') {
          final row = await c.resource(
            'parts/$id/',
            expectedOrganization: organization,
          );
          if (!mounted) return;
          Navigator.push(
            context,
            MaterialPageRoute<void>(
              builder: (_) => PartForm(
                controller: c,
                item: Map<String, dynamic>.from(row as Map),
              ),
            ),
          );
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
              Wrap(
                spacing: 8,
                children: [
                  for (final (kind, label) in [
                    ('entrapment', 'Важные'),
                    ('ordinary', 'Обычные'),
                    if (_groupCommissioning) ('commissioning', 'Пусконаладка'),
                  ])
                    ChoiceChip(
                      avatar: kind == 'entrapment'
                          ? const Icon(Icons.warning_amber_rounded)
                          : null,
                      label: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(label),
                          if (_unreadByCategory[kind] case final int count
                              when count > 0)
                            Padding(
                              padding: const EdgeInsets.only(left: 10),
                              child: unreadBadge(count),
                            ),
                        ],
                      ),
                      selected: _category == kind,
                      onSelected: _loading || _opening
                          ? null
                          : (_) {
                              if (_category == kind) return;
                              setState(() {
                                _category = kind;
                                _entries = [];
                                _nextBefore = null;
                                _historyExtended = false;
                              });
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
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Text('Уведомлений нет'),
              ),
            for (final item in _entries)
              Card(
                child: ListTile(
                  title: Text(text(item, 'title')),
                  subtitle: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (text(item, 'body', '').isNotEmpty)
                        Text(text(item, 'body')),
                      Text(dateLabel(item['created_at'], c.utcOffset)),
                    ],
                  ),
                  trailing: item['read_at'] == null
                      ? const Icon(
                          Icons.circle,
                          size: 9,
                          color: green,
                          semanticLabel: 'Непрочитанное',
                        )
                      : null,
                  onTap: _opening || _loading ? null : () => _open(item),
                ),
              ),
            if (_nextBefore != null)
              TextButton(
                onPressed: _loading || _opening
                    ? null
                    : () => _load(older: true),
                child: const Text('Загрузить ещё'),
              ),
          ],
        ),
      ),
    ),
  );
}
