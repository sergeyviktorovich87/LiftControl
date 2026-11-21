import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftcontrol_mobile/main.dart';
import 'package:liftcontrol_mobile/core/controller.dart';
import 'package:liftcontrol_mobile/core/diagnostics.dart';
import 'package:liftcontrol_mobile/core/storage.dart';
import 'package:liftcontrol_mobile/ui/adaptive_drawer.dart';

void main() {
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
      expect(find.byType(NavigationBar), findsNothing);
      expect(find.byType(NavigationRail), findsNothing);
      final menu = find.byTooltip('Открыть боковое меню');
      for (final name in ['Заявки', 'Объекты', 'Дежурство', 'Главная']) {
        await tester.tap(menu);
        await tester.pumpAndSettle();
        final destination = find.widgetWithText(
          NavigationDrawerDestination,
          name,
        );
        expect(destination, findsOneWidget);
        await tester.tap(destination);
        await tester.pumpAndSettle();
        expect(
          tester
              .widget<Scaffold>(find.byType(Scaffold).first)
              .bottomNavigationBar,
          isNull,
        );
        expect(
          tester.state<ScaffoldState>(find.byType(Scaffold).first).isDrawerOpen,
          isFalse,
        );
        expect(tester.takeException(), isNull, reason: name);
      }
      // All working sections must be available directly in the drawer,
      // or revealed by the height-aware overflow control.
      await tester.tap(menu);
      await tester.pumpAndSettle();
      if (find
          .widgetWithText(NavigationDrawerDestination, 'Ещё')
          .evaluate()
          .isNotEmpty) {
        await tester.tap(
          find.widgetWithText(NavigationDrawerDestination, 'Ещё'),
        );
        await tester.pumpAndSettle();
        expect(
          tester.state<ScaffoldState>(find.byType(Scaffold).first).isDrawerOpen,
          isTrue,
        );
      }
      expect(
        find.widgetWithText(NavigationDrawerDestination, 'Личные задания'),
        findsOneWidget,
      );
      expect(
        find.widgetWithText(NavigationDrawerDestination, 'Журнал ТО'),
        findsOneWidget,
      );
      tester.state<ScaffoldState>(find.byType(Scaffold).first).closeDrawer();
      await tester.pumpAndSettle();
      final bell = find.byTooltip('Центр уведомлений');
      final chat = find.byTooltip('Чат бригады');
      expect(tester.getCenter(bell).dx, lessThan(tester.getCenter(chat).dx));
      await tester.tap(bell);
      await tester.pumpAndSettle();
      expect(find.text('Центр уведомлений'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Профиль и настройки'));
      await tester.pumpAndSettle();
      expect(find.text('Системные уведомления'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      c.dispose();
    });
  }
  testWidgets('Short screen reveals overflow and expands in place', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 460);
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
    await tester.tap(find.byTooltip('Открыть боковое меню'));
    await tester.pumpAndSettle();
    final more = find.widgetWithText(NavigationDrawerDestination, 'Ещё');
    expect(more, findsOneWidget);
    await tester.tap(more);
    await tester.pumpAndSettle();
    expect(
      find.widgetWithText(NavigationDrawerDestination, 'Свернуть'),
      findsOneWidget,
    );
    expect(
      tester.state<ScaffoldState>(find.byType(Scaffold).first).isDrawerOpen,
      isTrue,
    );
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();
    c.dispose();
  });

  testWidgets('Drawer uses the last fitting row before offering more', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.padding = const FakeViewPadding(top: 24, bottom: 16);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPadding);
    const items = [
      LiftMenuItem(LiftMenuSection.home, 'Главная', Icons.home_outlined),
      LiftMenuItem(
        LiftMenuSection.tickets,
        'Заявки',
        Icons.assignment_outlined,
      ),
      LiftMenuItem(
        LiftMenuSection.elevators,
        'Объекты',
        Icons.elevator_outlined,
      ),
      LiftMenuItem(LiftMenuSection.duty, 'Дежурство', Icons.event_outlined),
    ];
    const exactFit = 24.0 + 60.0 + 4 * 56.0 + 16.0;
    tester.view.physicalSize = const Size(390, exactFit);
    var expansions = 0;
    LiftMenuSection? selection;

    await tester.pumpWidget(
      MaterialApp(
        home: AdaptiveNavigationDrawer(
          items: items,
          selectedSection: LiftMenuSection.home,
          onSelected: (section) => selection = section,
          onOverflowOpened: () => expansions++,
        ),
      ),
    );
    final more = find.text('Ещё');
    for (final item in items) {
      expect(find.text(item.label).hitTestable(), findsOneWidget);
    }
    expect(more, findsNothing);

    tester.view.physicalSize = const Size(390, exactFit - 1);
    await tester.pumpAndSettle();
    expect(find.text('Заявки').hitTestable(), findsOneWidget);
    expect(find.text('Объекты'), findsNothing);
    expect(more.hitTestable(), findsOneWidget);
    await tester.tap(more);
    await tester.pumpAndSettle();
    expect(expansions, 1);
    expect(find.text('Свернуть'), findsOneWidget);
    expect(find.text('Объекты'), findsOneWidget);
    final last = find.text('Дежурство');
    await tester.ensureVisible(last);
    await tester.pumpAndSettle();
    await tester.tap(last);
    expect(selection, LiftMenuSection.duty);
    await tester.pumpAndSettle();
    expect(find.text('Свернуть'), findsNothing);
    expect(more.hitTestable(), findsOneWidget);
  });

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
