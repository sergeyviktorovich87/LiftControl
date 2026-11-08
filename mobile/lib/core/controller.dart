import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'api.dart';
import 'demo.dart';
import 'diagnostics.dart';
import 'storage.dart';
import 'outbox.dart';
import 'device_bridge.dart';

class LiftController extends ChangeNotifier {
  LiftController({
    required this.store,
    required this.log,
    this.transport,
    Outbox? outbox,
  }) : outbox =
           outbox ??
           (store is DeviceStore ? DeviceOutbox() : StoredOutbox(store));
  final SecretStore store;
  final Diagnostics log;
  final http.Client? transport;
  final Outbox outbox;
  List<Json> _outboxRows = [];
  final Map<int, int> _resolvedTickets = {};
  Future<void>? _syncFuture;
  int _syncGeneration = -1;
  bool _outboxReady = false;
  bool get syncing => _syncFuture != null && _syncGeneration == _generation;
  List<Json> get pendingOperations =>
      List.unmodifiable(_outboxRows.where((r) => r['state'] != 'synced'));
  int get pendingCount => pendingOperations.length;
  int get failedCount =>
      pendingOperations.where((r) => r['state'] == 'failed').length;
  bool get canRecord =>
      !demo &&
      session != null &&
      organization != null &&
      me.isNotEmpty &&
      _outboxReady &&
      !_switchingOrganization;
  bool get canCreateTicket {
    if (!canRecord || me['can_create_ticket'] != true) return false;
    if (me['role'] != 'MECHANIC') return true;
    final shift = me['duty_shift'];
    if (shift is! Map) return false;
    final end = DateTime.tryParse('${shift['end']}');
    return end != null && DateTime.now().toUtc().isBefore(end.toUtc());
  }

  Json? session;
  Json snapshot = {};
  List<Json> organizations = [];
  int? organization;
  bool starting = true,
      refreshing = false,
      online = false,
      demo = false,
      dark = false;
  String serverText = '', error = '';
  DateTime? syncedAt;
  int _generation = 0;
  Future<void>? _refreshFuture;
  int _refreshGeneration = -1;
  bool _refreshAgain = false;
  int _organizationSwitch = 0;
  bool _switchingOrganization = false;
  Future<void> _writes = Future.value();
  Map<String, dynamic> _resources = {}, _drafts = {};
  Timer? _draftTimer;
  DateTime? _checkedUpdates;
  Json? updates;
  int? installedVersionCode;
  bool get hasUpdate =>
      updates?['android'] is Map &&
      installedVersionCode != null &&
      (updates!['android']['version_code'] as int) > installedVersionCode!;
  bool _pushSyncing = false;

