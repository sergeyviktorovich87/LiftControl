import 'dart:async';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';
import 'sync_queue.dart';

class CommissioningPage extends StatefulWidget {
  const CommissioningPage({
    super.key,
    required this.controller,
    this.initialProject,
  });
  final LiftController controller;
  final int? initialProject;
  @override
  State<CommissioningPage> createState() => _CommissioningPageState();
}

enum _ProjectTab {
  lifts('Лифты'),
  work('Работы'),
  expenses('Расходы'),
  chat('Чат');

  const _ProjectTab(this.label);
  final String label;
}

class _CommissioningPageState extends State<CommissioningPage> {
  List<Json> _projects = [];
  Json? _detail;
  bool _busy = false;
  String _error = '';
  LiftController get c => widget.controller;
  late final int org;
  var _tab = _ProjectTab.lifts;
  bool get canManage => c.me['can_manage_access'] == true;
  int? _readGeneration;

  @override
  void initState() {
    super.initState();
    org = c.organization!;
    c.addListener(_afterRefresh);
    unawaited(_load(initialProject: widget.initialProject));
  }

  @override
  void dispose() {
    c.removeListener(_afterRefresh);
    super.dispose();
  }

  void _afterRefresh() {
    if (!c.online ||
        c.refreshing ||
        _busy ||
        _readGeneration == c.syncRevision) {
      return;
    }
    _readGeneration = c.syncRevision;
    unawaited(_load());
  }

