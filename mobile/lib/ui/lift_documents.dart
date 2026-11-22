import 'dart:async';

import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';
import 'platform_bridge.dart';

const _categories = {
  'CONTRACT': 'Договоры',
  'ORDER': 'Приказы о назначении',
  'INSPECTION': 'Освидетельствование',
};

String inspectionDateLabel(Object? value) {
  if (value is! String) return 'Не назначено';
  final date = DateTime.tryParse(value);
  if (date == null) return 'Не назначено';
  String two(int number) => number.toString().padLeft(2, '0');
  return '${two(date.day)}.${two(date.month)}.${date.year}';
}

Future<void> _openPdf(
  BuildContext context,
  LiftController c,
  Json document,
  int org,
) async {
  try {
    final bytes = await c.download(text(document, 'url'), org, pdf: true);
    if (context.mounted && c.organization == org) {
      await PlatformBridge.openPdf(bytes);
    }
  } catch (error) {
    c.log.record('lift_document_open_failed');
    if (context.mounted) showError(context, error);
  }
}

class ElevatorInspection extends StatefulWidget {
  const ElevatorInspection({
    super.key,
    required this.controller,
    required this.elevator,
    required this.organization,
  });
  final LiftController controller;
  final int elevator, organization;

  @override
  State<ElevatorInspection> createState() => _ElevatorInspectionState();
}

class _ElevatorInspectionState extends State<ElevatorInspection> {
  Json _inspection = {};
  bool _loading = true;
  String? _error;

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
      final data = await widget.controller.request(
        'lift-inspections/${widget.elevator}/',
        expectedOrganization: widget.organization,
      );
      if (mounted) {
        setState(() => _inspection = Map<String, dynamic>.from(data as Map));
      }
    } catch (error) {
      widget.controller.log.record('lift_inspection_load_failed');
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final acts = records(_inspection['acts'] ?? []);
    return ListView(
      padding: const EdgeInsets.all(18),
      children: [
        ListTile(
          title: const Text('Следующее освидетельствование'),
          subtitle: Text(inspectionDateLabel(_inspection['date'])),
          trailing: IconButton(
            tooltip: 'Обновить',
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh),
          ),
        ),
        if (_loading) const LinearProgressIndicator(),
        if (_error != null) Text(_error!),
        if (!_loading && _error == null && acts.isEmpty)
          const Text('Актов пока нет.'),
        for (final act in acts)
          Card(
            child: ListTile(
              leading: const Icon(Icons.picture_as_pdf_outlined),
              title: Text(text(act, 'title')),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => _openPdf(
                context,
                widget.controller,
                act,
                widget.organization,
              ),
            ),
          ),
      ],
    );
  }
}

class LiftDocumentsPage extends StatefulWidget {
  const LiftDocumentsPage({super.key, required this.controller});
  final LiftController controller;

  @override
  State<LiftDocumentsPage> createState() => _LiftDocumentsPageState();
}

class _LiftDocumentsPageState extends State<LiftDocumentsPage> {
  late final int _org = c.organization!;
  LiftController get c => widget.controller;
  Json? _lift;
  String _category = 'CONTRACT';
  Object? _date;
  List<Json> _documents = [];
  bool _busy = false;

  int? get _id => _lift?['id'] as int?;

