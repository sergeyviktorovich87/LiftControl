import 'nameplates.dart';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';
import 'sync_queue.dart';
import 'media_widgets.dart';
import 'chat.dart';

class CommissioningPage extends StatefulWidget {
  const CommissioningPage({
    super.key,
    required this.controller,
    this.initialProject,
    this.embedded = false,
  });
  final LiftController controller;
  final int? initialProject;
  final bool embedded;
  @override
  State<CommissioningPage> createState() => _CommissioningPageState();
}

enum _ProjectTab {
  lifts('Лифты'),
  work('Работы'),
  expenses('Расходы'),
  nameplates('Шильдики');

  const _ProjectTab(this.label);
  final String label;
}

class _CommissioningPageState extends State<CommissioningPage> {
  List<Json> _projects = [];
  Json? _detail;
  int? _selectedLiftId;
  bool _unassignedOnly = false;
  bool _busy = false;
  String _error = '';
  LiftController get c => widget.controller;
  late final int org;
  var _tab = _ProjectTab.lifts;
  bool get canManage => c.me['can_manage_access'] == true;
  int? _readGeneration;
  int _loadSerial = 0;
  bool _backgroundLoading = false;

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
        _backgroundLoading ||
        _readGeneration == c.syncRevision) {
      return;
    }
    _readGeneration = c.syncRevision;
    unawaited(_load(quiet: true));
  }

  Future<void> _load({int? initialProject, bool quiet = false}) async {
    if (!mounted || c.organization != org) return;
    final serial = ++_loadSerial;
    final selected = initialProject ?? _detail?['id'];
    if (quiet) {
      _backgroundLoading = true;
    } else {
      setState(() {
        _busy = true;
        _error = '';
      });
    }
    try {
      final rows = records(
        await c.resource('commissioning/', expectedOrganization: org),
      );
      final data = selected == null
          ? null
          : await c.resource(
              'commissioning/$selected/',
              expectedOrganization: org,
            );
      if (!mounted || serial != _loadSerial || c.organization != org) return;
      setState(() {
        _projects = rows;
        if (!quiet || _detail?['id'] == selected) {
          _detail = data is Map ? Map<String, dynamic>.from(data) : null;
        }
      });
    } catch (error) {
      c.log.record('commissioning_load_failed');
      if (!quiet && mounted && serial == _loadSerial) {
        setState(
          () => _error = error is ApiError
              ? error.message
              : 'Не удалось загрузить наладку.',
        );
      }
    } finally {
      if (quiet) {
        _backgroundLoading = false;
      } else if (mounted && serial == _loadSerial) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _open(int id) async {
    ++_loadSerial;
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
          _selectedLiftId = null;
          _unassignedOnly = false;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _post(
    String path,
    Json body, {
    List<XFile> photos = const [],
  }) async {
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
      if (photos.isEmpty) {
        await c.request(
          path,
          method: 'POST',
          data: body,
          expectedOrganization: org,
        );
      } else {
        for (final photo in photos) {
          final size = await photo.length();
          if (size > maxFileBytes) {
            throw const ApiError('Размер фотографии должен быть до 100 МБ.');
          }
        }
        await c.postCommissioningPhotos(
          path,
          body.map((key, value) => MapEntry(key, '$value')),
          [
            for (final photo in photos)
              (bytes: await photo.readAsBytes(), name: photo.name),
          ],
          expectedOrganization: org,
        );
      }
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

  Widget _photoPicker(
    BuildContext context,
    List<XFile> photos,
    StateSetter update,
  ) {
    return Wrap(
      spacing: 8,
      children: [
        TextButton.icon(
          onPressed: c.canWrite
              ? () async {
                  try {
                    final selected = await ImagePicker().pickMultiImage(
                      limit: 5,
                      maxWidth: 1920,
                      maxHeight: 1920,
                      imageQuality: 82,
                    );
                    if (selected.isNotEmpty && context.mounted) {
                      update(
                        () => photos
                          ..clear()
                          ..addAll(selected),
                      );
                    }
                  } catch (error) {
                    if (context.mounted) showError(context, error);
                  }
                }
              : null,
          icon: const Icon(Icons.photo_library_outlined),
          label: Text(
            photos.isEmpty ? 'Прикрепить фото' : 'Фото: ${photos.length}',
          ),
        ),
        if (photos.isNotEmpty)
          TextButton(
            onPressed: () => update(photos.clear),
            child: const Text('Убрать фото'),
          ),
      ],
    );
  }

  Widget _withPhotos(String description, dynamic value) {
    final photos = records(value ?? []);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (description.isNotEmpty) Text(description),
        for (final photo in photos)
          PrivateMedia(
            key: ValueKey(photo['url']),
            controller: c,
            organization: org,
            attachment: photo,
          ),
      ],
    );
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
    final assigned = records(
      lift['assignees'] ?? [],
    ).map((row) => row['user']).toSet();
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
    final photos = <XFile>[];
    final result = await showDialog<Json>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, update) => AlertDialog(
          title: Text('Готовность: ${lift['label']}'),
          content: SingleChildScrollView(
            child: Column(
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
                _photoPicker(ctx, photos, update),
              ],
            ),
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
      if (photos.isEmpty && c.canRecordCommissioning) {
        await _queue(project, 'progress', {...result, 'lift': lift['id']});
      } else {
        await _post(
          'commissioning/$project/lifts/${lift['id']}/progress/',
          result,
          photos: photos,
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
      if (receipt != null && await receipt.length() > maxFileBytes) {
        throw const ApiError('Фото чека больше 100 МБ.');
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

  Future<void> _askPost(
    String title,
    String path,
    Map<String, String> fields,
  ) async {
    final body = await _form(title, fields);
    if (body != null) await _post(path, body);
  }

  Widget _section(String title, List<Widget> children) => Card(
    margin: const EdgeInsets.only(bottom: 12),
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

  static final _entrancePrefix = RegExp(
    r'^(?:подъезд|подезд|поезд)\s*№?\s*(\d+)(?=$|\s|[(·,:—-])\s*',
    caseSensitive: false,
  );

  ({String entrance, String title}) _liftLocation(Json lift) {
    final label = text(lift, 'label', '').trim();
    final match = _entrancePrefix.firstMatch(label);
    if (match == null) {
      return (entrance: text(lift, 'entrance', '').trim(), title: label);
    }
    final title = label
        .substring(match.end)
        .replaceAll(RegExp(r'^[\s(·,:—-]+|[\s)]+$'), '');
    return (
      entrance: match.group(1)!,
      title: title.isEmpty
          ? label
          : '${title[0].toUpperCase()}${title.substring(1)}',
    );
  }

  List<Json> _assignees(Json lift) => records(lift['assignees'] ?? []);

  void _goBack() => setState(() {
    if (_selectedLiftId != null) {
      _selectedLiftId = null;
    } else {
      _detail = null;
      _tab = _ProjectTab.lifts;
      _unassignedOnly = false;
    }
  });

  String _liftCount(int count) {
    final last = count % 10;
    final suffix = count % 100 >= 11 && count % 100 <= 14
        ? 'лифтов'
        : switch (last) {
            1 => 'лифт',
            2 || 3 || 4 => 'лифта',
            _ => 'лифтов',
          };
    return '$count $suffix';
  }

  Widget _projectCard(Json project) {
    final progress = (project['progress'] as num).toDouble();
    final unassigned = project['unassigned_count'] as int?;
    final address = text(project, 'address', '').trim();
    return Card(
      child: ListTile(
        title: Text(text(project, 'name')),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (address.isNotEmpty && address.toLowerCase() != 'нет адреса')
              Text(address),
            Text(_liftCount(project['lift_count'] as int)),
            const SizedBox(height: 6),
            LinearProgressIndicator(value: progress / 100),
            if (unassigned != null && unassigned > 0)
              Text('$unassigned без исполнителя'),
            if (project['archived'] == true) const Text('Архив'),
          ],
        ),
        trailing: Text('${project['progress']}% ›'),
        onTap: _busy ? null : () => _open(project['id'] as int),
      ),
    );
  }

  List<Widget> _liftGroups(List<Json> lifts, {required bool canAssign}) {
    final unassigned = lifts.where((lift) => _assignees(lift).isEmpty).length;
    final groups = <String, List<Json>>{};
    for (final lift in lifts) {
      if (_unassignedOnly && _assignees(lift).isNotEmpty) continue;
      groups.putIfAbsent(_liftLocation(lift).entrance, () => []).add(lift);
    }
    final entrances = groups.keys.toList()
      ..sort((a, b) {
        if (a.isEmpty) return 1;
        if (b.isEmpty) return -1;
        final left = int.tryParse(a), right = int.tryParse(b);
        return left != null && right != null
            ? left.compareTo(right)
            : a.compareTo(b);
      });
    return [
      if (canManage && lifts.isNotEmpty)
        Wrap(
          spacing: 8,
          children: [
            ChoiceChip(
              label: const Text('Все лифты'),
              selected: !_unassignedOnly,
              onSelected: (_) => setState(() => _unassignedOnly = false),
            ),
            ChoiceChip(
              label: Text('Без исполнителя · $unassigned'),
              selected: _unassignedOnly,
              onSelected: (_) => setState(() => _unassignedOnly = true),
            ),
          ],
        ),
      if (lifts.isEmpty)
        const EmptyState('Лифтов пока нет', 'Они появятся после добавления.')
      else if (groups.isEmpty)
        const Text('На все лифты назначены исполнители.'),
      for (final entrance in entrances)
        _section(entrance.isEmpty ? 'Подъезд не указан' : 'Подъезд $entrance', [
          for (final lift in groups[entrance]!)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(_liftLocation(lift).title),
              subtitle: _assignees(lift).isEmpty
                  ? null
                  : Text(
                      _assignees(
                        lift,
                      ).map((member) => text(member, 'name')).join(', '),
                    ),
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('${lift['progress']}%'),
                  if (canManage &&
                      _detail?['archived'] != true &&
                      _assignees(lift).isEmpty)
                    TextButton(
                      onPressed: canAssign ? () => _assign(lift) : null,
                      child: const Text('Назначить'),
                    )
                  else
                    const Icon(Icons.chevron_right),
                ],
              ),
              onTap: () => setState(() => _selectedLiftId = lift['id'] as int),
            ),
        ]),
    ];
  }

  void _openNameplates(Json lift) {
    Navigator.push(
      context,
      MaterialPageRoute<void>(
        builder: (_) => NameplatesPage(
          controller: c,
          project: _detail!['id'] as int,
          lift: lift,
          organization: org,
          archived: _detail?['archived'] == true,
        ),
      ),
    );
  }

  List<Widget> _liftDetails(
    Json lift, {
    required bool canQueue,
    required bool canAssign,
  }) {
    final location = _liftLocation(lift);
    final assignees = _assignees(
      lift,
    ).map((member) => text(member, 'name')).join(', ');
    final history = records(lift['history'] ?? []);
    final factory = text(lift, 'factory_number', '');
    final progress = (lift['progress'] as num).toDouble();
    return [
      Text(location.title, style: Theme.of(context).textTheme.headlineSmall),
      if (location.entrance.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 4, bottom: 12),
          child: Text(
            lift['entrance_kind'] == 'LIFT'
                ? 'Лифт №${location.entrance}'
                : 'Подъезд ${location.entrance}',
            style: Theme.of(context).textTheme.titleLarge,
          ),
        ),
      if (lift['can_view_nameplates'] == true)
        OutlinedButton.icon(
          onPressed: () => _openNameplates(lift),
          icon: const Icon(Icons.badge_outlined),
          label: const Text('Шильдики'),
        ),
      _section('Готовность наладки', [
        Text(
          '${lift['progress']}%',
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        LinearProgressIndicator(value: progress / 100),
        if (factory.isNotEmpty) Text('Заводской номер: $factory'),
      ]),
      _section('Исполнитель', [
        Text(assignees.isEmpty ? 'Не назначен' : assignees),
        if (canManage && _detail?['archived'] != true)
          TextButton(
            onPressed: canAssign ? () => _assign(lift) : null,
            child: Text(
              assignees.isEmpty ? 'Назначить' : 'Добавить исполнителя',
            ),
          ),
      ]),
      Card(
        margin: const EdgeInsets.only(bottom: 12),
        child: ExpansionTile(
          title: const Text('История работ'),
          children: [
            if (history.isEmpty)
              const ListTile(title: Text('Записей пока нет.')),
            for (final entry in history)
              ListTile(
                dense: true,
                title: Text(
                  '${entry['before']}% → ${entry['after']}% · ${entry['author']}',
                ),
                subtitle: _withPhotos(
                  text(entry, 'description', ''),
                  entry['photos'],
                ),
              ),
          ],
        ),
      ),
      if (lift['can_edit'] == true && _detail?['archived'] != true)
        FilledButton(
          onPressed: canQueue ? () => _progress(lift) : null,
          child: const Text('Записать работу'),
        ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final p = _detail;
    final lifts = records(p?['lifts'] ?? []);
    final selectedLift = lifts
        .where((lift) => lift['id'] == _selectedLiftId)
        .firstOrNull;
    final allowed = c.canWrite && !_busy && p?['archived'] != true;
    final canQueue =
        !_busy &&
        p?['archived'] != true &&
        (c.canRecordCommissioning || c.canWrite);
    final content = PopScope(
      canPop: p == null || _busy,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop && !_busy && p != null) _goBack();
      },
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 4),
            child: Row(
              children: [
                if (p != null)
                  IconButton(
                    onPressed: _busy ? null : _goBack,
                    icon: const Icon(Icons.arrow_back),
                    tooltip: selectedLift != null
                        ? 'К лифтам объекта'
                        : 'Все объекты',
                  )
                else if (!widget.embedded)
                  const BackButton(),
                Expanded(
                  child: Text(
                    selectedLift != null
                        ? text(p!, 'name')
                        : (p == null ? 'Наладка' : 'Объекты'),
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
                if (c.me['notification_counts_api'] == 1)
                  ListenableBuilder(
                    listenable: c,
                    builder: (context, _) => IconButton(
                      tooltip: 'Чат наладчиков',
                      icon: unreadBadge(
                        c.unreadNotifications('commissioning_chat'),
                        child: const Icon(Icons.chat_bubble_outline),
                      ),
                      onPressed: () => Navigator.push(
                        context,
                        MaterialPageRoute<void>(
                          builder: (_) =>
                              ChatPage(controller: c, commissioning: true),
                        ),
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
          if (_busy) const LinearProgressIndicator(),
          Expanded(
            child: ListView(
              key: PageStorageKey((p?['id'], selectedLift?['id'], _tab)),
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
              children: [
                if (p == null) ...[
                  Text(
                    'Объекты',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  for (final project in _projects) _projectCard(project),
                  if (_projects.isEmpty)
                    const Padding(
                      padding: EdgeInsets.all(24),
                      child: Text('Объектов пока нет.'),
                    ),
                  if (canManage)
                    FilledButton.icon(
                      onPressed: c.canWrite && !_busy ? _createProject : null,
                      icon: const Icon(Icons.add),
                      label: const Text('Добавить объект'),
                    ),
                ] else if (selectedLift != null) ...[
                  ..._liftDetails(
                    selectedLift,
                    canQueue: canQueue,
                    canAssign: allowed,
                  ),
                ] else ...[
                  Text(
                    text(p, 'name'),
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  _section(_liftCount(p['lift_count'] as int), [
                    Text('Готовность ${p['progress']}%'),
                    LinearProgressIndicator(
                      value: (p['progress'] as num).toDouble() / 100,
                    ),
                    if (p['archived'] == true)
                      const Text('Архив · только просмотр'),
                  ]),
                  Wrap(
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
                  if (_tab == _ProjectTab.nameplates) ...[
                    for (final lift in lifts.where(
                      (row) => row['can_view_nameplates'] == true,
                    ))
                      Card(
                        child: ListTile(
                          leading: const Icon(Icons.badge_outlined),
                          title: Text(text(lift, 'label')),
                          subtitle: const Text(
                            'Шильдики устройств безопасности',
                          ),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: () => _openNameplates(lift),
                        ),
                      ),
                    if (!lifts.any((row) => row['can_view_nameplates'] == true))
                      const Padding(
                        padding: EdgeInsets.all(16),
                        child: Text('Нет доступных лифтов.'),
                      ),
                  ],
                  if (_tab == _ProjectTab.lifts) ...[
                    ..._liftGroups(lifts, canAssign: allowed),
                    if (canManage && p['archived'] != true)
                      TextButton.icon(
                        onPressed: allowed ? _addLift : null,
                        icon: const Icon(Icons.add),
                        label: const Text('Добавить лифт'),
                      ),
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
                              canManage &&
                                  allowed &&
                                  extra['status'] == 'PENDING'
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
      ),
    );
    if (widget.embedded) return SafeArea(top: false, child: content);
    return ScopePage(
      controller: c,
      organization: org,
      builder: (_) => Scaffold(body: SafeArea(child: content)),
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
                            onPressed: () {
                              final request = widget.load();
                              setState(() {
                                _members = request;
                              });
                            },
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
