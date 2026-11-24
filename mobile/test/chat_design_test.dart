import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftcontrol_mobile/core/api.dart';
import 'package:liftcontrol_mobile/core/controller.dart';
import 'package:liftcontrol_mobile/core/diagnostics.dart';
import 'package:liftcontrol_mobile/core/storage.dart';
import 'package:liftcontrol_mobile/ui/chat.dart';
import 'package:liftcontrol_mobile/ui/common.dart';
import 'offline_test.dart' show OfflineServer, controller, login;

class _ChatController extends LiftController {
  _ChatController()
    : super(store: MemoryStore(), log: Diagnostics(MemoryStore())) {
    organization = 1;
    online = true;
    session = {};
    snapshot = {
      'me': {
        'id': 1,
        'name': 'Сергей',
        'organization': 'Организация',
        'chat_design_api': 1,
        'can_export_chat': true,
      },
      'chat': [
        for (var i = 1; i <= 12; i++)
          {
            'id': i,
            'author': i == 12 ? 1 : 2,
            'author_name': 'Алексей',
            'body': 'Сообщение $i',
            'created_at': '2026-11-24T10:00:00Z',
            'attachments': <Json>[],
            'receipt': i == 12 ? {'total': 2, 'delivered': 2, 'read': 1} : null,
          },
      ],
    };
  }
  @override
  Future<void> refresh() async => notifyListeners();
  @override
  Future<dynamic> request(
    String path, {
    String method = 'GET',
    Json? data,
    int? expectedOrganization,
  }) async => path == 'chat/pinned/' ? {'message': null} : {};
}

void main() {
  for (final scale in [1.0, 1.4]) {
    testWidgets(
      'Shared chat fits narrow screen at scale $scale and supports reply',
      (tester) async {
        tester.view.physicalSize = const Size(360, 800);
        tester.view.devicePixelRatio = 1;
        tester.platformDispatcher.textScaleFactorTestValue = scale;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        final c = _ChatController();
        await tester.pumpWidget(MaterialApp(home: ChatPage(controller: c)));
        await tester.pumpAndSettle();
        expect(find.text('Чат'), findsOneWidget);
        expect(find.text('Чат команды'), findsNothing);
        expect(tester.takeException(), isNull);
        await tester.tap(find.byTooltip('Меню чата'));
        await tester.pumpAndSettle();
        expect(find.text('Вложения'), findsOneWidget);
        await tester.tap(find.text('Поиск в чате'));
        await tester.pumpAndSettle();
        await tester.tap(find.byTooltip('Закрыть поиск'));
        await tester.pumpAndSettle();
        await tester.longPress(find.text('Сообщение 11'));
        await tester.pumpAndSettle();
        expect(find.text('Копировать'), findsOneWidget);
        await tester.tap(find.text('Ответить'));
        await tester.pumpAndSettle();
        expect(find.byTooltip('Отменить ответ'), findsOneWidget);
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pumpAndSettle();
        c.dispose();
      },
    );
  }
  test('Lift number and entrance have distinct labels', () {
    expect(
      entranceLabel({'entrance': '20', 'entrance_kind': 'LIFT'}),
      'Лифт №20',
    );
    expect(entranceLabel({'entrance': '3'}), 'Подъезд 3');
  });
  test('Reply target survives an offline restart', () async {
    final store = MemoryStore(), server = OfflineServer()..mediaApi = true;
    var c = controller(store, server);
    await login(c);
    server.offline = true;
    await c.refresh();
    await c.request(
      'chat/',
      method: 'POST',
      data: {'body': 'Принял', 'reply_to': 42},
      expectedOrganization: 1,
    );
    expect(c.pendingOperations.single['command']['body']['reply_to'], 42);
    c.dispose();
    c = controller(store, server);
    await c.initialize();
    expect(c.pendingOperations.single['command']['body']['reply_to'], 42);
    c.dispose();
  });
}
