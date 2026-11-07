import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:liftcontrol_mobile/main.dart';
import 'package:liftcontrol_mobile/core/controller.dart';
import 'package:liftcontrol_mobile/core/diagnostics.dart';
import 'package:liftcontrol_mobile/core/storage.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets(
    'Native Android to Django: login, report, image, second employer and logout',
    (tester) async {
      final store = DeviceStore();
      await store.clear();
      final c = LiftController(store: store, log: Diagnostics(store));
      await c.initialize();
      await tester.pumpWidget(LiftApp(controller: c, initialize: false));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const Key('server')),
        'http://127.0.0.1:18081',
      );
      await tester.enterText(find.byKey(const Key('username')), 'ci-mechanic');
      await tester.enterText(
        find.byKey(const Key('password')),
        'ci-test-password-only',
      );
      await tester.tap(find.byKey(const Key('login')));
      Future<void> waitUntil(bool Function() test) async {
        for (var i = 0; i < 100; i++) {
          await tester.pump(const Duration(milliseconds: 250));
          if (test()) return;
        }
        fail('State did not become ready.');
      }

      await waitUntil(() => c.online && c.snapshot.isNotEmpty);
      await tester.pumpAndSettle();
      expect(c.me['can_create_ticket'], true);
      expect(c.me['role'], 'MECHANIC');
      await binding.convertFlutterSurfaceToImage();
      await tester.pumpAndSettle();
      await binding.takeScreenshot('01-home');
      await tester.tap(find.text('Заявки').last);
      await tester.pumpAndSettle();
      await binding.takeScreenshot('02-tickets');
      await tester.tap(find.text('Проверка дверей • CI'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Принять заявку'));
      await waitUntil(() => c.list('tickets').first['status'] == 'IN_PROGRESS');
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(find.text('Лифт остановлен'), 250,
        scrollable: find.byType(Scrollable).first);
      await tester.tap(find.text('Лифт остановлен'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField), 'Ожидаем запасную плату');
      await tester.tap(find.text('Сохранить остановку'));
      await waitUntil(() => c.list('tickets').first['status'] == 'STOPPED');
      await tester.pumpAndSettle();
      expect(c.list('elevators').first['stopped_at'], isNotNull);
      await binding.takeScreenshot('02b-lift-stopped');
      await tester.scrollUntilVisible(find.text('Продолжить ремонт'), 250,
        scrollable: find.byType(Scrollable).first);
      await tester.tap(find.text('Продолжить ремонт'));
      await waitUntil(() => c.list('tickets').first['status'] == 'IN_PROGRESS');
      await tester.pumpAndSettle();
      expect(c.list('elevators').first['stopped_at'], isNotNull);
      // Exercise the real multipart API. Camera/gallery UI is checked on a physical phone.
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      canvas.drawRect(
        const Rect.fromLTWH(0, 0, 16, 16),
        Paint()..color = const Color(0xFF237651),
      );
      final image = await recorder.endRecording().toImage(16, 16);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await c.uploadPhoto(
        c.list('tickets').first['id'] as int,
        bytes!.buffer.asUint8List(),
        'ci.png',
        c.organization!,
      );
      image.dispose();
      await tester.scrollUntilVisible(
        find.byTooltip('Добавить комментарий'),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.byTooltip('Добавить комментарий'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(TextFormField),
        'Проверены контакты дверей',
      );
      await tester.tap(find.text('Отправить'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Завершить с отчётом'),
        -300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Завершить с отчётом'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(TextFormField),
        'Восстановлены контакты. Работа проверена.',
      );
      await tester.tap(find.text('Завершить'));
      await waitUntil(() => c.list('tickets').first['status'] == 'DONE');
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Выполнена'),
        -300,
        scrollable: find.byType(Scrollable).first,
      );
      await binding.takeScreenshot('03-ticket-completed');
      expect(c.draft(c.list('tickets').first['id'] as int), '');
      expect(c.list('elevators').first['stopped_at'], isNull);
      expect(c.list('tickets').first['stop_reason'], 'Ожидаем запасную плату');
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      final original = c.organization;
      await tester.tap(find.text('Мегаполис • CI').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Эверест • CI'));
      await waitUntil(() => c.organization != original && !c.refreshing);
      await tester.pumpAndSettle();
      expect(c.list('tickets'), isEmpty);
      await binding.takeScreenshot('04-second-employer');
      await tester.tap(find.text('Эверест • CI').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Мегаполис • CI'));
      await waitUntil(() => c.organization == original && !c.refreshing);
      await tester.pumpAndSettle();
      expect(c.list('tickets').first['status'], 'DONE');
      await tester.tap(find.text('Объекты').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Тестовая улица'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Тестовая улица, 1'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('CI-001'));
      await tester.pumpAndSettle();
      await binding.takeScreenshot('05-elevator');
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Профиль и настройки'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Switch));
      await tester.pumpAndSettle();
      expect(c.dark, true);
      await binding.takeScreenshot('06-dark-settings');
      await c.log.flush();
      expect(c.log.export(), isNot(contains('ci-test-password-only')));
      expect(c.log.export(), isNot(contains('ci-mechanic')));
      await tester.scrollUntilVisible(
        find.text('Выйти из аккаунта'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Выйти из аккаунта'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Выйти'));
      await waitUntil(() => !c.loggedIn);
      await tester.pumpAndSettle();
      expect(await store.read('session'), isNull);
      expect(find.byKey(const Key('login')), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.enterText(find.byKey(const Key('server')), 'http://127.0.0.1:18081');
      await tester.enterText(find.byKey(const Key('username')), 'ci-admin');
      await tester.enterText(find.byKey(const Key('password')), 'ci-admin-password-only');
      await tester.tap(find.byKey(const Key('login')));
      await waitUntil(() => c.online && c.me['role'] == 'ADMIN');
      await tester.pumpAndSettle();
      await tester.tap(find.text('Ещё').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Сотрудники'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Добавить сотрудника'));
      await tester.pumpAndSettle();
      final staffName = find.widgetWithText(TextFormField, 'ФИО сотрудника');
      await tester.ensureVisible(staffName);
      await tester.enterText(staffName, 'Новый сотрудник CI');
      final loginField = find.widgetWithText(TextFormField, 'Логин');
      await tester.ensureVisible(loginField);
      await tester.enterText(loginField, 'ci-created-mechanic');
      final passwordField = find.widgetWithText(TextFormField, 'Пароль (от 12 символов)');
      await tester.ensureVisible(passwordField);
      await tester.enterText(passwordField, 'UniqueNativeCreatedPassword-2026!');
      await tester.scrollUntilVisible(find.text('Создать сотрудника и доступ'), 250,
        scrollable: find.byType(Scrollable).first);
      await tester.tap(find.text('Создать сотрудника и доступ'));
      await waitUntil(() => c.list('technicians').any((t) => t['full_name'] == 'Новый сотрудник CI'));
      await tester.pumpAndSettle();
      final members = await c.request('organizations/members/');
      expect((members as List).where((m) => m['name'] == 'Новый сотрудник CI').length, 1);
      await binding.takeScreenshot('07-admin-created-employee');
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      await c.logout();
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      c.dispose();
    },
  );
}