  bool get loggedIn => session != null || demo;
  bool get canWrite => online && !demo && session != null;
  Json get me =>
      snapshot['me'] is Map ? Map<String, dynamic>.from(snapshot['me']) : {};
  int get utcOffset => (me['utc_offset_minutes'] as num?)?.toInt() ?? 0;
  List<Json> list(String name) {
    final base = snapshot[name] is List ? records(snapshot[name]) : <Json>[];
    if (name != 'tickets') return base;
    final tickets = {for (final row in base) row['id'] as int: row};
    for (final row in _outboxRows) {
      final command = Map<String, dynamic>.from(row['command'] as Map);
      final response = row['response'];
      if (row['state'] == 'synced' &&
          response is Map &&
          response['ticket'] is Map) {
        final ticket = Map<String, dynamic>.from(response['ticket']);
        tickets[ticket['id'] as int] = ticket;
        if (row['local_id'] is int) tickets.remove(row['local_id']);
        continue;
      }
      final id = (command['ticket'] ?? row['local_id']) as int;
      final existing =
          tickets[id] ??
          (row['local_ticket'] is Map
              ? Map<String, dynamic>.from(row['local_ticket'])
              : <String, dynamic>{});
      if (existing.isEmpty) continue;
      final ticket = {
        ...existing,
        'sync_state': row['state'],
        'sync_error': row['error'] ?? '',
        'sync_operation': row['id'],
      };
      final body = command['body'] as Map;
      if (row['state'] != 'failed') {
        switch (command['type']) {
          case 'accept':
            ticket['status'] = 'IN_PROGRESS';
            ticket['assigned_to'] = me['technician'];
            ticket['technician_name'] = me['name'];
          case 'complete':
            ticket['status'] = 'DONE';
            ticket['repair'] = body['work_description'];
          case 'stop':
            ticket['status'] = 'STOPPED';
            ticket['stop_reason'] = body['reason'];
            ticket['stopped_at'] = command['occurred_at'];
          case 'resume':
            ticket['status'] = 'IN_PROGRESS';
          case 'cancel':
            ticket['status'] = 'CANCELED';
            ticket['cancellation_reason'] = body['reason'];
          case 'assign':
            ticket['assigned_to'] = body['assigned_to'];
            ticket['technician_name'] =
                list('technicians').firstWhere(
                  (t) => t['id'] == body['assigned_to'],
                  orElse: () => {},
                )['full_name'] ??
                '';
        }
        if (id > 0) {
          final own =
              ticket['assigned_to'] == me['technician'] &&
              me['role'] == 'MECHANIC';
          final responsible =
              ticket['assigned_to'] ??
              list('elevators').firstWhere(
                (e) => e['id'] == ticket['elevator'],
                orElse: () => {},
              )['assigned_technician'];
          ticket['can_accept'] =
              me['role'] == 'MECHANIC' &&
              responsible == me['technician'] &&
              ticket['status'] == 'NEW';
          ticket['can_complete'] =
              own && ['IN_PROGRESS', 'STOPPED'].contains(ticket['status']);
          ticket['can_stop'] = own && ticket['status'] == 'IN_PROGRESS';
          ticket['can_resume'] = own && ticket['status'] == 'STOPPED';
          ticket['can_assign'] =
              ticket['can_assign'] == true && ticket['status'] == 'NEW';
          ticket['can_cancel'] =
              ticket['can_cancel'] == true &&
              ticket['status'] != 'CANCELED' &&
              (ticket['status'] != 'DONE' ||
                  ['ADMIN', 'DIRECTOR'].contains(me['role']));
        }
      }
      tickets[id] = ticket;
    }
    return tickets.values.toList();
  }

  int resolvedTicket(int id) => _resolvedTickets[id] ?? id;
  Json localTicket(int id) => list(
    'tickets',
  ).firstWhere((t) => t['id'] == resolvedTicket(id), orElse: () => {});
  String get scope => storageScope(
    Uri.parse(session!['server'] as String),
    session!['user']['id'] as int,
    organization!,
  );
  int get generation => _generation;
  DateTime get orgNow =>
      DateTime.now().toUtc().add(Duration(minutes: utcOffset));

  ApiClient _api({bool unscoped = false}) => ApiClient(
    server: Uri.parse(session!['server']),
    token: session!['token'],
    organization: unscoped ? null : organization,
    log: log,
    transport: transport,
  );

  Future<void> _write(int generation, String key, String value) {
    _writes = _writes
        .then((_) async {
          if (_generation == generation) await store.write(key, value);
        })
        .catchError((Object _) {
          log.record('secure_write_failed');
        });
    return _writes;
  }

  Future<void> initialize() async {
    await log.restore();
    log.record('startup');
    try {
      serverText =
          await store.read('server') ??
          const String.fromEnvironment('API_SERVER');
      dark = await store.read('theme') == 'dark';
      final saved = await store.read('session');
      if (saved != null) {
        final value = Map<String, dynamic>.from(jsonDecode(saved));
        parseServer(value['server']);
        if (DateTime.parse(
          value['expires_at'],
        ).isAfter(DateTime.now().toUtc())) {
          session = value;
          organizations = records(value['organizations']);
          organization = value['organization'];
          await _restoreSnapshot();
        } else {
          await _clearAccount();
          error = 'Срок входа истёк. Войдите заново.';
        }
      }
    } catch (_) {
      await _clearAccount();
      error = 'Не удалось прочитать сохранённый сеанс. Войдите заново.';
    }
    starting = false;
    notifyListeners();
    if (session != null) {
      await refresh();
      unawaited(syncDevice());
    }
  }

