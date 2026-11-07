import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:liftcontrol_mobile/main.dart';
import 'package:liftcontrol_mobile/core/controller.dart';
import 'package:liftcontrol_mobile/core/diagnostics.dart';
import 'package:liftcontrol_mobile/core/demo.dart';
import 'package:liftcontrol_mobile/core/storage.dart';

void main() {
  testWidgets('Employer header and data follow an asynchronous company switch', (tester) async {
    final gate = Completer<void>();
    const companies = [
      {'id': 1, 'name': 'Мегаполис', 'role': 'MECHANIC'},
      {'id': 2, 'name': 'Эверест', 'role': 'DIRECTOR'},
    ];
    final client = MockClient((request) async {
      final route = request.url.path.replaceFirst('/api/', '').replaceAll('/', '');
      final company = int.tryParse(request.headers['X-Organization-ID'] ?? '') ?? 1;
      if (route == 'mobilelogin') {
        return http.Response(jsonEncode({
          'token': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          'expires_at': DateTime.now().toUtc().add(const Duration(days: 1)).toIso8601String(),
          'user': {'id': 1}, 'organizations': companies,
        }), 200, headers: {'content-type': 'application/json; charset=utf-8'});
      }
      if (company == 2 && route == 'me') await gate.future;
      final data = demoSnapshot(company);
      (data['me'] as Map)['organizations'] = companies;
      return http.Response(jsonEncode(route == 'updates' || route == 'mobilepush'
          ? {} : data[route] ?? []), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    });
    final c = LiftController(store: MemoryStore(), log: Diagnostics(MemoryStore()), transport: client);
    await c.initialize();
    await c.login('https://example.ru', 'test-only', 'test-password-only');
    await tester.pumpWidget(LiftApp(controller: c, initialize: false));
    await tester.pumpAndSettle();
    expect(find.text('Мегаполис'), findsOneWidget);
    final switching = c.selectOrganization(2);
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('Игнатьевское'), findsNothing);
    gate.complete();
    await switching;
    await tester.pumpAndSettle();
    expect(find.text('Эверест'), findsOneWidget);
    expect(find.textContaining('Игнатьевское'), findsNothing);
    await tester.tap(find.byKey(const Key('organization-switch')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Мегаполис'));
    await tester.pumpAndSettle();
    expect(find.text('Мегаполис'), findsOneWidget);
    expect(c.organization, 1);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();
    c.dispose();
    client.close();
  });
  for (final spec in [
    (360.0, 800.0, 1.0, false),
    (390.0, 844.0, 1.3, true),
    (960.0, 800.0, 1.0, false),
  ]) {
    testWidgets('Demo navigation fits ${spec.$1}px and text scale ${spec.$3}', (
      tester,
    ) async {
      tester.view.physicalSize = Size(spec.$1, spec.$2);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = spec.$3;
      addTearDown(() => tester.view.resetPhysicalSize());
      addTearDown(() => tester.view.resetDevicePixelRatio());
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final c = LiftController(
        store: MemoryStore(),
        log: Diagnostics(MemoryStore()),
      );
      await c.initialize();
      c.dark = spec.$4;
      await tester.pumpWidget(LiftApp(controller: c, initialize: false));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('preview')));
      await tester.pumpAndSettle();
      expect(find.text('Здравствуйте, Сергей'), findsOneWidget);
      expect(tester.takeException(), isNull);
      for (final name in ['Заявки', 'Объекты', 'Дежурство', 'Ещё', 'Главная']) {
        await tester.tap(find.text(name).last);
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull, reason: name);
      }
      await tester.tap(find.byTooltip('Профиль и настройки'));
      await tester.pumpAndSettle();
      expect(find.text('Системные уведомления'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      c.dispose();
    });
  }
  testWidgets('Switching demo employer hides the first company data', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(() => tester.view.resetPhysicalSize());
    addTearDown(() => tester.view.resetDevicePixelRatio());
    final c = LiftController(
      store: MemoryStore(),
      log: Diagnostics(MemoryStore()),
    );
    await c.initialize();
    c.preview();
    await tester.pumpWidget(LiftApp(controller: c, initialize: false));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Мегаполис').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Эверест'));
    await tester.pumpAndSettle();
    expect(c.organization, 2);
    expect(find.textContaining('Игнатьевское'), findsNothing);
    expect(find.text('Эверест'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();
    c.dispose();
  });
}
