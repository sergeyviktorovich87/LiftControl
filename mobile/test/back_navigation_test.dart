import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftcontrol_mobile/main.dart';
import 'package:liftcontrol_mobile/core/controller.dart';
import 'package:liftcontrol_mobile/core/diagnostics.dart';
import 'package:liftcontrol_mobile/core/storage.dart';
import 'package:liftcontrol_mobile/ui/tickets.dart';
import 'package:liftcontrol_mobile/ui/elevators.dart';

void main() {
  testWidgets(
    'System back closes drawer, then restores sections and detail route',
    (tester) async {
      final store = MemoryStore();
      final c = LiftController(store: store, log: Diagnostics(store));
      await c.initialize();
      c.preview();
      await tester.pumpWidget(LiftApp(controller: c, initialize: false));
      await tester.pumpAndSettle();
      Future<void> section(String title) async {
        await tester.tap(find.byTooltip('Открыть боковое меню'));
        await tester.pumpAndSettle();
        await tester.tap(
          find.widgetWithText(NavigationDrawerDestination, title),
        );
        await tester.pumpAndSettle();
      }

      await section('Заявки');
      expect(find.byType(TicketsPage), findsOneWidget);
      await section('Объекты');
      expect(find.byType(ElevatorsPage), findsOneWidget);
      await tester.tap(find.byTooltip('Открыть боковое меню'));
      await tester.pumpAndSettle();
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(
        tester.state<ScaffoldState>(find.byType(Scaffold).first).isDrawerOpen,
        isFalse,
      );
      expect(find.byType(ElevatorsPage), findsOneWidget);
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.byType(TicketsPage), findsOneWidget);
      await tester.tap(find.byTooltip('Центр уведомлений'));
      await tester.pumpAndSettle();
      expect(find.text('Центр уведомлений'), findsOneWidget);
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.byType(TicketsPage), findsOneWidget);
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.text('Здравствуйте, Сергей'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      c.dispose();
    },
  );
}