  Future<void> login(String server, String username, String password) async {
    final uri = parseServer(server);
    final api = ApiClient(server: uri, log: log, transport: transport);
    try {
      final data = Map<String, dynamic>.from(
        await api.call(
          'mobile/login/',
          method: 'POST',
          data: {
            'username': username.trim(),
            'password': password,
            'device_name': 'LiftControl Android',
          },
        ),
      );
      if (data['token'] is! String ||
          data['user'] is! Map ||
          data['organizations'] is! List) {
        throw const ApiError(
          'Ответ входа не поддерживается. Проверьте адрес сервера.',
        );
      }
      _generation++;
      _organizationSwitch++;
      _switchingOrganization = false;
      demo = false;
      organizations = records(data['organizations']);
      organization = organizations.isEmpty
          ? null
          : organizations.first['id'] as int;
      session = {
        ...data,
        'server': uri.toString(),
        'organization': organization,
      };
      serverText = uri.toString();
      online = true;
      error = '';
      snapshot = {};
      _resources = {};
      _drafts = {};
      _outboxRows = [];
      _resolvedTickets.clear();
      await _write(_generation, 'server', serverText);
      await _saveSession();
      await _loadOutbox();
      log.record('login_success');
      notifyListeners();
      await refresh();
    } on ApiError catch (e) {
      if (e.status == 404) {
        throw const ApiError(
          'На сервере ещё нет входа для Android. Установите обновление API для приложения.',
        );
      }
      rethrow;
    } finally {
      api.close();
    }
  }

  void preview() {
    _generation++;
    _organizationSwitch++;
    _switchingOrganization = false;
    demo = true;
    online = false;
    error = '';
    organization = 1;
    organizations = [
      {'id': 1, 'name': 'Мегаполис', 'role': 'MECHANIC'},
      {'id': 2, 'name': 'Эверест', 'role': 'DIRECTOR'},
    ];
    snapshot = demoSnapshot(1);
    syncedAt = null;
    notifyListeners();
  }

  Future<void> _saveSession() async {
    if (session == null) return;
    session!['organization'] = organization;
    session!['organizations'] = organizations;
    await _write(_generation, 'session', jsonEncode(session));
  }

  Future<void> _restoreSnapshot() async {
    final captured = _generation;
    snapshot = {};
    _resources = {};
    _drafts = {};
    _outboxRows = [];
    _outboxReady = false;
    _resolvedTickets.clear();
    syncedAt = null;
    online = false;
    if (session == null || organization == null) return;
    final key = scope;
    Json restoredSnapshot = {};
    Map<String, dynamic> restoredResources = {}, restoredDrafts = {};
    DateTime? restoredAt;
    try {
      final saved = await store.read('cache_$key');
      if (captured != _generation) return;
      if (saved != null) {
        final data = jsonDecode(saved) as Map;
        final at = DateTime.parse(data['at']);
        if (DateTime.now().toUtc().difference(at) < const Duration(days: 7)) {
          restoredSnapshot = Map<String, dynamic>.from(data['snapshot']);
          restoredAt = at;
        }
      }
    } catch (_) {
      log.record('cache_read_failed');
    }
    try {
      final values = await Future.wait([
        store.read('resources_$key'),
        store.read('drafts_$key'),
      ]);
      if (captured != _generation) return;
      restoredResources = Map<String, dynamic>.from(
        jsonDecode(values[0] ?? '{}'),
      );
      restoredDrafts = Map<String, dynamic>.from(jsonDecode(values[1] ?? '{}'));
    } catch (_) {
      log.record('draft_read_failed');
    }
    if (captured != _generation) return;
    snapshot = restoredSnapshot;
    syncedAt = restoredAt;
    _resources = restoredResources;
    _drafts = restoredDrafts;
    await _loadOutbox();
  }

  Future<void> _loadOutbox() async {
    if (session == null || organization == null) return;
    final captured = _generation, key = scope;
    try {
      final rows = await outbox.rows(key);
      if (captured != _generation) return;
      _outboxRows = rows;
      _outboxReady = true;
      for (final row in rows) {
        if (row['local_id'] is int && row['response'] is Map) {
          _resolvedTickets[row['local_id'] as int] =
              row['response']['ticket']['id'] as int;
        }
      }
      await outbox.configure(key, {
        'server': session!['server'],
        'token': session!['token'],
        'organization': organization,
        'expires_at': session!['expires_at'],
      });
    } catch (_) {
      if (captured != _generation) return;
      _outboxReady = false;
      error =
          'Не удалось прочитать очередь телефона. Сохранённые записи не удалены.';
      log.record('outbox_read_failed');
    }
  }

