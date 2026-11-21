import 'package:flutter/material.dart';
import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';
import 'tickets.dart';
import 'platform_bridge.dart';

const maintenanceNames = {
  'TO1': 'ТО-1',
  'TO2': 'ТО-2',
  'REPAIR': 'Ремонт',
  'INSPECTION': 'Осмотр',
};

class ElevatorMaintenanceJournal extends StatefulWidget {
  const ElevatorMaintenanceJournal({
    super.key,
    required this.controller,
    required this.elevatorId,
    required this.organization,
  });

  final LiftController controller;
  final int elevatorId, organization;

  @override
  State<ElevatorMaintenanceJournal> createState() =>
      _ElevatorMaintenanceJournalState();
}

class _ElevatorMaintenanceJournalState extends State<ElevatorMaintenanceJournal> {
  DateTime? _from, _to;
  late Future<List<Json>> _rows;
  bool _exporting = false;
  LiftController get c => widget.controller;
  String get _base => 'maintenance/${widget.elevatorId}/journal/';
  bool get _valid => _from == null || _to == null || !_to!.isBefore(_from!);
  String get _query {
    final dates = {
      if (_from != null) 'from': _isoDate(_from!),
      if (_to != null) 'to': _isoDate(_to!),
    };
    return dates.isEmpty ? '' : '?${Uri(queryParameters: dates).query}';
  }

  static String _isoDate(DateTime value) => value.toIso8601String().substring(0, 10);

  @override
  void initState() {
    super.initState();
    _rows = _load();
  }

  Future<List<Json>> _load() async {
    if (c.demo || !_valid) return [];
    try {
      final result = await c.request(
        '$_base$_query',
        expectedOrganization: widget.organization,
      );
      return records(result['rows']);
    } catch (_) {
      c.log.record('maintenance_journal_failed');
      rethrow;
    }
  }

  Future<void> _pickDate({required bool start}) async {
    final first = DateTime(1900);
    final last = DateTime(2100, 12, 31);
    final current = start ? _from : _to;
    final selected = await showDatePicker(
      context: context,
      firstDate: first,
      lastDate: last,
      initialDate: current ?? DateUtils.dateOnly(c.orgNow),
      helpText: start ? 'Дата начала' : 'Дата окончания',
    );
    if (selected == null || !mounted) return;
    setState(() {
      if (start) {
        _from = selected;
      } else {
        _to = selected;
      }
      _rows = _load();
    });
  }

  Future<void> _openPdf() async {
    setState(() => _exporting = true);
    try {
      final bytes = await c.download(
        '${_base}pdf/$_query',
        widget.organization,
        pdf: true,
      );
      if (!mounted) return;
      await PlatformBridge.openPdf(bytes);
      c.log.record('maintenance_pdf_opened');
    } catch (error) {
      c.log.record('maintenance_pdf_failed');
      if (mounted) showError(context, error);
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  void _openSource(Json row) {
    final id = row['source_id'] as int;
    if (row['source'] == 'ticket') {
      openTicket(context, c, id);
      return;
    }
    final items = c.list('maintenance').where((item) => item['id'] == id);
    if (items.isEmpty) return;
    Navigator.push<void>(
      context,
      MaterialPageRoute<void>(
        builder: (_) => MaintenanceForm(controller: c, item: items.first),
      ),
    ).then((_) {
      if (mounted) setState(() => _rows = _load());
    });
  }

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(18),
    children: [
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          OutlinedButton(
            onPressed: () => _pickDate(start: true),
            child: Text(_from == null ? 'С даты' : 'С ${_isoDate(_from!)}'),
          ),
          OutlinedButton(
            onPressed: () => _pickDate(start: false),
            child: Text(_to == null ? 'По дату' : 'По ${_isoDate(_to!)}'),
          ),
          if (_from != null || _to != null)
            TextButton(
              onPressed: () => setState(() {
                _from = _to = null;
                _rows = _load();
              }),
              child: const Text('Сбросить даты'),
            ),
        ],
      ),
      const SizedBox(height: 12),
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          FilledButton.icon(
            onPressed: !c.demo && _valid && !_exporting ? _openPdf : null,
            icon: const Icon(Icons.picture_as_pdf_outlined),
            label: Text(_exporting ? 'Формирование…' : 'PDF для печати'),
          ),
          IconButton(
            tooltip: 'Обновить журнал',
            onPressed: _valid ? () => setState(() => _rows = _load()) : null,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      const SizedBox(height: 16),
      if (!_valid)
        const Text('Дата окончания раньше даты начала.')
      else
        FutureBuilder<List<Json>>(
          future: _rows,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              final error = snapshot.error;
              return Text(error is ApiError ? error.message : 'Не удалось загрузить журнал.');
            }
            final rows = snapshot.data ?? [];
            if (rows.isEmpty) {
              return const EmptyState(
                'За выбранный период выполненных работ нет',
                'Здесь появятся выполненные ТО и закрытые заявки.',
              );
            }
            return Column(
              children: [
                for (final (index, row) in rows.indexed)
                  Card(
                    child: ListTile(
                      title: Text(text(row, 'description')),
                      subtitle: Text(
                        '${text(row, 'date').split('-').reversed.join('.')} · ${text(row, 'performer')}',
                      ),
                      leading: Text('${index + 1}'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => _openSource(row),
                    ),
                  ),
              ],
            );
          },
        ),
    ],
  );
}