  Future<void> _run(Future<void> Function() action) async {
    if (_busy || c.organization != _org) return;
    setState(() => _busy = true);
    try {
      await action();
      final id = _id;
      if (id == null) return;
      final documents = await c.request(
        'lift-documents/?elevator=$id&category=$_category',
        expectedOrganization: _org,
      );
      final inspection = _category == 'INSPECTION'
          ? await c.request('lift-inspections/$id/', expectedOrganization: _org)
          : null;
      if (mounted) {
        setState(() {
          _documents = records(documents);
          _date = inspection?['date'];
        });
      }
    } catch (error) {
      c.log.record('lift_documents_action_failed');
      if (mounted) showError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _upload() async {
    final title = await askText(
      context,
      title: 'Название документа',
      label: 'Название',
      minimum: 1,
      maximum: 200,
      action: 'Выбрать PDF',
    );
    if (title == null || title.trim().isEmpty || !mounted) return;
    await _run(() async {
      final file = await PlatformBridge.pickPdf();
      if (file == null) return;
      try {
        if (!mounted) return;
        await c.uploadPdf('lift-documents/', file, {
          'title': title.trim(),
          'elevator': '$_id',
          'category': _category,
        }, _org);
      } finally {
        await PlatformBridge.discardPickedPdf(file);
      }
      c.log.record('lift_document_uploaded');
    });
  }

  Future<void> _remove(Json document) async {
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: const Text('Удалить документ?'),
        content: Text(text(document, 'title')),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialog, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialog, true),
            child: const Text('Удалить'),
          ),
        ],
      ),
    );
    if (accepted != true || !mounted) {
      return;
    }
    await _run(() async {
      await c.request(
        'lift-documents/${document['id']}/',
        method: 'DELETE',
        expectedOrganization: _org,
      );
      c.log.record('lift_document_deleted');
    });
  }

  Future<void> _saveDate({bool clear = false}) async {
    final now = c.orgNow;
    final today = DateTime(now.year, now.month, now.day);
    final saved = DateTime.tryParse('$_date');
    final selected = clear
        ? null
        : await showDatePicker(
            context: context,
            firstDate: today,
            lastDate: DateTime(9999, 12, 31),
            initialDate: saved != null && !saved.isBefore(today)
                ? saved
                : today,
          );
    if (!mounted || (selected == null && !clear)) return;
    await _run(() async {
      await c.request(
        'lift-inspections/$_id/',
        method: 'PATCH',
        expectedOrganization: _org,
        data: {'date': selected?.toIso8601String().split('T').first},
      );
      c.log.record('lift_inspection_date_saved');
      unawaited(c.refresh());
    });
  }

  String _liftLabel(Json lift) =>
      '${text(lift, 'address')} · ${entranceLabel(lift)} · ${liftLabel(lift)}';

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: c,
    organization: _org,
    builder: (context) {
      if (c.me['can_manage_lift_documents'] != true) {
        return Scaffold(
          appBar: AppBar(title: const Text('Документы')),
          body: const Center(child: Text('Раздел доступен администратору.')),
        );
      }
      return Scaffold(
        appBar: AppBar(title: const Text('Документы')),
        body: ListView(
          padding: const EdgeInsets.all(18),
          children: [
            Autocomplete<Json>(
              displayStringForOption: _liftLabel,
              optionsBuilder: (input) {
                if (_busy) return const <Json>[];
                final query = input.text.toLowerCase().trim();
                return c
                    .list('elevators')
                    .where(
                      (row) => _liftLabel(row).toLowerCase().contains(query),
                    )
                    .take(60);
              },
              fieldViewBuilder: (context, input, focus, submit) => TextField(
                controller: input,
                focusNode: focus,
                enabled: !_busy,
                onSubmitted: (_) => submit(),
                decoration: const InputDecoration(
                  labelText: 'Найти лифт по адресу или номеру',
                ),
              ),
              onSelected: (lift) {
                setState(() {
                  _lift = lift;
                  _documents = [];
                  _date = null;
                });
                unawaited(_run(() async {}));
              },
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: _category,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Раздел'),
              items: [
                for (final category in _categories.entries)
                  DropdownMenuItem(
                    value: category.key,
                    child: Text(category.value),
                  ),
              ],
              onChanged: _busy
                  ? null
                  : (value) {
                      if (value == null) return;
                      setState(() {
                        _category = value;
                        _documents = [];
                        _date = null;
                      });
                      unawaited(_run(() async {}));
                    },
            ),
            if (_busy) const LinearProgressIndicator(),
            if (_lift != null) ...[
              const SizedBox(height: 12),
              Text(
                _liftLabel(_lift!),
                style: Theme.of(context).textTheme.titleMedium,
              ),
              if (_category == 'INSPECTION') ...[
                ListTile(
                  title: const Text('Следующее освидетельствование'),
                  subtitle: Text(inspectionDateLabel(_date)),
                ),
                Wrap(
                  spacing: 8,
                  children: [
                    OutlinedButton(
                      onPressed:
                          c.canWrite && !_busy && _lift?['active'] == true
                          ? () => _saveDate()
                          : null,
                      child: const Text('Назначить дату'),
                    ),
                    if (_date != null)
                      TextButton(
                        onPressed:
                            c.canWrite && !_busy && _lift?['active'] == true
                            ? () => _saveDate(clear: true)
                            : null,
                        child: const Text('Снять дату'),
                      ),
                  ],
                ),
              ],
              FilledButton.icon(
                onPressed: c.canWrite && !_busy ? _upload : null,
                icon: const Icon(Icons.upload_file_outlined),
                label: const Text('Добавить PDF'),
              ),
              for (final document in _documents)
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.picture_as_pdf_outlined),
                    title: Text(text(document, 'title')),
                    onTap: () => _openPdf(context, c, document, _org),
                    trailing: IconButton(
                      tooltip: 'Удалить PDF',
                      onPressed: c.canWrite && !_busy
                          ? () => _remove(document)
                          : null,
                      icon: const Icon(Icons.delete_outline),
                    ),
                  ),
                ),
            ],
          ],
        ),
      );
    },
  );
}