  Future<void> syncPending() {
    if (session == null || organization == null || demo || !_outboxReady) {
      return Future.value();
    }
    if (_syncFuture != null && _syncGeneration == _generation) {
      return _syncFuture!;
    }
    final captured = _generation, key = scope;
    final done = Completer<void>();
    _syncFuture = done.future;
    _syncGeneration = captured;
    unawaited(() async {
      final api = _api();
      try {
        if (outbox.nativeSync) {
          await outbox.sync(key);
        } else {
          final blocked = <int>{};
          for (final row in await outbox.rows(key)) {
            if (captured != _generation) break;
            final command = Map<String, dynamic>.from(row['command']);
            final target = (command['ticket'] ?? row['local_id']) as int;
            if (row['state'] == 'failed') {
              blocked.add(target);
              continue;
            }
            if (row['state'] != 'queued' || blocked.contains(target)) continue;
            try {
              final response = Map<String, dynamic>.from(
                await api.call('mobile/sync/', method: 'POST', data: command),
              );
              if (response['operation_id'] != row['id'] ||
                  response['ticket'] is! Map ||
                  response['ticket']['id'] is! int) {
                throw const ApiError(
                  'Сервер не подтвердил сохранение операции.',
                  network: true,
                );
              }
              await outbox.finish(
                key,
                row['id'] as String,
                'synced',
                response: response,
              );
              log.record('outbox_sent');
            } on ApiError catch (e) {
              if (e.network ||
                  e.status == null ||
                  e.status! >= 500 ||
                  [408, 425, 429].contains(e.status)) {
                if (captured == _generation) online = false;
                log.record('outbox_retry', status: e.status);
                break;
              }
              await outbox.finish(
                key,
                row['id'] as String,
                'failed',
                error: e.message,
              );
              blocked.add(target);
              log.record('outbox_rejected', status: e.status);
              if (e.status == 401) break;
            }
          }
        }
        if (captured == _generation) await _loadOutbox();
        done.complete();
      } catch (e, st) {
        log.record('outbox_sync_failed');
        done.completeError(e, st);
      } finally {
        api.close();
        if (identical(_syncFuture, done.future)) _syncFuture = null;
        if (captured == _generation) notifyListeners();
      }
    }());
    return done.future;
  }

  Future<void> retryOperation(String id) async {
    if (session == null || organization == null) return;
    await outbox.retry(scope, id);
    await _loadOutbox();
    notifyListeners();
    unawaited(refresh());
  }

  String _operationId() {
    final random = Random.secure();
    final bytes = List<int>.generate(16, (_) => random.nextInt(256));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    final h = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
  }

