import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:liftcontrol_mobile/core/api.dart';
import 'package:liftcontrol_mobile/core/controller.dart';
import 'package:liftcontrol_mobile/core/demo.dart';
import 'package:liftcontrol_mobile/core/diagnostics.dart';
import 'package:liftcontrol_mobile/core/storage.dart';

const token = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const organizations = [
  {'id': 1, 'name': 'Мегаполис', 'role': 'MECHANIC'},
  {'id': 2, 'name': 'Эверест', 'role': 'DISPATCHER'},
];

class Server {
  bool offline = false, forbidden = false;
  Completer<void>? delayed;
  final requests = <http.Request>[];
  late final client = MockClient((r) async {
    requests.add(r);
    if (offline) throw http.ClientException('Offline');
    final route = r.url.path.replaceFirst('/api/', '');
    final org = int.tryParse(r.headers['X-Organization-ID'] ?? '1') ?? 1;
    if (route == 'mobile/login/') {
      return _json({
        'token': token,
        'expires_at': DateTime.now()
            .toUtc()
            .add(const Duration(days: 30))
            .toIso8601String(),
        'user': {'id': 7, 'name': 'Private account name'},
        'organizations': organizations,
      });
    }
    if (route == 'mobile/logout/') return _json({'ok': true});
    if (route == 'organizations/') {
      return _json({
        'organizations': forbidden ? [organizations[1]] : organizations,
      });
    }
    if (forbidden && org == 1) return _json({'detail': 'No access'}, 403);
    final data = demoSnapshot(org);
    (data['me'] as Map)['organizations'] = organizations;
    if (route == 'tickets/' && org == 1 && delayed != null) {
      await delayed!.future;
    }
    return _json(data[route.replaceAll('/', '')] ?? []);
  });
  http.Response _json(dynamic value, [int status = 200]) => http.Response(
    jsonEncode(value),
    status,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );
}

