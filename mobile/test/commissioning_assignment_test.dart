import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftcontrol_mobile/core/api.dart';
import 'package:liftcontrol_mobile/core/controller.dart';
import 'package:liftcontrol_mobile/core/diagnostics.dart';
import 'package:liftcontrol_mobile/core/storage.dart';
import 'package:liftcontrol_mobile/ui/commissioning.dart';

class _CommissioningController extends LiftController {
  _CommissioningController()
    : super(store: MemoryStore(), log: Diagnostics(MemoryStore())) {
    organization = 1;
    online = true;
    session = {};
    snapshot = {
      'me': {'can_manage_access': true},
    };
  }

  bool _failLoading = true;
  Json? assignment;

  @override
  Future<dynamic> resource(String path, {int? expectedOrganization}) async {
    const project = {
      'id': 1,
      'name': 'Жилой дом',
      'address': 'Ленина, 5',
      'lift_count': 1,
      'progress': 10,
    };
    if (path == 'commissioning/') return [project];
    expect(path, 'commissioning/1/');
    return {
      ...project,
      'lifts': [
        {
          'id': 2,
          'label': 'Лифт №1',
          'progress': 10,
          'assignees': [
            if (assignment != null) {'user': 20, 'name': 'Иван Петров'},
          ],
        },
      ],
    };
  }

  @override
  Future<dynamic> request(
    String path, {
    String method = 'GET',
    Json? data,
    int? expectedOrganization,
  }) async {
    expect(expectedOrganization, 1);
    if (path == 'commissioning/assignees/') {
      if (_failLoading) {
        _failLoading = false;
        throw const ApiError('Ошибка соединения');
      }
      return [
        {
          'user': 20,
          'role': 'MECHANIC',
          'name': 'Иван Петров',
          'can_commissioning': false,
        },
        {
          'user': 30,
          'role': 'ADJUSTER',
          'name': 'Пётр Иванов',
          'can_commissioning': true,
        },
      ];
    }
    expect(path, 'commissioning/1/lifts/2/assign/');
    expect(method, 'POST');
    assignment = data;
    return {'active': true};
  }
}

void main() {
  testWidgets(
    'Find a mechanic and confirm the additional role before assigning',
    (tester) async {
      tester.view.physicalSize = const Size(360, 700);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final controller = _CommissioningController();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CommissioningPage(controller: controller, initialProject: 1),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Чат'));
      await tester.pumpAndSettle();
      expect(find.text('Сообщений пока нет.'), findsOneWidget);
      expect(find.text('Назначить исполнителя'), findsNothing);
      await tester.tap(find.text('Лифты'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Назначить исполнителя'));
      await tester.pumpAndSettle();
      expect(find.text('Не удалось загрузить сотрудников'), findsOneWidget);

      await tester.tap(find.text('Повторить'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'Петров');
      await tester.pumpAndSettle();
      expect(find.text('Пётр Иванов'), findsNothing);
      await tester.tap(find.text('Иван Петров'));
      await tester.pumpAndSettle();
      expect(controller.assignment, isNull);
      await tester.tap(find.text('Добавить роль и назначить'));
      await tester.pumpAndSettle();
      expect(controller.assignment, {'user': 20, 'grant_commissioning': true});
      expect(find.text('Исполнители: Иван Петров'), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.pumpWidget(const SizedBox.shrink());
      controller.dispose();
    },
  );
}