  Future<Json> _recordTicket(String kind, Json body, {int? ticketId}) async {
    if (!canRecord) {
      throw const ApiError('Сначала войдите и загрузите данные организации.');
    }
    if (kind == 'create' && !canCreateTicket) {
      throw const ApiError(
        'Создавать заявки может диспетчер или дежурный в течение смены.',
      );
    }
    final captured = _generation, key = scope, id = _operationId();
    final at = DateTime.now().toUtc().toIso8601String();
    Json ticket;
    int? localId;
    if (kind == 'create') {
      final lift = list(
        'elevators',
      ).firstWhere((e) => e['id'] == body['elevator'], orElse: () => {});
      if (lift.isEmpty || lift['active'] == false) {
        throw const ApiError(
          'Выберите действующий лифт из сохранённого списка.',
        );
      }
      localId =
          -DateTime.now().microsecondsSinceEpoch -
          Random.secure().nextInt(1000);
      final assignee = body['assigned_to'] ?? lift['assigned_technician'];
      final person = list(
        'technicians',
      ).firstWhere((e) => e['id'] == assignee, orElse: () => {});
      ticket = {
        'id': localId,
        ...body,
        'address': lift['address'],
        'elevator_label': lift['factory_number'] ?? lift['inventory_number'],
        'assigned_to': assignee,
        'technician_name': person['full_name'] ?? '',
        'created_at': at,
        'status': 'NEW',
        'photos': <Json>[],
        'can_accept': false,
        'can_complete': false,
        'can_stop': false,
        'can_resume': false,
        'can_cancel': false,
      };
    } else {
      ticketId = resolvedTicket(ticketId!);
      ticket = localTicket(ticketId);
      if (ticketId <= 0 || ticket.isEmpty) {
        throw const ApiError(
          'Дождитесь отправки новой заявки. Остальные записи уже сохранены.',
        );
      }
      if (pendingOperations.any(
        (r) => r['command']['ticket'] == ticketId && r['state'] == 'failed',
      )) {
        throw const ApiError(
          'Сначала проверьте ошибку отправки этой заявки в очереди.',
        );
      }
      final permission = {
        'accept': 'can_accept',
        'complete': 'can_complete',
        'stop': 'can_stop',
        'resume': 'can_resume',
        'photo': 'can_complete',
        'cancel': 'can_cancel',
        'assign': 'can_assign',
      }[kind];
      if (kind == 'comment' &&
          (!['NEW', 'IN_PROGRESS', 'STOPPED'].contains(ticket['status']) ||
              !(ticket['can_complete'] == true ||
                  me['on_duty'] == true ||
                  me['can_manage'] == true))) {
        throw const ApiError(
          'Комментировать может исполнитель, дежурный или диспетчер открытой заявки.',
        );
      }
      if (permission != null && ticket[permission] != true) {
        throw const ApiError('Это действие недоступно для выбранной заявки.');
      }
    }
    final command = <String, dynamic>{
      'id': id,
      'type': kind,
      'body': body,
      'occurred_at': at,
      'ticket': ?ticketId,
      if (kind == 'create' && me['offline_grant'] is String)
        'grant': me['offline_grant'],
    };
    await outbox.enqueue(key, [
      {
        'id': id,
        'command': command,
        'local_ticket': ticket,
        'local_id': ?localId,
      },
    ]);
    log.record('outbox_saved');
    if (captured != _generation) {
      throw const ApiError(
        'Организация изменилась. Запись сохранена в очереди прежней организации.',
      );
    }
    await _loadOutbox();
    notifyListeners();
    if (online) {
      try {
        await syncPending();
      } catch (_) {
        /* The committed local row remains visible. */
      }
    }
    final row = _outboxRows.firstWhere((r) => r['id'] == id, orElse: () => {});
    if (row['response'] is Map) {
      return Map<String, dynamic>.from(row['response']['ticket']);
    }
    return localTicket(ticketId ?? localId!);
  }

  Future<void> selectOrganization(int id) async {
    if (!organizations.any((o) => o['id'] == id)) {
      throw const ApiError('Нет доступа к организации.');
    }
    final selection = ++_organizationSwitch;
    if (!_switchingOrganization) await flushDrafts();
    if (selection != _organizationSwitch) return;
    final captured = ++_generation;
    _switchingOrganization = true;
    log.record('organization_switch_started');
    organization = id;
    updates = null;
    _checkedUpdates = null;
    refreshing = true;
    error = '';
    if (demo) {
      snapshot = demoSnapshot(id);
      refreshing = false;
      _switchingOrganization = false;
      notifyListeners();
      return;
    }
    final restoration = _restoreSnapshot();
    notifyListeners();
    try {
      await restoration;
      if (captured != _generation) return;
      await _saveSession();
      if (captured != _generation) return;
      // No asynchronous gap between releasing the guard and starting refresh.
      refreshing = false;
      await refresh();
    } finally {
      if (captured == _generation) {
        _switchingOrganization = false;
        refreshing = false;
        log.record('organization_switch_finished');
        notifyListeners();
      } else {
        log.record('organization_switch_superseded');
      }
    }
  }

  Future<void> refresh() {
    if (!loggedIn || demo) {
      return Future<void>.value();
    }
    final captured = _generation;
    if (_refreshFuture != null && _refreshGeneration == captured) {
      // A write may finish while an older read is still returning. Do not
      // discard its refresh or resolve the caller before the fresh pass.
      _refreshAgain = true;
      return _refreshFuture!;
    }
    if (_switchingOrganization && refreshing) {
      return Future<void>.value();
    }
    final done = Completer<void>();
    _refreshGeneration = captured;
    _refreshFuture = done.future;
    unawaited(() async {
      try {
        do {
          _refreshAgain = false;
          await _refreshOnce();
        } while (captured == _generation && loggedIn && !demo && _refreshAgain);
        done.complete();
      } catch (error, stack) {
        done.completeError(error, stack);
      } finally {
        if (identical(_refreshFuture, done.future)) {
          _refreshFuture = null;
        }
      }
    }());
    return done.future;
  }