void main() {
  test('Only HTTPS and loopback tunnels accept credentials', () {
    expect(parseServer('https://example.ru/').host, 'example.ru');
    expect(parseServer('http://127.0.0.1:18081').port, 18081);
    for (final value in [
      'http://example.ru',
      'http://89.169.20.154:18080',
      'https://user:pass@example.ru',
      'https://example.ru/path',
      'https://example.ru/?token=secret',
      'javascript:alert(1)',
      'https://example.ru/#secret',
    ]) {
      expect(() => parseServer(value), throwsA(isA<ApiError>()), reason: value);
    }
  });
  test(
    'Tokens are scoped to the configured origin and organization; redirects are rejected',
    () async {
      final log = Diagnostics(MemoryStore());
      final client = ApiClient(
        server: parseServer('https://example.ru'),
        token: token,
        organization: 1,
        log: log,
        transport: MockClient((r) async {
          expect(r.headers['Authorization'], 'Bearer $token');
          expect(r.headers['X-Organization-ID'], '1');
          expect(r.followRedirects, false);
          return http.Response(
            '',
            302,
            headers: {'location': 'https://other.ru'},
          );
        }),
      );
      await expectLater(client.call('me/'), throwsA(isA<ApiError>()));
      for (final value in [
        'https://evil.ru/api/documents/1/download/',
        '/api/documents/1/download/?organization=2',
        '/private-media/x',
        '/api/tickets/1/../../secret/',
      ]) {
        expect(() => client.resourceUri(value), throwsA(isA<ApiError>()));
      }
      expect(
        client.resourceUri('/api/documents/1/download/?organization=1').host,
        'example.ru',
      );
      await log.flush();
      expect(log.export(), isNot(contains(token)));
    },
  );
  test(
    'No secrets, business bodies or logins in persistent diagnostics',
    () async {
      final store = MemoryStore(),
          log = Diagnostics(MemoryStore()),
          server = Server();
      final c = LiftController(
        store: store,
        log: log,
        transport: server.client,
      );
      await c.initialize();
      await c.login('https://example.ru', 'secret-login', 'secret-password');
      await log.flush();
      final report = log.export();
      for (final value in [
        token,
        'secret-login',
        'secret-password',
        'Private account name',
        'Игнатьевское',
        'Не закрываются',
      ]) {
        expect(report, isNot(contains(value)));
      }
      expect(report, contains('login_success'));
      c.dispose();
    },
  );
  test(
    'Offline restart restores scoped data and drafts but never submits a transition',
    () async {
      final store = MemoryStore(),
          server = Server(),
          log = Diagnostics(MemoryStore());
      final first = LiftController(
        store: store,
        log: log,
        transport: server.client,
      );
      await first.initialize();
      await first.login('https://example.ru', 'worker', 'password');
      first.setDraft(103, 'My private work report', 1);
      await first.flushDrafts();
      first.dispose();
      server.offline = true;
      final restored = LiftController(
        store: store,
        log: log,
        transport: server.client,
      );
      await restored.initialize();
      expect(restored.list('tickets'), isNotEmpty);
      expect(restored.draft(103), 'My private work report');
      expect(restored.canWrite, false);
      final before = server.requests.length;
      await expectLater(
        restored.request(
          'tickets/103/complete/',
          method: 'POST',
          data: {'work_description': 'text'},
        ),
        throwsA(isA<ApiError>()),
      );
      expect(server.requests.length, before);
      restored.dispose();
    },
  );
  test(
    'Organizations keep different caches and reports; switching never reuses the other snapshot',
    () async {
      final store = MemoryStore(), server = Server();
      final c = LiftController(
        store: store,
        log: Diagnostics(MemoryStore()),
        transport: server.client,
      );
      await c.initialize();
      await c.login('https://example.ru', 'worker', 'password');
      c.setDraft(103, 'First employer report', 1);
      await c.flushDrafts();
      await c.selectOrganization(2);
      expect(c.list('tickets'), isEmpty);
      expect(c.draft(103), '');
      c.setDraft(103, 'Second employer report', 2);
      await c.flushDrafts();
      await c.selectOrganization(1);
      expect(c.draft(103), 'First employer report');
      expect(c.list('tickets'), isNotEmpty);
      expect(
        storageScope(parseServer('https://other.ru'), 7, 1),
        isNot(c.scope),
      );
      c.dispose();
    },
  );
  test(
    'Late responses from a previous organization cannot overwrite the active page',
    () async {
      final server = Server(),
          c = LiftController(
            store: MemoryStore(),
            log: Diagnostics(MemoryStore()),
            transport: null,
          );
      // Use a separate controller to keep the injectable transport immutable.
      c.dispose();
      final active = LiftController(
        store: MemoryStore(),
        log: Diagnostics(MemoryStore()),
        transport: server.client,
      );
      await active.initialize();
      await active.login('https://example.ru', 'worker', 'password');
      server.delayed = Completer<void>();
      final old = active.refresh();
      await Future<void>.delayed(Duration.zero);
      await active.selectOrganization(2);
      server.delayed!.complete();
      await old;
      expect(active.organization, 2);
      expect(active.me['organization'], 'Эверест');
      expect(active.list('tickets'), isEmpty);
      active.dispose();
    },
  );
  test('Revoked organization clears its cached data immediately', () async {
    final server = Server(), store = MemoryStore();
    final c = LiftController(
      store: store,
      log: Diagnostics(MemoryStore()),
      transport: server.client,
    );
    await c.initialize();
    await c.login('https://example.ru', 'worker', 'password');
    final key = c.scope;
    c.setDraft(103, 'sensitive report', 1);
    await c.flushDrafts();
    server.forbidden = true;
    await c.refresh();
    expect(c.organization, isNull);
    expect(c.snapshot, isEmpty);
    expect(await store.read('cache_$key'), isNull);
    expect(await store.read('drafts_$key'), isNull);
    c.dispose();
  });
  test(
    'Logout clears every employer cache and all credentials even without a connection',
    () async {
      final server = Server(), store = MemoryStore();
      final c = LiftController(
        store: store,
        log: Diagnostics(store),
        transport: server.client,
      );
      await c.initialize();
      await c.login('https://example.ru', 'worker', 'password');
      c.setDraft(103, 'private report', 1);
      await c.flushDrafts();
      await c.selectOrganization(2);
      server.offline = true;
      expect(await c.logout(), false);
      expect(c.loggedIn, false);
      expect(await store.read('session'), isNull);
      expect(
        store.values.keys.where(
          (key) =>
              key.startsWith('cache_') ||
              key.startsWith('drafts_') ||
              key.startsWith('resources_'),
        ),
        isEmpty,
      );
      expect(store.values.values.join(), isNot(contains(token)));
      c.dispose();
    },
  );
}
