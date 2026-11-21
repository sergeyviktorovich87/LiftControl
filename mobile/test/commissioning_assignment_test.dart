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
      'me': {'can_manage_access': true, 'notification_counts_api': 1},
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
      'lift_count': 2,
      'progress': 10,
    };
    if (path == 'commissioning/') {
      return [
        {...project, 'unassigned_count': assignment == null ? 1 : 0},
        {'id': 3, 'name': 'Другой объект', 'lift_count': 6, 'progress': 50},
        {'id': 4, 'name': 'Третий объект', 'lift_count': 19, 'progress': 65},
      ];
    }
    expect(path, 'commissioning/1/');
    return {
      ...project,
      'lifts': [
        {
          'id': 2,
          'label': 'подъезд 1 (левый)',
          'progress': 10,
          'assignees': [
            if (assignment != null) {'user': 20, 'name': 'Иван Петров'},
          ],
        },
        {
          'id': 5,
          'label': 'Правый',
          'entrance': '2',
          'progress': 20,
          'assignees': [
            {'user': 30, 'name': 'Пётр Иванов'},
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
          home: CommissioningPage(controller: controller),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Другой объект'), findsOneWidget);
      expect(find.text('Третий объект'), findsOneWidget);
      expect(find.text('1 без исполнителя'), findsOneWidget);
      await tester.tap(find.text('Жилой дом'));
      await tester.pumpAndSettle();
      expect(find.text('Подъезд 1'), findsOneWidget);
      expect(find.text('Подъезд 2'), findsOneWidget);
      await tester.tap(find.text('Без исполнителя · 1'));
      await tester.pumpAndSettle();
      expect(find.text('Правый'), findsNothing);
      expect(find.text('Чат'), findsNothing);
      expect(find.text('Чат объекта'), findsNothing);
      expect(find.byTooltip('Чат наладчиков'), findsOneWidget);
      await tester.tap(find.text('Назначить'));
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
      expect(find.text('На все лифты назначены исполнители.'), findsOneWidget);
      await tester.tap(find.text('Все лифты'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Левый'));
      await tester.pumpAndSettle();
      expect(find.text('Иван Петров'), findsOneWidget);
      expect(find.text('История работ'), findsOneWidget);
      final entrance = find.text('Подъезд 1');
      expect(find.ancestor(of: entrance, matching: find.byType(Scaffold)), findsOneWidget);
      expect(tester.widget<Text>(entrance).style, isNotNull);
      expect(tester.getRect(entrance).left, greaterThanOrEqualTo(16));
      expect(tester.getRect(entrance).right, lessThanOrEqualTo(344));
      await tester.tap(find.byTooltip('К лифтам объекта'));
      await tester.pumpAndSettle();
      expect(find.text('Правый'), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.pumpWidget(const SizedBox.shrink());
      controller.dispose();
    },
  );
}