  Future<void> _refreshOnce() async {
    final captured = _generation;
    final api = _api();
    refreshing = true;
    notifyListeners();
    try {
      if (organization == null) {
        final data = await api.call('organizations/');
        if (captured != _generation) return;
        organizations = records(data['organizations']);
        online = true;
        error = '';
        await _saveSession();
        return;
      }
      final currentScope = scope;
      await _loadOutbox();
      if (captured != _generation) return;
      await syncPending();
      if (captured != _generation) return;
      const names = [
        'me',
        'tickets',
        'elevators',
        'buildings',
        'duty',
        'duty-swaps',
        'technicians',
        'maintenance',
        'parts',
        'chat',
      ];
      final from = orgNow
          .subtract(const Duration(days: 1))
          .toIso8601String()
          .substring(0, 10);
      final to = orgNow
          .add(const Duration(days: 45))
          .toIso8601String()
          .substring(0, 10);
      final values = await Future.wait(
        names.map(
          (name) => api.call(
            '$name/',
            query: name == 'duty' ? {'from': from, 'to': to} : null,
          ),
        ),
      );
      if (captured != _generation) return;
      final next = Map<String, dynamic>.fromIterables(names, values);
      next['tasks'] = next['me'] is Map && next['me']['field_ops_api'] == 1
          ? await api.call('tasks/')
          : <Json>[];
      if (captured != _generation) return;
      snapshot = next;
      organizations = records(me['organizations']);
      online = true;
      error = '';
      syncedAt = DateTime.now().toUtc();
      final cache = jsonEncode({
        'at': syncedAt!.toIso8601String(),
        'snapshot': snapshot,
      });
      if (utf8.encode(cache).length < 2 * 1024 * 1024) {
        await _write(captured, 'cache_$currentScope', cache);
      }
      // Only remove confirmed receipts after reading the committed server list.
      final ids = records(snapshot['tickets']).map((t) => t['id']).toSet();
      for (final row in List<Json>.from(_outboxRows)) {
        if (row['state'] == 'synced' &&
            ids.contains(row['response']?['ticket']?['id'])) {
          await outbox.acknowledge(currentScope, row['id'] as String);
        }
      }
      if (captured != _generation) return;
      await _loadOutbox();
      await _saveSession();
    } on ApiError catch (e) {
      if (captured != _generation) return;
      online = false;
      error = e.message;
      if (e.status == 401) {
        await _clearAccount();
        error = 'Сеанс завершён. Войдите заново.';
      }
      if (e.status == 403) {
        await _writes;
        if (organization != null) {
          await store.delete('cache_$scope');
          await store.delete('resources_$scope');
          await store.delete('drafts_$scope');
        }
        snapshot = {};
        _resources = {};
        _drafts = {};
        _outboxRows = [];
        _outboxReady = false;
        final unscoped = _api(unscoped: true);
        try {
          final data = await unscoped.call('organizations/');
          if (captured == _generation) {
            organizations = records(data['organizations']);
            organization = null;
            online = true;
            await _saveSession();
          }
        } catch (_) {
          /* Existing business data has already been removed. */
        } finally {
          unscoped.close();
        }
      }
    } catch (_) {
      if (captured == _generation) {
        online = false;
        error = 'Не удалось загрузить данные. Обновите экран.';
        log.record('snapshot_invalid');
      }
    } finally {
      api.close();
      if (captured == _generation) {
        refreshing = false;
        notifyListeners();
      }
    }
  }

  Future<dynamic> request(
    String path, {
    String method = 'GET',
    Json? data,
    int? expectedOrganization,
  }) async {
    if (demo) {
      throw const ApiError(
        'Это демонстрация. Для работы подключитесь к серверу.',
      );
    }
    if (session == null ||
        (expectedOrganization != null &&
            expectedOrganization != organization)) {
      throw const ApiError('Организация изменилась. Откройте запись заново.');
    }
    if (method == 'POST' && path == 'tickets/') {
      return _recordTicket('create', data ?? {});
    }
    final ticketAction = RegExp(
      r'^tickets/(\d+)/(accept|complete|stop|resume|comment|cancel|assign)/$',
    ).firstMatch(path);
    if (method == 'POST' && ticketAction != null) {
      return _recordTicket(
        ticketAction.group(2)!,
        data ?? {},
        ticketId: int.parse(ticketAction.group(1)!),
      );
    }
    if (method != 'GET' && !online) {
      throw const ApiError('Сначала восстановите связь и обновите данные.');
    }
    final captured = _generation;
    final api = _api();
    try {
      final value = await api.call(path, method: method, data: data);
      if (captured != _generation) {
        throw const ApiError('Сеанс или организация изменились.');
      }
      return value;
    } on ApiError catch (e) {
      if (captured == _generation) {
        if (e.network) {
          online = false;
          error = e.message;
          notifyListeners();
        }
        if (e.status == 401) {
          await _clearAccount();
          error = e.message;
          notifyListeners();
        }
      }
      rethrow;
    } finally {
      api.close();
    }
  }

