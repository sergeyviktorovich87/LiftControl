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
      await tester.pageBack();
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
      await tester.pageBack();
      await tester.pumpAndSettle();
      await tester.pageBack();
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
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      c.dispose();
    },
  );
}
