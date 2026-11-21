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
      await tester.tap(menu);
      await tester.pumpAndSettle();
      expect(
        find.widgetWithText(NavigationDrawerDestination, 'Ещё'),
        findsNothing,
      );
      expect(
        find.widgetWithText(NavigationDrawerDestination, 'Личные задания'),
        findsOneWidget,
      );
      expect(
        find.widgetWithText(NavigationDrawerDestination, 'Журнал ТО'),
        findsNothing,
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
  testWidgets('Short screen scrolls to the last menu section', (tester) async {
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
    final drawer = find.byType(NavigationDrawer);
    final scrollable = find.descendant(
      of: drawer,
      matching: find.byType(Scrollable),
    );
    final lastSection = find.byKey(const ValueKey('drawer-settings'));
    expect(
      find.widgetWithText(NavigationDrawerDestination, 'Ещё'),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey('drawer-home')).hitTestable(),
      findsOneWidget,
    );
    expect(lastSection.hitTestable(), findsNothing);
    expect(
      tester.state<ScrollableState>(scrollable).position.maxScrollExtent,
      greaterThan(0),
    );
    await tester.drag(scrollable, const Offset(0, -400));
    await tester.pumpAndSettle();
    expect(lastSection.hitTestable(), findsOneWidget);
    await tester.tap(lastSection);
    await tester.pumpAndSettle();
    expect(find.text('Системные уведомления'), findsOneWidget);
    expect(drawer.hitTestable(), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();
    c.dispose();
  });

  testWidgets('Drawer needs no scrolling when every section fits', (
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
    LiftMenuSection? selection;

    await tester.pumpWidget(
      MaterialApp(
        home: AdaptiveNavigationDrawer(
          items: items,
          selectedSection: LiftMenuSection.home,
          unread: const {LiftMenuSection.tickets: 3},
          onSelected: (section) => selection = section,
        ),
      ),
    );
    for (final item in items) {
      expect(find.text(item.label).hitTestable(), findsOneWidget);
    }
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('drawer-tickets')),
        matching: find.text('3'),
      ).hitTestable(),
      findsOneWidget,
    );
    expect(
      tester
          .state<ScrollableState>(find.byType(Scrollable))
          .position
          .maxScrollExtent,
      0,
    );
    await tester.tap(find.text('Дежурство'));
    expect(selection, LiftMenuSection.duty);
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
