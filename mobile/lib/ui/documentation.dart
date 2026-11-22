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
  final _search = TextEditingController();
  String? _error;
  bool _loading = true;
  int? _opening;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
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

  Future<void> _edit([Json? document]) async {
    final creating = document == null;
    final saved = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) => _TechnicalDocumentEditor(
          controller: widget.controller,
          organization: widget.organization,
          document: document,
        ),
      ),
    );
    if (saved != true || !mounted) return;
    if (creating) _search.clear();
    await _load();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            creating ? 'Документ добавлен' : 'Документация обновлена',
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: widget.controller,
    organization: widget.organization,
    builder: (context) {
      final query = _search.text.trim().toLowerCase();
      final words = query.split(RegExp(r'\s+'));
      final canManage = widget.controller.me['can_manage'] == true;
      final canEdit = widget.controller.canWrite && _opening == null;
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
              if (canManage) ...[
                FilledButton.icon(
                  onPressed: canEdit ? () => _edit() : null,
                  icon: const Icon(Icons.add),
                  label: const Text('Добавить документ'),
                ),
                const SizedBox(height: 12),
              ],
              TextField(
                controller: _search,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  labelText: 'Название, производитель, модель или тег',
                ),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: 16),
              if (_loading) const LinearProgressIndicator(),
              if (_error != null) ...[
                Text(_error!),
                TextButton(onPressed: _load, child: const Text('Повторить')),
              ],
              if (!_loading && _error == null && documents.isEmpty)
                EmptyState(
                  query.isEmpty ? 'Библиотека пока пуста' : 'Ничего не найдено',
                  query.isEmpty
                      ? 'Загруженные технические PDF появятся здесь.'
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
                    trailing: canManage
                        ? IconButton(
                            tooltip: 'Редактировать документ',
                            icon: const Icon(Icons.edit_outlined),
                            onPressed: canEdit ? () => _edit(document) : null,
                          )
                        : _opening == document['id']
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

class _TechnicalDocumentEditor extends StatefulWidget {
  const _TechnicalDocumentEditor({
    required this.controller,
    required this.organization,
    this.document,
  });

  final LiftController controller;
  final int organization;
  final Json? document;

  @override
  State<_TechnicalDocumentEditor> createState() =>
      _TechnicalDocumentEditorState();
}

class _TechnicalDocumentEditorState extends State<_TechnicalDocumentEditor> {
  static const _labels = {
    'title': ('Название', 200),
    'manufacturer': ('Производитель', 150),
    'model': ('Модель', 150),
    'documentation_tags': ('Теги через запятую', 640),
  };
  bool get _creating => widget.document == null;

  late final _fields = {
    for (final key in _labels.keys)
      key: TextEditingController(text: text(widget.document ?? {}, key, '')),
  };

  String? _pdf;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    final pdf = _pdf;
    if (pdf != null) unawaited(PlatformBridge.discardPickedPdf(pdf));
    for (final field in _fields.values) {
      field.dispose();
    }
    super.dispose();
  }

  Future<void> _pick() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final file = await PlatformBridge.pickPdf();
      if (file == null) return;
      if (!mounted) {
        await PlatformBridge.discardPickedPdf(file);
        return;
      }
      final previous = _pdf;
      setState(() => _pdf = file);
      if (previous != null) await PlatformBridge.discardPickedPdf(previous);
    } catch (error) {
      widget.controller.log.record('technical_document_pick_failed');
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final c = widget.controller;
    final document = widget.document;
    final pdf = _pdf;
    final fields = {
      for (final entry in _fields.entries) entry.key: entry.value.text.trim(),
      if (document?['updated_at'] case final String updatedAt)
        'expected_updated_at': updatedAt,
    };
    if (fields['title']!.isEmpty ||
        fields['manufacturer']!.isEmpty &&
            fields['documentation_tags']!.isEmpty) {
      setState(() => _error = 'Укажите название и производителя или теги.');
      return;
    }
    if (document == null && pdf == null) {
      setState(() => _error = 'Выберите PDF для загрузки.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (document == null) {
        await c.addTechnicalDocument(pdf!, fields, widget.organization);
        c.log.record('technical_document_added');
      } else {
        await c.updateTechnicalDocument(
          document['id'] as int,
          fields,
          widget.organization,
          pdf: pdf,
        );
        c.log.record('technical_document_updated');
      }
      if (mounted) Navigator.pop(context, true);
    } catch (error) {
      c.log.record(
        _creating
            ? 'technical_document_add_failed'
            : 'technical_document_update_failed',
      );
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: widget.controller,
    organization: widget.organization,
    builder: (context) => Scaffold(
      appBar: AppBar(
        title: Text(_creating ? 'Новый документ' : 'Редактировать документ'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          for (final entry in _labels.entries)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: TextField(
                controller: _fields[entry.key],
                enabled: !_busy,
                maxLength: entry.value.$2,
                decoration: InputDecoration(labelText: entry.value.$1),
              ),
            ),
          Wrap(
            spacing: 8,
            children: [
              OutlinedButton.icon(
                onPressed: _busy ? null : _pick,
                icon: const Icon(Icons.picture_as_pdf_outlined),
                label: Text(
                  _pdf != null
                      ? 'Выбрать другой PDF'
                      : _creating
                      ? 'Выбрать PDF'
                      : 'Заменить PDF',
                ),
              ),
              if (_pdf != null)
                TextButton(
                  onPressed: _busy
                      ? null
                      : () {
                          final file = _pdf;
                          setState(() => _pdf = null);
                          if (file != null) {
                            unawaited(PlatformBridge.discardPickedPdf(file));
                          }
                        },
                  child: Text(
                    _creating ? 'Убрать файл' : 'Оставить прежний PDF',
                  ),
                ),
            ],
          ),
          if (_pdf != null)
            const Text('Новый PDF будет загружен при сохранении.'),
          if (_busy) const LinearProgressIndicator(),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed:
                !_busy &&
                    widget.controller.canWrite &&
                    widget.controller.me['can_manage'] == true
                ? _save
                : null,
            child: Text(_creating ? 'Загрузить документ' : 'Сохранить'),
          ),
        ],
      ),
    ),
  );
}
