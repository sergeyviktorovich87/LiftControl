import 'dart:async';

import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';
import 'platform_bridge.dart';

Future<void> openTechnicalDocument(
  BuildContext context,
  LiftController controller,
  int organization,
  Json document,
) async {
  try {
    final bytes = await controller.download(
      text(document, 'url'),
      organization,
      pdf: true,
    );
    if (context.mounted && controller.organization == organization) {
      await PlatformBridge.openPdf(bytes);
    }
  } catch (error) {
    controller.log.record('technical_document_open_failed');
    if (context.mounted) showError(context, error);
  }
}

class DocumentationPage extends StatefulWidget {
  const DocumentationPage({
    super.key,
    required this.controller,
    required this.organization,
  });

  final LiftController controller;
  final int organization;

  @override
  State<DocumentationPage> createState() => _DocumentationPageState();
}

class _DocumentationPageState extends State<DocumentationPage> {
  List<Json> _documents = [];
  String _search = '';
  String? _error;
  bool _loading = true;
  int? _opening;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final response = await widget.controller.resource(
        'documents/',
        expectedOrganization: widget.organization,
      );
      if (mounted) setState(() => _documents = records(response));
    } catch (error) {
      widget.controller.log.record('technical_documentation_load_failed');
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _open(Json document) async {
    setState(() => _opening = document['id'] as int);
    await openTechnicalDocument(
      context,
      widget.controller,
      widget.organization,
      document,
    );
    if (mounted) setState(() => _opening = null);
  }

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: widget.controller,
    organization: widget.organization,
    builder: (context) {
      final words = _search.trim().toLowerCase().split(RegExp(r'\s+'));
      final documents = _documents.where((document) {
        final content = [
          for (final key in [
            'title',
            'manufacturer',
            'model',
            'documentation_tags',
          ])
            text(document, key, ''),
        ].join(' ').toLowerCase();
        return words.every(content.contains);
      });
      return Scaffold(
        appBar: AppBar(title: const Text('Документация')),
        body: RefreshIndicator(
          onRefresh: _load,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.all(18),
            children: [
              TextField(
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  labelText: 'Название, производитель, модель или тег',
                ),
                onChanged: (value) => setState(() => _search = value),
              ),
              const SizedBox(height: 16),
              if (_loading) const LinearProgressIndicator(),
              if (_error != null) ...[
                Text(_error!),
                TextButton(onPressed: _load, child: const Text('Повторить')),
              ],
              if (!_loading && _error == null && documents.isEmpty)
                EmptyState(
                  _search.trim().isEmpty
                      ? 'Библиотека пока пуста'
                      : 'Ничего не найдено',
                  _search.trim().isEmpty
                      ? 'Технические PDF появятся здесь после загрузки в веб-панели.'
                      : 'Попробуйте другое название, модель или тег.',
                  icon: Icons.menu_book_outlined,
                ),
              for (final document in documents)
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.picture_as_pdf_outlined),
                    title: Text(text(document, 'title')),
                    subtitle: Text(
                      [
                        for (final key in [
                          'manufacturer',
                          'model',
                          'documentation_tags',
                        ])
                          if (text(document, key, '').isNotEmpty)
                            text(document, key, ''),
                      ].join(' · '),
                    ),
                    trailing: _opening == document['id']
                        ? const SizedBox.square(
                            dimension: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.open_in_new),
                    onTap: _opening == null ? () => _open(document) : null,
                  ),
                ),
            ],
          ),
        ),
      );
    },
  );
}
