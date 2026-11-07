import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'api.dart';
import 'demo.dart';
import 'diagnostics.dart';
import 'storage.dart';

class LiftController extends ChangeNotifier {
  LiftController({required this.store, required this.log, this.transport});
  final SecretStore store;
  final Diagnostics log;
  final http.Client? transport;
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
  Future<void> _writes = Future.value();
  Map<String, dynamic> _resources = {}, _drafts = {};
  Timer? _draftTimer;

  bool get loggedIn => session != null || demo;
  bool get canWrite => online && !demo && session != null;
  Json get me =>
      snapshot['me'] is Map ? Map<String, dynamic>.from(snapshot['me']) : {};
  int get utcOffset => (me['utc_offset_minutes'] as num?)?.toInt() ?? 0;
  List<Json> list(String name) =>
      snapshot[name] is List ? records(snapshot[name]) : [];
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
    if (session != null) await refresh();
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
      await _write(_generation, 'server', serverText);
      await _saveSession();
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
    snapshot = {};
    _resources = {};
    _drafts = {};
    syncedAt = null;
    online = false;
    if (session == null || organization == null) return;
    final saved = await store.read('cache_$scope');
    if (saved != null) {
      try {
        final data = jsonDecode(saved) as Map;
        final at = DateTime.parse(data['at']);
        if (DateTime.now().toUtc().difference(at) < const Duration(days: 7)) {
          snapshot = Map<String, dynamic>.from(data['snapshot']);
          syncedAt = at;
        }
      } catch (_) {
        log.record('cache_read_failed');
      }
    }
    try {
      _resources = Map<String, dynamic>.from(
        jsonDecode(await store.read('resources_$scope') ?? '{}'),
      );
      _drafts = Map<String, dynamic>.from(
        jsonDecode(await store.read('drafts_$scope') ?? '{}'),
      );
    } catch (_) {
      log.record('draft_read_failed');
    }
  }

  Future<void> selectOrganization(int id) async {
    if (!organizations.any((o) => o['id'] == id)) {
      throw const ApiError('Нет доступа к организации.');
    }
    await flushDrafts();
    _generation++;
    organization = id;
    refreshing = false;
    error = '';
    if (demo) {
      snapshot = demoSnapshot(id);
      notifyListeners();
      return;
    }
    await _restoreSnapshot();
    await _saveSession();
    notifyListeners();
    await refresh();
  }

  Future<void> refresh() async {
    if (!loggedIn || demo || refreshing) return;
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
      snapshot = Map<String, dynamic>.fromIterables(names, values);
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
    if (!canWrite || expectedOrg != organization) {
      throw const ApiError('Для загрузки фотографии нужна связь с сервером.');
    }
    final captured = _generation, api = _api();
    try {
      await api.uploadPhoto(id, bytes, name);
      if (captured != _generation) {
        throw const ApiError('Сеанс или организация изменились.');
      }
    } finally {
      api.close();
    }
  }

  Future<Uint8List> download(
    String path,
    int expectedOrg, {
    bool pdf = false,
  }) async {
    if (!canWrite || expectedOrg != organization) {
      throw const ApiError('Для просмотра файла нужна связь с сервером.');
    }
    final captured = _generation, api = _api();
    try {
      final data = await api.download(path, pdf: pdf);
      if (captured != _generation) {
        throw const ApiError('Сеанс или организация изменились.');
      }
      return data;
    } finally {
      api.close();
    }
  }

  String draft(int ticket) => _drafts['$ticket'] as String? ?? '';
  void setDraft(int ticket, String value, int expectedOrg) {
    if (demo || session == null || expectedOrg != organization) return;
    if (value.isEmpty) {
      _drafts.remove('$ticket');
    } else {
      _drafts['$ticket'] = value;
    }
    _draftTimer?.cancel();
    _draftTimer = Timer(const Duration(milliseconds: 350), flushDrafts);
  }

  Future<void> flushDrafts() async {
    _draftTimer?.cancel();
    if (!demo && session != null && organization != null) {
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
    _generation++;
    _draftTimer?.cancel();
    session = null;
    organization = null;
    organizations = [];
    snapshot = {};
    _resources = {};
    _drafts = {};
    online = false;
    refreshing = false;
    syncedAt = null;
    demo = false;
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

  @override
  void dispose() {
    _draftTimer?.cancel();
    super.dispose();
  }
}
