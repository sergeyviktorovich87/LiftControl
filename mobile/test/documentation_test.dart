import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:liftcontrol_mobile/core/api.dart';
import 'package:liftcontrol_mobile/core/controller.dart';
import 'package:liftcontrol_mobile/core/diagnostics.dart';
import 'package:liftcontrol_mobile/core/storage.dart';
import 'package:liftcontrol_mobile/ui/documentation.dart';

void _signIn(LiftController controller, {required bool canManage}) {
  controller
    ..session = {
      'server': 'https://lift.example.com',
      'user': {'id': 1},
      'token': 'test-session',
    }
    ..organization = 7
    ..online = true
    ..snapshot = {
      'me': {'can_manage': canManage},
    };
}

class _LibraryController extends LiftController {
  _LibraryController(MemoryStore store, {bool canManage = true})
    : super(store: store, log: Diagnostics(store)) {
    _signIn(this, canManage: canManage);
  }

  final documents = <Json>[];

  @override
  Future<dynamic> resource(
    String path, {
    required int expectedOrganization,
  }) async {
    expect(path, 'documents/');
    expect(expectedOrganization, 7);
    return documents.toList();
  }

  @override
  Future<void> addTechnicalDocument(
    String pdf,
    Map<String, String> fields,
    int expectedOrg,
  ) async {
    expect(pdf, '/picked.pdf');
    expect(expectedOrg, 7);
    expect(fields['title'], 'Схема дверей');
    expect(fields['documentation_tags'], 'as380');
    documents.add({'id': 1, ...fields});
  }
}

void main() {
  testWidgets('Adds a PDF by tags and shows it after saving', (tester) async {
    tester.view.physicalSize = const Size(390, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final discarded = <String>[];
    const files = MethodChannel('ru.liftcontrol.app/files');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(files, (call) async {
      if (call.method == 'pickPdf') return '/picked.pdf';
      expect(call.method, 'discardPickedPdf');
      discarded.add(call.arguments['path'] as String);
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(files, null));

    final controller = _LibraryController(MemoryStore());
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: DocumentationPage(controller: controller, organization: 7),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'запрос без совпадений');
    await tester.pump();

    await tester.tap(find.text('Добавить документ'));
    await tester.pumpAndSettle();
    expect(find.text('Новый документ'), findsOneWidget);
    await tester.enterText(
      find.widgetWithText(TextField, 'Название'),
      '  Схема дверей  ',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Теги через запятую'),
      'as380',
    );
    final save = find.text('Загрузить документ');
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(find.text('Выберите PDF для загрузки.'), findsOneWidget);
    expect(controller.documents, isEmpty);

    final pick = find.text('Выбрать PDF');
    await tester.ensureVisible(pick);
    await tester.tap(pick);
    await tester.pumpAndSettle();
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();

    expect(find.text('Документ добавлен'), findsOneWidget);
    expect(find.text('Схема дверей'), findsOneWidget);
    expect(discarded, ['/picked.pdf']);
  });

  testWidgets('Users with read-only access cannot see the add button', (
    tester,
  ) async {
    final controller = _LibraryController(MemoryStore(), canManage: false);
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: DocumentationPage(controller: controller, organization: 7),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Добавить документ'), findsNothing);
  });

  test(
    'Creates a technical document by multipart POST in the active organization',
    () async {
      final dir = Directory.systemTemp.createTempSync('lift-document-');
      addTearDown(() => dir.deleteSync(recursive: true));
      const pdf = '%PDF-1.7\n% fixture';
      final file = File('${dir.path}/upload.pdf')..writeAsStringSync(pdf);
      var requests = 0;
      final transport = MockClient((request) async {
        requests++;
        expect(request.url.path, '/api/documents/');
        expect(request.method, 'POST');
        expect(request.headers['X-Organization-ID'], '7');
        expect(request.headers['Authorization'], 'Bearer test-session');
        expect(
          request.headers['content-type'],
          startsWith('multipart/form-data;'),
        );
        final body = utf8.decode(request.bodyBytes);
        expect(body, contains('name="title"'));
        expect(body, contains('\r\n\r\nСхема дверей\r\n'));
        expect(body, contains('name="file"; filename="document.pdf"'));
        expect(body, contains(pdf));
        return http.Response('{"id":1}', 201);
      });
      addTearDown(transport.close);
      final store = MemoryStore();
      final controller = LiftController(
        store: store,
        log: Diagnostics(store),
        transport: transport,
      );
      addTearDown(controller.dispose);
      const fields = {'title': 'Схема дверей', 'documentation_tags': 'as380'};

      _signIn(controller, canManage: false);
      await expectLater(
        controller.addTechnicalDocument(file.path, fields, 7),
        throwsA(isA<ApiError>()),
      );
      _signIn(controller, canManage: true);
      await expectLater(
        controller.addTechnicalDocument(file.path, fields, 8),
        throwsA(isA<ApiError>()),
      );
      expect(requests, 0);
      await controller.addTechnicalDocument(file.path, fields, 7);
      expect(requests, 1);
    },
  );
}