  Future<dynamic> resource(
    String path, {
    required int expectedOrganization,
  }) async {
    if (demo) {
      if (path.endsWith('history/')) {
        return {'events': <Json>[], 'comments': <Json>[]};
      }
      if (path.endsWith('documents/')) return <Json>[];
      return {};
    }
    try {
      final captured = _generation, key = scope;
      final result = await request(
        path,
        expectedOrganization: expectedOrganization,
      );
      if (captured == _generation) {
        _resources[path] = result;
        // Keep the text cache bounded. Photos and PDFs are not stored in this cache.
        var encoded = jsonEncode(_resources);
        if (utf8.encode(encoded).length > 2 * 1024 * 1024) {
          _resources = {path: result};
          encoded = jsonEncode(_resources);
        }
        await _write(captured, 'resources_$key', encoded);
      }
      return result;
    } on ApiError catch (e) {
      if (e.network &&
          expectedOrganization == organization &&
          _resources.containsKey(path)) {
        return _resources[path];
      }
      if (e.status == 403 || e.status == 404) {
        _resources.remove(path);
        if (session != null && organization == expectedOrganization) {
          await _write(_generation, 'resources_$scope', jsonEncode(_resources));
        }
      }
      rethrow;
    }
  }

  Future<void> uploadPhoto(
    int id,
    Uint8List bytes,
    String name,
    int expectedOrg,
  ) async {
    if (!canRecord || expectedOrg != organization) {
      throw const ApiError('Организация изменилась. Откройте заявку заново.');
    }
    if (bytes.isEmpty || bytes.length > 10 * 1024 * 1024) {
      throw const ApiError('Выберите фотографию до 10 МБ.');
    }
    await _recordTicket('photo', {'file': base64Encode(bytes)}, ticketId: id);
  }

  Future<Uint8List> download(
    String path,
    int expectedOrg, {
    bool pdf = false,
    bool video = false,
  }) async {
    if (!canWrite || expectedOrg != organization) {
      throw const ApiError('Для просмотра файла нужна связь с сервером.');
    }
    final captured = _generation, api = _api();
    try {
      final data = await api.download(path, pdf: pdf, video: video);
      if (captured != _generation) {
        throw const ApiError('Сеанс или организация изменились.');
      }
      return data;
    } finally {
      api.close();
    }
  }

  String draft(int ticket) => _drafts['$ticket'] as String? ?? '';

  Future<dynamic> uploadMedia(
    String route,
    List<({Uint8List bytes, String name})> files,
    int expectedOrg, {
    Map<String, String> fields = const {},
    String field = 'files',
  }) async {
    if (!canWrite || organization != expectedOrg) {
      throw const ApiError(
        'Для отправки вложения нужна связь с выбранной организацией.',
      );
    }
    final captured = _generation, api = _api();
    try {
      final result = await api.uploadMedia(
        route,
        files,
        fields: fields,
        field: field,
      );
      if (captured != _generation) {
        throw const ApiError(
          'Организация или сеанс изменились. Обновите список.',
        );
      }
      return result;
    } finally {
      api.close();
    }
  }

  String taskDraft(int task) => _drafts['task:$task'] as String? ?? '';
  void setTaskDraft(int task, String value, int expectedOrg) =>
      _setDraft('task:$task', value, expectedOrg);
  void setDraft(int ticket, String value, int expectedOrg) =>
      _setDraft('$ticket', value, expectedOrg);
  void _setDraft(String key, String value, int expectedOrg) {
    if (demo || session == null || expectedOrg != organization) return;
    if (value.isEmpty) {
      _drafts.remove(key);
    } else {
      _drafts[key] = value;
    }
    _draftTimer?.cancel();
    _draftTimer = Timer(const Duration(milliseconds: 350), flushDrafts);
  }

