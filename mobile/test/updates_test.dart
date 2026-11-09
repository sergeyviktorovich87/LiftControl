import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:liftcontrol_mobile/core/controller.dart';
import 'package:liftcontrol_mobile/core/demo.dart';
import 'package:liftcontrol_mobile/core/device_bridge.dart';
import 'package:liftcontrol_mobile/core/diagnostics.dart';
import 'package:liftcontrol_mobile/core/storage.dart';
import 'package:liftcontrol_mobile/ui/shell.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  int checks = 0, registrations = 0, permissionPrompts = 0;
  int? version;
  bool configured = false;
  late LiftController c;
  setUp(() {
    checks = 0; registrations = 0; permissionPrompts = 0;
    version = 2031; configured = false;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(DeviceBridge.channel, (call) async {
      if (call.method == 'status') return {'version_code': 2030, 'notifications_allowed': true};
      if (call.method == 'registerPush') { if ((call.arguments as Map)['prompt'] == true) { permissionPrompts++; } return 'test-fcm-token'; }
      return null;
    });
    final store = MemoryStore();
    c = LiftController(store: store, log: Diagnostics(store), transport: MockClient((request) async {
      Object result = {};
      if (request.url.path == '/api/updates/') {
        checks++;
        result = {'android': version == null ? null : {'version_code': version, 'version': '0.5.0', 'size': 100, 'sha256': 'a' * 64}, 'installed': {'panel': '0.10'}};
      }
      if (request.url.path == '/api/mobile/push/') {
        if (request.method == 'POST') { registrations++; result = {'ok': true}; }
        else { result = {'enabled': configured, 'config': configured ? {'apiKey': 'key', 'appId': 'app', 'projectId': 'project', 'messagingSenderId': 'sender'} : null}; }
      }
      return http.Response(jsonEncode(result), 200, headers: {'content-type': 'application/json'});
    }));
    c.session = {'server': 'https://example.com', 'token': 'a' * 43, 'user': {'id': 7}};
    c.organization = 1; c.organizations = [{'id': 1, 'name': 'Компания', 'role': 'MECHANIC'}];
    c.snapshot = demoSnapshot(1); c.online = true; c.starting = false;
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(DeviceBridge.channel, null);
    c.dispose();
  });

  testWidgets('Opening prompts once; Later suppresses duplicates until the next foreground', (tester) async {
    await tester.pumpWidget(MaterialApp(home: LiftShell(controller: c)));
    await tester.pumpAndSettle();
    expect(find.text('Доступно обновление'), findsOneWidget);
    await tester.tap(find.text('Позже')); await tester.pumpAndSettle();
    await c.checkUpdates(force: true); await tester.pumpAndSettle();
    expect(find.text('Доступно обновление'), findsNothing);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(find.text('Доступно обновление'), findsOneWidget);
    expect(checks, greaterThanOrEqualTo(3));
    await tester.pumpWidget(const SizedBox());
  });

  for (final current in [2030, 2029, null]) {
    testWidgets('No update dialog for server version $current', (tester) async {
      version = current;
      await tester.pumpWidget(MaterialApp(home: LiftShell(controller: c)));
      await tester.pumpAndSettle();
      expect(find.text('Доступно обновление'), findsNothing);
      expect(checks, 1);
      await tester.pumpWidget(const SizedBox());
    });
  }

  test('Forced foreground checks bypass throttling', () async {
    await c.checkUpdates(); await c.checkUpdates();
    expect(checks, 1);
    await c.checkUpdates(force: true); expect(checks, 2);
  });

  test('Push registers without a manual opt-in and retries after server setup', () async {
    await c.syncDevice(); expect(registrations, 0);
    configured = true;
    await c.syncDevice(); expect(registrations, 1); expect(permissionPrompts, 1);
    await c.syncDevice(); expect(registrations, 2); expect(permissionPrompts, 1);
  });
}