  Future<void> _load({int? initialProject}) async {
    if (!mounted || c.organization != org) return;
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      final rows = records(
        await c.resource('commissioning/', expectedOrganization: org),
      );
      final selected = initialProject ?? _detail?['id'];
      final data = selected == null
          ? null
          : await c.resource(
              'commissioning/$selected/',
              expectedOrganization: org,
            );
      if (!mounted) return;
      setState(() {
        _projects = rows;
        _detail = data is Map ? Map<String, dynamic>.from(data) : null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
      c.log.record('commissioning_load_failed');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _open(int id) async {
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      final result = await c.resource(
        'commissioning/$id/',
        expectedOrganization: org,
      );
      if (mounted) {
        setState(() {
          _detail = Map<String, dynamic>.from(result as Map);
          _tab = _ProjectTab.lifts;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _post(String path, Json body) async {
    if (!c.canWrite || _busy) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Для изменения нужна связь с сервером.'),
          ),
        );
      }
      return;
    }
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      await c.request(
        path,
        method: 'POST',
        data: body,
        expectedOrganization: org,
      );
      if (!mounted) return;
      setState(() => _busy = false);
      await _load();
    } catch (e) {
      c.log.record('commissioning_mutation_failed');
      if (mounted) {
        setState(() {
          _error = '$e';
          _busy = false;
        });
      }
    }
  }

  Future<Json?> _form(
    String title,
    Map<String, String> labels, {
    Map<String, String> defaults = const {},
    bool expense = false,
  }) async {
    final inputs = {
      for (final entry in labels.entries)
        entry.key: TextEditingController(text: defaults[entry.key] ?? ''),
    };
    final formKey = GlobalKey<FormState>();
    XFile? receipt;
    int? expenseLift;
    DateTime spent = c.orgNow;
    final result = await showDialog<Json>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, update) => AlertDialog(
          title: Text(title),
          content: Form(
            key: formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (final entry in labels.entries)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: TextFormField(
                        controller: inputs[entry.key],
                        maxLength: entry.key == 'description' ? 2000 : 300,
                        keyboardType: ['amount', 'price'].contains(entry.key)
                            ? const TextInputType.numberWithOptions(
                                decimal: true,
                              )
                            : TextInputType.text,
                        decoration: InputDecoration(labelText: entry.value),
                        validator: (value) =>
                            value == null || value.trim().isEmpty
                            ? 'Заполните поле'
                            : null,
                      ),
                    ),
                  if (expense) ...[
                    DropdownButtonFormField<int>(
                      initialValue: expenseLift,
                      decoration: const InputDecoration(labelText: 'Лифт'),
                      items: [
                        const DropdownMenuItem(
                          value: 0,
                          child: Text('Весь объект'),
                        ),
                        for (final l in records(
                          _detail!['lifts'],
                        ).where((l) => l['can_edit'] == true))
                          DropdownMenuItem(
                            value: l['id'] as int,
                            child: Text(text(l, 'label')),
                          ),
                      ],
                      onChanged: (value) => update(() => expenseLift = value),
                    ),
                    TextButton.icon(
                      icon: const Icon(Icons.event),
                      label: Text(
                        'Дата • ${dateLabel(spent.toIso8601String().substring(0, 10), 0)}',
                      ),
                      onPressed: () async {
                        final date = await showDatePicker(
                          context: ctx,
                          initialDate: spent,
                          firstDate: DateTime(2000),
                          lastDate: DateTime(2100),
                        );
                        if (date != null && ctx.mounted) {
                          update(() => spent = date);
                        }
                      },
                    ),
                    TextButton.icon(
                      icon: const Icon(Icons.camera_alt_outlined),
                      label: Text(
                        receipt == null
                            ? 'Прикрепить фото чека'
                            : 'Заменить фото чека',
                      ),
                      onPressed: () async {
                        try {
                          final photo = await _pickReceipt(ctx);
                          if (photo != null && ctx.mounted) {
                            update(() => receipt = photo);
                          }
                        } catch (error) {
                          if (ctx.mounted) showError(ctx, error);
                        }
                      },
                    ),
                  ],
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Отмена'),
            ),
            FilledButton(
              onPressed: () {
                if (formKey.currentState!.validate()) {
                  Navigator.pop(ctx, <String, dynamic>{
                    for (final entry in inputs.entries)
                      entry.key: entry.value.text.trim(),
                    if (expenseLift != null && expenseLift != 0)
                      'lift': expenseLift,
                    if (expense)
                      'spent_on': spent.toIso8601String().substring(0, 10),
                    'receipt': ?receipt,
                  });
                }
              },
              child: const Text('Сохранить'),
            ),
          ],
        ),
      ),
    );
    for (final controller in inputs.values) {
      controller.dispose();
    }
    return result;
  }

  Future<void> _createProject() async {
    final body = await _form('Новый объект наладки', {
      'name': 'Название объекта',
      'address': 'Адрес',
    });
    if (body != null) await _post('commissioning/', body);
  }

  Future<void> _addLift() async {
    final p = _detail!;
    final body = await _form('Добавить лифт', {'label': 'Лифт / номер'});
    if (body != null) await _post('commissioning/${p['id']}/lifts/', body);
  }

  Future<void> _assign(Json lift) async {
    final project = _detail!['id'] as int;
    final assigned = records(lift['assignees'] ?? [])
        .map((row) => row['user'])
        .toSet();
    final chosen = await showModalBottomSheet<Json>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      builder: (context) => _AssigneePicker(
        lift: text(lift, 'label'),
        assigned: assigned,
        load: () async {
          try {
            return records(
              await c.request(
                'commissioning/assignees/',
                expectedOrganization: org,
              ),
            );
          } catch (_) {
            c.log.record('commissioning_member_list_failed');
            rethrow;
          }
        },
      ),
    );
    if (!mounted || chosen == null) return;
    final grant = chosen['can_commissioning'] != true;
    if (grant) {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Добавить роль «Наладчик»?'),
          content: Text(
            '${text(chosen, 'name')} получит доступ к разделу «Наладка» '
            'и назначение на ${text(lift, 'label')}. Роль «Механик» сохранится.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Отмена'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Добавить роль и назначить'),
            ),
          ],
        ),
      );
      if (!mounted || confirmed != true) return;
    }
    await _post('commissioning/$project/lifts/${lift['id']}/assign/', {
      'user': chosen['user'],
      if (grant) 'grant_commissioning': true,
    });
  }

  Future<void> _progress(Json lift) async {
    final project = _detail!['id'] as int;
    var value = (lift['progress'] as num).toDouble();
    final note = TextEditingController();
    final result = await showDialog<Json>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, update) => AlertDialog(
          title: Text('Готовность: ${lift['label']}'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('${value.round()}%'),
              Slider(
                min: 0,
                max: 100,
                divisions: 100,
                value: value,
                onChanged: (v) => update(() => value = v),
              ),
              TextField(
                controller: note,
                maxLines: 3,
                maxLength: 4000,
                onChanged: (_) => update(() {}),
                decoration: const InputDecoration(
                  labelText: 'Что сделано (обязательно)',
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Отмена'),
            ),
            FilledButton(
              onPressed:
                  value.round() == lift['progress'] || note.text.trim().isEmpty
                  ? null
                  : () => Navigator.pop(ctx, {
                      'revision': lift['revision'],
                      'progress': value.round(),
                      'description': note.text.trim(),
                    }),
              child: const Text('Зафиксировать'),
            ),
          ],
        ),
      ),
    );
    note.dispose();
    if (result != null) {
      if (c.canRecordCommissioning) {
        await _queue(project, 'progress', {...result, 'lift': lift['id']});
      } else {
        await _post(
          'commissioning/$project/lifts/${lift['id']}/progress/',
          result,
        );
      }
    }
  }

  Future<void> _addExpense() async {
    final project = _detail!['id'] as int;
    final body = await _form('Личный расход', {
      'amount': 'Сумма, ₽',
      'description': 'За что оплачено',
    }, expense: true);
    if (body == null) return;
    final photo = body.remove('receipt') as XFile?;
    body['amount'] = (body['amount'] as String).replaceAll(',', '.');
    if (c.canRecordCommissioning) {
      await _queue(project, 'expense', body, receipt: photo);
    } else {
      await _post('commissioning/$project/expenses/', body);
    }
  }

  Future<XFile?> _pickReceipt(BuildContext context) async {
    final source = await showModalBottomSheet<ImageSource>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.camera_alt_outlined),
              title: const Text('Сфотографировать чек'),
              onTap: () => Navigator.pop(ctx, ImageSource.camera),
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text('Выбрать фото'),
              onTap: () => Navigator.pop(ctx, ImageSource.gallery),
            ),
          ],
        ),
      ),
    );
    if (source == null) return null;
    return ImagePicker().pickImage(
      source: source,
      maxWidth: 1920,
      maxHeight: 1920,
      imageQuality: 80,
    );
  }

  Future<void> _queue(
    int project,
    String action,
    Json body, {
    XFile? receipt,
  }) async {
    if (!mounted || _busy) return;
    final expectedOrganization = org;
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      if (receipt != null && await receipt.length() > 10 * 1024 * 1024) {
        throw const ApiError('Фото чека больше 10 МБ.');
      }
      await c.queueCommissioning(
        project,
        action,
        body,
        receipt: await receipt?.readAsBytes(),
        expectedOrganization: expectedOrganization,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Сохранено на телефоне · ожидает отправки'),
          ),
        );
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        _afterRefresh();
      }
    }
  }

  Future<void> _receipt(Json expense) async {
    final project = _detail!['id'] as int;
    try {
      final photo = await _pickReceipt(context);
      if (!mounted || photo == null) return;
      if (c.canRecordCommissioning) {
        await _queue(project, 'receipt', {
          'expense': expense['id'],
        }, receipt: photo);
      } else {
        await c.uploadCommissioningReceipt(
          project,
          expense['id'] as int,
          await photo.readAsBytes(),
          photo.name,
          expectedOrganization: org,
        );
        if (mounted) await _load();
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _showReceipt(Json expense) async {
    try {
      final bytes = await c.download(
        '/api/commissioning/${_detail!['id']}/expenses/${expense['id']}/receipt/',
        org,
      );
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Чек'),
          content: InteractiveViewer(
            child: Image.memory(bytes, fit: BoxFit.contain),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Закрыть'),
            ),
          ],
        ),
      );
    } catch (error) {
      if (mounted) showError(context, error);
    }
  }

  Future<void> _writeMessage(int project) async {
    final body = await _form('Написать в чат', {'text': 'Сообщение'});
    if (body == null) return;
    if (c.canRecordCommissioning) {
      await _queue(project, 'message', body);
    } else {
      await _post('commissioning/$project/messages/', body);
    }
  }

  Future<void> _askPost(
    String title,
    String path,
    Map<String, String> fields,
  ) async {
    final body = await _form(title, fields);
    if (body != null) await _post(path, body);
  }

  Widget _section(String title, List<Widget> children) => Card(
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 10),
          ...children,
        ],
      ),
    ),
  );

  Widget _liftCard(
    Json lift, {
    required bool canQueue,
    required bool canAssign,
  }) {
    final assignees = records(lift['assignees'] ?? [])
        .map((member) => text(member, 'name'))
        .join(', ');
    final history = records(lift['history'] ?? []);
    final factory = text(lift, 'factory_number', '');
    final progress = (lift['progress'] as num).toDouble();
    return _section('${lift['label']} · ${lift['progress']}%', [
      LinearProgressIndicator(value: progress / 100),
      const SizedBox(height: 8),
      if (factory.isNotEmpty) Text('Заводской номер: $factory'),
      Text(
        assignees.isEmpty
            ? 'Исполнитель не назначен'
            : 'Исполнители: $assignees',
      ),
      if (canManage && _detail?['archived'] != true)
        OutlinedButton.icon(
          onPressed: canAssign ? () => _assign(lift) : null,
          icon: const Icon(Icons.person_add_outlined),
          label: const Text('Назначить исполнителя'),
        ),
      if (canQueue && lift['can_edit'] == true)
        FilledButton.tonal(
          onPressed: () => _progress(lift),
          child: const Text('Записать работу и готовность'),
        ),
      if (history.isNotEmpty)
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: Text('История работ · ${history.length}'),
          children: [
            for (final entry in history)
              ListTile(
                dense: true,
                title: Text(
                  '${entry['before']}% → ${entry['after']}% · ${entry['author']}',
                ),
                subtitle: Text(text(entry, 'description')),
              ),
          ],
        ),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    final p = _detail;
    final allowed = c.canWrite && !_busy && p?['archived'] != true;
    final canQueue =
        !_busy &&
        p?['archived'] != true &&
        (c.canRecordCommissioning || c.canWrite);
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 4),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  'Наладка',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              if (c.pendingCount > 0)
                IconButton(
                  tooltip: 'Очередь отправки · ${c.pendingCount}',
                  icon: Badge(
                    label: Text('${c.pendingCount}'),
                    child: const Icon(Icons.cloud_upload_outlined),
                  ),
                  onPressed: () => Navigator.push(
                    context,
                    MaterialPageRoute<void>(
                      builder: (_) => SyncQueuePage(controller: c),
                    ),
                  ),
                ),
              IconButton(
                tooltip: 'Обновить',
                onPressed: _busy ? null : _load,
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
        ),
        if (_error.isNotEmpty)
          Padding(
            padding: const EdgeInsets.all(12),
            child: Text(
              _error,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        if (!c.online)
          const Padding(
            padding: EdgeInsets.all(8),
            child: Text(
              'Нет сети. Прогресс, расходы и сообщения сохраняются на телефоне.',
            ),
          ),
        if (p != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Wrap(
              spacing: 8,
              children: [
                for (final tab in _ProjectTab.values)
                  ChoiceChip(
                    label: Text(tab.label),
                    selected: _tab == tab,
                    showCheckmark: false,
                    onSelected: (_) => setState(() => _tab = tab),
                  ),
              ],
            ),
          ),
        if (_busy) const LinearProgressIndicator(),
        Expanded(
          child: ListView(
            key: PageStorageKey((p?['id'], _tab)),
            padding: const EdgeInsets.all(12),
            children: [
              if (p == null) ...[
                if (canManage)
                  FilledButton.icon(
                    onPressed: c.canWrite && !_busy ? _createProject : null,
                    icon: const Icon(Icons.add),
                    label: const Text('Создать объект'),
                  ),
                for (final project in _projects)
                  Card(
                    child: ListTile(
                      title: Text(text(project, 'name')),
                      subtitle: Text(
                        '${project['address']} · ${project['lift_count']} лифтов',
                      ),
                      trailing: Text('${project['progress']}%'),
                      onTap: _busy ? null : () => _open(project['id'] as int),
                    ),
                  ),
                if (_projects.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(24),
                    child: Text('Назначенных объектов пока нет.'),
                  ),
              ] else ...[
                OutlinedButton.icon(
                  onPressed: _busy
                      ? null
                      : () => setState(() {
                          _detail = null;
                          _tab = _ProjectTab.lifts;
                        }),
                  icon: const Icon(Icons.arrow_back),
                  label: const Text('Все объекты'),
                ),
                const SizedBox(height: 10),
                _section(text(p, 'name'), [
                  Text(text(p, 'address')),
                  Text('Общая готовность: ${p['progress']}%'),
                  if (p['archived'] == true)
                    const Text('Архив · только просмотр'),
                  if (_tab == _ProjectTab.lifts &&
                      canManage &&
                      p['archived'] != true)
                    TextButton.icon(
                      onPressed: allowed ? _addLift : null,
                      icon: const Icon(Icons.add),
                      label: const Text('Добавить лифт'),
                    ),
                ]),
                if (_tab == _ProjectTab.lifts) ...[
                  if (records(p['lifts'] ?? []).isEmpty)
                    const EmptyState(
                      'Лифтов пока нет',
                      'Добавьте лифт на объект.',
                    ),
                  for (final lift in records(p['lifts'] ?? []))
                    _liftCard(lift, canQueue: canQueue, canAssign: allowed),
                  _section('Запросы на добавление лифтов', [
                    for (final r in records(p['lift_requests'] ?? []))
                      ListTile(
                        dense: true,
                        title: Text(text(r, 'label')),
                        subtitle: Text(switch (r['status']) {
                          'APPROVED' => 'Одобрен',
                          'REJECTED' => 'Отклонён',
                          _ => 'На рассмотрении',
                        }),
                        trailing:
                            canManage && allowed && r['status'] == 'PENDING'
                            ? Wrap(
                                children: [
                                  IconButton(
                                    onPressed: () => _post(
                                      'commissioning/${p['id']}/lift-requests/${r['id']}/decision/',
                                      {'approve': true},
                                    ),
                                    icon: const Icon(Icons.check),
                                    tooltip: 'Одобрить',
                                  ),
                                  IconButton(
                                    onPressed: () => _post(
                                      'commissioning/${p['id']}/lift-requests/${r['id']}/decision/',
                                      {'approve': false},
                                    ),
                                    icon: const Icon(Icons.close),
                                    tooltip: 'Отклонить',
                                  ),
                                ],
                              )
                            : null,
                      ),
                    if (records(p['lift_requests'] ?? []).isEmpty)
                      const Text('Запросов пока нет.'),
                    if (!canManage && allowed)
                      OutlinedButton(
                        onPressed: () => _askPost(
                          'Запросить лифт',
                          'commissioning/${p['id']}/lift-requests/',
                          {'label': 'Обозначение лифта'},
                        ),
                        child: const Text('Запросить добавление лифта'),
                      ),
                  ]),
                ],
                if (_tab == _ProjectTab.work) ...[
                  _section('Потребности', [
                    for (final need in records(p['needs'] ?? []))
                      ListTile(
                        dense: true,
                        title: Text(
                          '${need['blocking'] == true ? '⛔ ' : ''}${need['description']}',
                        ),
                        subtitle: Text(
                          need['resolved'] == true ? 'Закрыта' : 'Ожидает',
                        ),
                        trailing:
                            canManage && allowed && need['resolved'] != true
                            ? IconButton(
                                icon: const Icon(Icons.check),
                                tooltip: 'Закрыть',
                                onPressed: () => _post(
                                  'commissioning/${p['id']}/needs/${need['id']}/resolve/',
                                  {},
                                ),
                              )
                            : null,
                      ),
                    if (allowed)
                      OutlinedButton.icon(
                        onPressed: () => _askPost(
                          'Потребность',
                          'commissioning/${p['id']}/needs/',
                          {'description': 'Что требуется'},
                        ),
                        icon: const Icon(Icons.add),
                        label: const Text('Добавить потребность'),
                      ),
                  ]),
                  _section('Дополнительные работы', [
                    for (final extra in records(p['extras'] ?? []))
                      ListTile(
                        dense: true,
                        title: Text(text(extra, 'description')),
                        subtitle: Text(
                          '${extra['price']} ₽ · ${extra['status']}',
                        ),
                        trailing:
                            canManage && allowed && extra['status'] == 'PENDING'
                            ? Wrap(
                                children: [
                                  IconButton(
                                    onPressed: () => _post(
                                      'commissioning/${p['id']}/extra-work/${extra['id']}/decision/',
                                      {'approve': true},
                                    ),
                                    icon: const Icon(Icons.check),
                                    tooltip: 'Согласовать',
                                  ),
                                  IconButton(
                                    onPressed: () => _post(
                                      'commissioning/${p['id']}/extra-work/${extra['id']}/decision/',
                                      {'approve': false},
                                    ),
                                    icon: const Icon(Icons.close),
                                    tooltip: 'Отклонить',
                                  ),
                                ],
                              )
                            : null,
                      ),
                    if (allowed)
                      OutlinedButton.icon(
                        onPressed: () => _askPost(
                          'Дополнительная работа',
                          'commissioning/${p['id']}/extra-work/',
                          {'description': 'Работа', 'price': 'Стоимость, ₽'},
                        ),
                        icon: const Icon(Icons.add),
                        label: const Text('Предложить работу'),
                      ),
                  ]),
                ],
                if (_tab == _ProjectTab.expenses)
                  _section(
                    canManage ? 'Расходы сотрудников' : 'Мои личные расходы',
                    [
                      if (records(p['expenses'] ?? []).isEmpty)
                        const Text('Расходов пока нет.'),
                      for (final expense in records(p['expenses'] ?? []))
                        ListTile(
                          dense: true,
                          title: Text(
                            '${expense['amount']} ₽ · ${expense['description']}',
                          ),
                          subtitle: Text(
                            [
                              expense['author'],
                              expense['spent_on'],
                              if (expense['has_receipt'] == true)
                                'Чек прикреплён',
                            ].whereType<String>().join(' · '),
                          ),
                          onTap: expense['has_receipt'] == true
                              ? () => _showReceipt(expense)
                              : null,
                          trailing:
                              expense['has_receipt'] != true &&
                                  !canManage &&
                                  canQueue
                              ? IconButton(
                                  icon: const Icon(Icons.camera_alt_outlined),
                                  tooltip: 'Прикрепить чек',
                                  onPressed: () => _receipt(expense),
                                )
                              : canManage &&
                                    allowed &&
                                    expense['reimbursed_at'] == null
                              ? TextButton(
                                  onPressed: () => _post(
                                    'commissioning/${p['id']}/expenses/${expense['id']}/reimburse/',
                                    {},
                                  ),
                                  child: const Text('Возместить'),
                                )
                              : null,
                        ),
                      if (!canManage && canQueue)
                        FilledButton.tonal(
                          onPressed: _addExpense,
                          child: const Text('Добавить личный расход'),
                        ),
                    ],
                  ),
                if (_tab == _ProjectTab.chat)
                  _section('Чат объекта', [
                    if (records(p['messages'] ?? []).isEmpty)
                      const Text('Сообщений пока нет.'),
                    for (final m in records(p['messages'] ?? []))
                      ListTile(
                        dense: true,
                        title: Text(text(m, 'author')),
                        subtitle: Text(text(m, 'text')),
                      ),
                    if (canQueue)
                      OutlinedButton(
                        onPressed: () => _writeMessage(p['id'] as int),
                        child: const Text('Новое сообщение'),
                      ),
                  ]),
                if (_tab == _ProjectTab.work && canManage && allowed)
                  TextButton(
                    onPressed: () => _askPost(
                      'Архивировать объект',
                      'commissioning/${p['id']}/archive/',
                      {'reason': 'Причина архивации'},
                    ),
                    child: const Text('Архивировать объект'),
                  ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _AssigneePicker extends StatefulWidget {
  const _AssigneePicker({
    required this.lift,
    required this.assigned,
    required this.load,
  });

  final String lift;
  final Set<Object?> assigned;
  final Future<List<Json>> Function() load;

  @override
  State<_AssigneePicker> createState() => _AssigneePickerState();
}

class _AssigneePickerState extends State<_AssigneePicker> {
  late Future<List<Json>> _members;
  String _search = '';

  @override
  void initState() {
    super.initState();
    _members = widget.load();
  }

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
    child: SafeArea(
      top: false,
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * 0.45,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Исполнитель · ${widget.lift}',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              TextField(
                onChanged: (value) =>
                    setState(() => _search = value.trim().toLowerCase()),
                decoration: const InputDecoration(
                  labelText: 'Поиск по имени',
                  prefixIcon: Icon(Icons.search),
                ),
              ),
              Expanded(
                child: FutureBuilder<List<Json>>(
                  future: _members,
                  builder: (context, state) {
                    if (state.connectionState != ConnectionState.done) {
                      return const Center(child: CircularProgressIndicator());
                    }
                    if (state.hasError) {
                      return ListView(
                        children: [
                          ListTile(
                            title: const Text(
                              'Не удалось загрузить сотрудников',
                            ),
                            subtitle: Text('${state.error}'),
                          ),
                          TextButton(
                            onPressed: () =>
                                setState(() => _members = widget.load()),
                            child: const Text('Повторить'),
                          ),
                        ],
                      );
                    }
                    final candidates = state.requireData
                        .where(
                          (member) =>
                              member['can_commissioning'] != true ||
                              !widget.assigned.contains(member['user']),
                        )
                        .toList();
                    final matches = candidates
                        .where(
                          (member) => text(
                            member,
                            'name',
                          ).toLowerCase().contains(_search),
                        )
                        .toList();
                    if (matches.isEmpty) {
                      return ListView(
                        children: [
                          ListTile(
                            title: Text(
                              candidates.isEmpty
                                  ? 'Нет свободных для назначения сотрудников'
                                  : 'По этому имени никто не найден',
                            ),
                            subtitle: candidates.isEmpty
                                ? const Text(
                                    'Проверьте, что у сотрудника есть активная учётная запись в этой организации.',
                                  )
                                : null,
                          ),
                        ],
                      );
                    }
                    return ListView.builder(
                      itemCount: matches.length,
                      itemBuilder: (context, index) {
                        final member = matches[index];
                        final label = member['role'] == 'ADJUSTER'
                            ? 'Внешний наладчик'
                            : member['can_commissioning'] == true
                            ? 'Механик и наладчик'
                            : 'Механик · требуется роль «Наладчик»';
                        return ListTile(
                          title: Text(text(member, 'name')),
                          subtitle: Text(label),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: () => Navigator.pop(context, member),
                        );
                      },
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}