  Future<void> flushDrafts() async {
    _draftTimer?.cancel();
    if (!demo &&
        !_switchingOrganization &&
        session != null &&
        organization != null) {
      await _write(_generation, 'drafts_$scope', jsonEncode(_drafts));
    }
  }

  Future<void> join(String code) async {
    await request(
      'organizations/join/',
      method: 'POST',
      data: {'code': code.trim()},
    );
    final data = await request('organizations/');
    organizations = records(data['organizations']);
    await selectOrganization(organizations.last['id'] as int);
  }

  Future<void> setDark(bool value) async {
    dark = value;
    notifyListeners();
    await _write(_generation, 'theme', value ? 'dark' : 'light');
  }

  Future<void> _clearAccount() async {
    await outbox.clearAuth();
    try {
      await DeviceBridge.clearPrivateFiles();
    } catch (_) {
      /* Android only. */
    }
    try {
      await DeviceBridge.disablePush();
    } catch (_) {
      /* Native bridge is Android only. */
    }
    _generation++;
    _organizationSwitch++;
    _switchingOrganization = false;
    _draftTimer?.cancel();
    session = null;
    organization = null;
    organizations = [];
    snapshot = {};
    _resources = {};
    _drafts = {};
    _outboxRows = [];
    _outboxReady = false;
    _resolvedTickets.clear();
    online = false;
    refreshing = false;
    syncedAt = null;
    demo = false;
    updates = null;
    _checkedUpdates = null;
    await _writes;
    await log.flush();
    await store.clear();
    await store.write('server', serverText);
    await store.write('theme', dark ? 'dark' : 'light');
  }

  Future<bool> logout() async {
    var revoked = demo;
    if (!demo && session != null) {
      final api = _api(unscoped: true);
      try {
        await api.call('mobile/logout/', method: 'POST', data: {});
        revoked = true;
      } on ApiError catch (e) {
        revoked = e.status == 401;
      } finally {
        api.close();
      }
    }
    await _clearAccount();
    notifyListeners();
    return revoked;
  }

  Future<Json?> checkUpdates({bool force = false}) async {
    if (!canWrite || organization == null) return null;
    if (!force &&
        _checkedUpdates != null &&
        DateTime.now().difference(_checkedUpdates!) <
            const Duration(hours: 12)) {
      return updates;
    }
    final result = await request('updates/');
    updates = Map<String, dynamic>.from(result);
    _checkedUpdates = DateTime.now();
    notifyListeners();
    return updates;
  }

  Future<void> enablePush({bool prompt = true}) async {
    if (_pushSyncing || !canWrite || organization == null) return;
    _pushSyncing = true;
    final captured = _generation;
    try {
      final response = Map<String, dynamic>.from(await request('mobile/push/'));
      if (response['enabled'] != true || response['config'] is! Map) {
        throw const ApiError(
          'На сервере ещё не настроена доставка FCM. Администратору нужно подключить Firebase.',
        );
      }
      final token = await DeviceBridge.registerPush({
        ...Map<String, dynamic>.from(response['config']),
        'prompt': prompt,
      });
      if (captured != _generation || token == null) return;
      await request('mobile/push/', method: 'POST', data: {'token': token});
      if (captured != _generation) return;
      await DeviceBridge.activatePush();
      await _write(captured, 'push_enabled', 'true');
      log.record('push_registered');
    } finally {
      _pushSyncing = false;
    }
  }

  Future<void> disablePush() async {
    await DeviceBridge.disablePush();
    await _write(_generation, 'push_enabled', 'false');
    if (canWrite) await request('mobile/push/', method: 'DELETE');
    log.record('push_disabled');
  }

  Future<void> syncDevice() async {
    if (!canWrite || organization == null) return;
    try {
      installedVersionCode =
          ((await DeviceBridge.status())['version_code'] as num?)?.toInt();
    } catch (_) {
      /* Platform bridge unavailable. */
    }
    try {
      if (await store.read('push_enabled') == 'true') {
        await enablePush(prompt: false);
      }
    } catch (_) {
      log.record('push_sync_failed');
    }
    try {
      await checkUpdates();
    } catch (_) {
      log.record('update_check_failed');
    }
  }

  @override
  void dispose() {
    _draftTimer?.cancel();
    super.dispose();
  }
}