class MaintenanceTile extends StatelessWidget {
  const MaintenanceTile({
    super.key,
    required this.controller,
    required this.item,
  });
  final LiftController controller;
  final Json item;
  @override
  Widget build(BuildContext context) {
    final completed = item['completed_at'] != null;
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.all(16),
        leading: Icon(
          completed ? Icons.task_alt : Icons.build_outlined,
          color: completed ? green : Theme.of(context).colorScheme.primary,
        ),
        title: Text(
          '${maintenanceNames[item['kind']] ?? item['kind']} · ${dateLabel(item['planned_date'], 0, time: false)}',
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 7),
          child: Text(
            '${text(item, 'address')}\nЛифт ${text(item, 'elevator_label')} · ${completed ? 'Выполнено' : 'Запланировано'}',
          ),
        ),
        isThreeLine: true,
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute<void>(
            builder: (_) => MaintenanceForm(controller: controller, item: item),
          ),
        ),
      ),
    );
  }
}

class MaintenanceForm extends StatefulWidget {
  const MaintenanceForm({
    super.key,
    required this.controller,
    this.item,
    this.elevator,
  });
  final LiftController controller;
  final Json? item, elevator;
  @override
  State<MaintenanceForm> createState() => _MaintenanceFormState();
}

class _MaintenanceFormState extends State<MaintenanceForm> {
  final _form = GlobalKey<FormState>();
  late final TextEditingController _notes;
  late int _org;
  int? _technician;
  Json? _elevator;
  String _kind = 'TO1';
  late DateTime _date;
  bool _completed = false, _busy = false;
  bool get editable =>
      widget.item == null ||
      widget.controller.me['can_manage'] == true ||
      widget.item!['technician'] == widget.controller.me['technician'];
  @override
  void initState() {
    super.initState();
    _org = widget.controller.organization!;
    _elevator = widget.elevator;
    _technician = (widget.item?['technician'] ?? _elevator?['assigned_technician']) as int?;
    _notes = TextEditingController(text: widget.item?['notes'] ?? '');
    _kind = widget.item?['kind'] ?? 'TO1';
    _date =
        DateTime.tryParse('${widget.item?['planned_date']}') ??
        widget.controller.orgNow;
    _completed = widget.item?['completed_at'] != null;
  }

