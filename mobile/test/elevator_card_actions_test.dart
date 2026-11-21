import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftcontrol_mobile/core/api.dart';
import 'package:liftcontrol_mobile/core/controller.dart';
import 'package:liftcontrol_mobile/core/diagnostics.dart';
import 'package:liftcontrol_mobile/core/storage.dart';
import 'package:liftcontrol_mobile/ui/elevators.dart';

class _CardController extends LiftController {
  _CardController({required bool admin})
    : super(store: MemoryStore(), log: Diagnostics(MemoryStore())) {
    organization = 1;
    online = true;
    session = {};
    snapshot = {
      'me': {
        'can_manage': admin,
        'can_manage_access': admin,
        'can_create_ticket': admin,
        'lift_documents_api': 1,
      },
      'buildings': [
        {'id': 8, 'address': 'Ленина 5'},
      ],
      'elevators': [lift],
    };
  }

  final Json lift = {
    'id': 7,
    'building': 8,
    'address': 'Ленина 5',
    'inventory_number': 'M-114',
    'entrance': '1 (Левый)',
    'active': true,
  };
  Json? changes;

  @override
  bool get canCreateTicket => me['can_create_ticket'] == true;

  @override
  Future<void> refresh() async => notifyListeners();

  @override
  Future<dynamic> resource(String path, {int? expectedOrganization}) async {
    return [];
  }

  @override
  Future<dynamic> request(
    String path, {
    String method = 'GET',
    Json? data,
    int? expectedOrganization,
  }) async {
    expect(expectedOrganization, 1);
    expect(path, 'elevators/7/');
    expect(method, 'PATCH');
    changes = data;
    lift.addAll(data!);
    return lift;
  }
}

void main() {
  for (final admin in [true, false]) {
    testWidgets('Lift card actions respect permissions (admin: $admin)', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(360, 800);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = 1.3;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final controller = _CardController(admin: admin);
      await tester.pumpWidget(
        MaterialApp(
          home: ElevatorPage(controller: controller, id: 7, organization: 1),
        ),
      );
      await tester.pumpAndSettle();

      final edit = find.text('Изменить сведения');
      final ticket = find.text('Создать заявку');
      final parts = find.text('Нужна запчасть');
      final archive = find.text('Удалить из списка');
      final passport = find.descendant(
        of: find.byKey(const ValueKey('lift-passport')),
        matching: find.byType(Scrollable),
      );
      await tester.scrollUntilVisible(parts, 220, scrollable: passport);
      expect(parts, findsOneWidget);
      for (final button in [edit, ticket, archive]) {
        expect(button, admin ? findsOneWidget : findsNothing);
      }
      if (admin) {
        await tester.ensureVisible(edit);
        await tester.tap(edit);
        await tester.pumpAndSettle();
        final entrance = find.widgetWithText(TextFormField, 'Подъезд');
        await tester.enterText(entrance, '2 (Правый)');
        final save = find.text('Сохранить');
        await tester.scrollUntilVisible(save, 220);
        await tester.tap(save);
        await tester.pumpAndSettle();
        expect(controller.changes, {'entrance': '2 (Правый)'});
        expect(find.text('Подъезд 2 (Правый)'), findsOneWidget);
      }
      await tester.scrollUntilVisible(parts, 220, scrollable: passport);
      await tester.tap(parts);
      await tester.pumpAndSettle();
      expect(find.text('Запросить запчасть').first, findsOneWidget);
      expect(find.text('Ленина 5 · M-114'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      controller.dispose();
    });
  }
}
