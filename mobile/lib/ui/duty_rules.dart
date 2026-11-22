import 'dart:async';

import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';

String dutyDate(DateTime date) => date.toIso8601String().substring(0, 10);

Iterable<Json> dutyMechanics(LiftController controller) => controller
    .list('technicians')
    .where((row) => row['active'] == true && row['role'] == 'MECHANIC');

const _labels = {
  'cycle': 'Очередь сотрудников',
  'temp': 'Временная очередь',
  'leave': 'Отпуск',
  'replace': 'Подмена на период',
};

class DutyRosterSettings extends StatefulWidget {
  const DutyRosterSettings({
    super.key,
    required this.controller,
    required this.organization,
  });
  final LiftController controller;
  final int organization;

  @override
  State<DutyRosterSettings> createState() => _DutyRosterSettingsState();
}

class _DutyRosterSettingsState extends State<DutyRosterSettings> {
  Json? _config;
  String? _error;
  bool _busy = false;
  LiftController get _controller => widget.controller;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _error = null;
      _busy = true;
    });
    try {
      final response = await _controller.request(
        'duty/roster-settings/',
        expectedOrganization: widget.organization,
      );
      if (mounted) {
        setState(() => _config = Map<String, dynamic>.from(response as Map));
      }
    } catch (error) {
      _controller.log.record('duty_roster_settings_load_failed');
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _edit(
    String type, {
    int? index,
    Json? rule,
    bool remove = false,
  }) async {
    final config = _config;
    if (config == null) return;
    final now = _controller.orgNow;
    final tomorrow = DateTime(now.year, now.month, now.day + 1);
    final key = type == 'cycle' ? 'cycles' : 'periods';
    final rules = records(config[key]);
    if (remove) {
      rules.removeAt(index!);
    } else {
      final edit = await showDialog<Json>(
        context: context,
        builder: (_) => _RuleDialog(
          type: type,
          rule: rule,
          first: tomorrow,
          mechanics: dutyMechanics(_controller).toList(),
        ),
      );
      if (edit == null || !mounted) return;
      if (index == null) {
        rules.add(edit);
      } else {
        rules[index] = edit;
      }
    }
    setState(() {
      _error = null;
      _busy = true;
    });
    try {
      final response = await _controller.request(
        'duty/roster-settings/',
        method: 'PUT',
        expectedOrganization: widget.organization,
        data: {
          'previous': config,
          'config': {...config, key: rules},
        },
      );
      if (mounted) {
        setState(() => _config = Map<String, dynamic>.from(response as Map));
      }
      _controller.log.record('duty_roster_settings_saved');
    } catch (error) {
      _controller.log.record('duty_roster_settings_update_failed');
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: _controller,
    organization: widget.organization,
    builder: (context) {
      final config = _config;
      final today = dutyDate(_controller.orgNow);
      final disabled = _busy || !_controller.canWrite;
      final names = {
        for (final worker in dutyMechanics(_controller))
          worker['id']: text(worker, 'full_name'),
      };
      return Scaffold(
        appBar: AppBar(title: const Text('Настройки графика')),
        body: ListView(
          padding: const EdgeInsets.all(18),
          children: [
            if (_busy) const LinearProgressIndicator(),
            if (_error != null) ...[
              Text(_error!),
              TextButton(
                onPressed: _busy ? null : _load,
                child: const Text('Обновить'),
              ),
            ],
            if (config != null) ...[
              const Text(
                'Очередь и периоды применяются при публикации месяца.',
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final entry in _labels.entries)
                    OutlinedButton(
                      onPressed: disabled ? null : () => _edit(entry.key),
                      child: Text(entry.value),
                    ),
                ],
              ),
              for (final key in ['cycles', 'periods'])
                for (final (index, rule) in records(config[key]).indexed)
                  Card(
                    child: ListTile(
                      title: Text(_labels[rule['type'] ?? 'cycle']!),
                      subtitle: Text(
                        [
                          [
                            rule['from'],
                            if (rule['to'] != null) rule['to'],
                          ].join(' — '),
                          (rule['people'] as List? ??
                                  [
                                    rule['worker'],
                                    if (rule['target'] != null) rule['target'],
                                  ])
                              .map((id) => names[id] ?? 'Архивный сотрудник')
                              .join(' → '),
                        ].join('\n'),
                      ),
                      trailing: (rule['from'] as String).compareTo(today) <= 0
                          ? null
                          : PopupMenuButton<String>(
                              enabled: !disabled,
                              onSelected: (action) => _edit(
                                rule['type'] ?? 'cycle',
                                index: index,
                                rule: rule,
                                remove: action == 'remove',
                              ),
                              itemBuilder: (_) => const [
                                PopupMenuItem(
                                  value: 'edit',
                                  child: Text('Изменить'),
                                ),
                                PopupMenuItem(
                                  value: 'remove',
                                  child: Text('Убрать из плана'),
                                ),
                              ],
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

class _RuleDialog extends StatefulWidget {
  const _RuleDialog({
    required this.type,
    required this.first,
    required this.mechanics,
    required this.rule,
  });
  final String type;
  final DateTime first;
  final List<Json> mechanics;
  final Json? rule;

  @override
  State<_RuleDialog> createState() => _RuleDialogState();
}

class _RuleDialogState extends State<_RuleDialog> {
  late DateTime from, to;
  late List<int> order;
  int? employee, replacement;

  bool get cycle => widget.type == 'cycle';
  bool get rotation => cycle || widget.type == 'temp';
  bool get replace => widget.type == 'replace';

  @override
  void initState() {
    super.initState();
    final rule = widget.rule;
    from = DateTime.tryParse('${rule?['from']}') ?? widget.first;
    to = DateTime.tryParse('${rule?['to']}') ?? from;
    order =
        (rule?['people'] as List?)?.cast<int>().toList() ??
        widget.mechanics.map((worker) => worker['id'] as int).toList();
    employee = rule?['worker'] as int?;
    replacement = rule?['target'] as int?;
  }

  Future<void> _date(bool start) async {
    final initial = start ? from : to;
    final min = start ? widget.first : from;
    final picked = await showDatePicker(
      context: context,
      initialDate: initial.isBefore(min) ? min : initial,
      firstDate: min,
      lastDate: DateTime(9998),
    );
    if (picked == null || !mounted) return;
    setState(() {
      if (start) {
        from = picked;
        if (to.isBefore(from)) to = from;
      } else {
        to = picked;
      }
    });
  }

  Widget _choose(
    String label,
    int? value,
    void Function(int?) onChanged, {
    int? exclude,
  }) {
    final available = widget.mechanics.where(
      (worker) => worker['id'] != exclude,
    );
    return DropdownButton<int>(
      value: available.any((worker) => worker['id'] == value) ? value : null,
      hint: Text(label),
      isExpanded: true,
      onChanged: onChanged,
      items: [
        for (final worker in available)
          DropdownMenuItem(
            value: worker['id'] as int,
            child: Text(
              text(worker, 'full_name'),
              overflow: TextOverflow.ellipsis,
            ),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final names = {
      for (final worker in widget.mechanics)
        worker['id']: text(worker, 'full_name'),
    };
    final ready = rotation
        ? order.isNotEmpty
        : employee != null && (!replace || replacement != null);
    return AlertDialog(
      title: Text(_labels[widget.type]!),
      content: SizedBox(
        width: 440,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              OutlinedButton(
                onPressed: () => _date(true),
                child: Text('С ${dutyDate(from)}'),
              ),
              if (!cycle)
                OutlinedButton(
                  onPressed: () => _date(false),
                  child: Text('По ${dutyDate(to)} включительно'),
                ),
              if (rotation) ...[
                for (final (index, employee) in order.indexed)
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          '${index + 1}. ${names[employee] ?? 'Архивный сотрудник'}',
                        ),
                      ),
                      IconButton(
                        tooltip: 'Раньше',
                        icon: const Icon(Icons.arrow_upward),
                        onPressed: index == 0
                            ? null
                            : () {
                                setState(() {
                                  order.removeAt(index);
                                  order.insert(index - 1, employee);
                                });
                              },
                      ),
                      IconButton(
                        tooltip: 'Убрать из очереди',
                        icon: const Icon(Icons.close),
                        onPressed: () => setState(() => order.removeAt(index)),
                      ),
                    ],
                  ),
                DropdownButton<int>(
                  isExpanded: true,
                  hint: const Text('Добавить механика'),
                  items: [
                    for (final worker in widget.mechanics)
                      if (!order.contains(worker['id']))
                        DropdownMenuItem(
                          value: worker['id'] as int,
                          child: Text(text(worker, 'full_name')),
                        ),
                  ],
                  onChanged: (id) {
                    if (id != null) setState(() => order.add(id));
                  },
                ),
              ] else ...[
                _choose(
                  'Сотрудник',
                  employee,
                  (value) => setState(() {
                    employee = value;
                    if (replacement == employee) replacement = null;
                  }),
                ),
                if (replace)
                  _choose(
                    'Кто подменяет',
                    replacement,
                    (value) => setState(() => replacement = value),
                    exclude: employee,
                  ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Отмена'),
        ),
        FilledButton(
          onPressed: ready
              ? () => Navigator.pop(context, <String, dynamic>{
                  'from': dutyDate(from),
                  if (!cycle) ...{'type': widget.type, 'to': dutyDate(to)},
                  if (rotation) 'people': order else 'worker': employee,
                  if (replace) 'target': replacement,
                })
              : null,
          child: const Text('Сохранить'),
        ),
      ],
    );
  }
}