  @override
  void dispose() {
    _notes.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_busy || !_form.currentState!.validate()) return;
    if (widget.item == null && _elevator == null) {
      showError(context, const ApiError('Выберите лифт.'));
      return;
    }
    setState(() => _busy = true);
    final c = widget.controller;
    try {
      final data = <String, dynamic>{
        'notes': _notes.text.trim(),
        'completed_at': _completed
            ? (widget.item?['completed_at'] ??
                  DateTime.now().toUtc().toIso8601String())
            : null,
      };
      if (widget.item == null) {
        data.addAll({
          'elevator': _elevator!['id'],
          'kind': _kind,
          'planned_date': _date.toIso8601String().substring(0, 10),
        });
      }
      if (c.me['can_manage'] == true && widget.item?['completed_at'] == null) {
        data['technician'] = _technician;
      }
      await c.request(
        widget.item == null
            ? 'maintenance/'
            : 'maintenance/${widget.item!['id']}/',
        method: widget.item == null ? 'POST' : 'PATCH',
        data: data,
        expectedOrganization: _org,
      );
      await c.refresh();
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: widget.controller,
    organization: _org,
    builder: (context) => Scaffold(
      appBar: AppBar(
        title: Text(
          widget.item == null
              ? 'Запланировать работу по ТО'
              : 'Работа ${maintenanceNames[_kind] ?? _kind}',
        ),
      ),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.all(18),
          children: [
            Sheet(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (widget.item != null)
                    Text(
                      '${text(widget.item!, 'address')} · ${text(widget.item!, 'elevator_label')}',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  if (widget.item == null) ...[
                    OutlinedButton.icon(
                      onPressed: _busy
                          ? null
                          : () async {
                              final e = await pickElevator(
                                context,
                                widget.controller,
                              );
                              if (e != null && mounted) {
                                setState(() => _elevator = e);
                              }
                            },
                      icon: const Icon(Icons.elevator_outlined),
                      label: Text(
                        _elevator == null
                            ? 'Выбрать лифт'
                            : '${text(_elevator!, 'address')} · ${liftLabel(_elevator!)}',
                      ),
                    ),
                    const SizedBox(height: 14),
                    DropdownButtonFormField<String>(
                      initialValue: _kind,
                      decoration: const InputDecoration(
                        labelText: 'Вид работы',
                      ),
                      items: maintenanceNames.entries
                          .map(
                            (e) => DropdownMenuItem(
                              value: e.key,
                              child: Text(e.value),
                            ),
                          )
                          .toList(),
                      onChanged: _busy
                          ? null
                          : (v) => setState(() => _kind = v!),
                    ),
                    const SizedBox(height: 12),
                    OutlinedButton(
                      onPressed: _busy
                          ? null
                          : () async {
                              final d = await showDatePicker(
                                context: context,
                                initialDate: _date,
                                firstDate: DateTime(2020),
                                lastDate: DateTime(2040),
                              );
                              if (d != null) setState(() => _date = d);
                            },
                      child: Text(
                        'Дата: ${dateLabel(_date.toIso8601String().substring(0, 10), 0, time: false)} ${_date.year}',
                      ),
                    ),
                  ],
                  if (widget.controller.me['can_manage'] == true &&
                      widget.item?['completed_at'] == null) ...[
                    const SizedBox(height: 14),
                    DropdownButtonFormField<int>(
                      initialValue: _technician ?? 0,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: 'Исполнитель'),
                      items: [
                        const DropdownMenuItem<int>(
                          value: 0,
                          child: Text('Не назначен'),
                        ),
                        for (final person in widget.controller.list('technicians'))
                          if (person['active'] == true || person['id'] == _technician)
                            DropdownMenuItem<int>(
                              value: person['id'] as int,
                              child: Text(text(person, 'full_name')),
                            ),
                        if (_technician != null && !widget.controller
                            .list('technicians').any((p) => p['id'] == _technician))
                          DropdownMenuItem<int>(
                            value: _technician,
                            child: const Text('Текущий исполнитель'),
                          ),
                      ],
                      onChanged: _busy ? null : (value) {
                        setState(() => _technician = value == 0 ? null : value);
                      },
                    ),
                  ],
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _notes,
                    readOnly: !editable,
                    decoration: const InputDecoration(
                      labelText: 'Результат и замечания',
                    ),
                    maxLength: 4000,
                    minLines: 4,
                    maxLines: 10,
                    validator: (v) => _completed && (v?.trim().isEmpty ?? true)
                        ? 'Для выполненной работы нужен результат'
                        : null,
                  ),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Работа выполнена'),
                    value: _completed,
                    onChanged: editable && !_busy
                        ? (v) => setState(() => _completed = v)
                        : null,
                  ),
                  if (!editable)
                    const Text(
                      'Изменить запись может её исполнитель или руководитель.',
                    ),
                ],
              ),
            ),
            const SizedBox(height: 18),
            if (editable)
              FilledButton(
                onPressed: widget.controller.canWrite && !_busy ? _save : null,
                child: Text(_busy ? 'Сохранение…' : 'Сохранить работу'),
              ),
          ],
        ),
      ),
    ),
  );
}
