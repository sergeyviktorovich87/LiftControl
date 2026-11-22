import 'dart:async';

import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';
import 'duty_rules.dart';

class DutyCard extends StatefulWidget {
  const DutyCard({super.key, required this.controller});
  final LiftController controller;
  @override
  State<DutyCard> createState() => _DutyCardState();
}

class _DutyCardState extends State<DutyCard> {
  bool _busy = false;
  @override
  Widget build(BuildContext context) {
    final c = widget.controller,
        shift = c.me['duty_shift'] is Map
            ? Map<String, dynamic>.from(c.me['duty_shift'])
            : <String, dynamic>{};
    final own = c.me['on_duty'] == true;
    return Sheet(
      color: forest,
      padding: 12,
      child: DefaultTextStyle(
        style: const TextStyle(color: Colors.white, fontSize: 14, height: 1.4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.shield_outlined, color: Color(0xFFC9E3D0)),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    own ? 'Вы на дежурстве' : 'Дежурный механик',
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              shift.isEmpty
                  ? 'Сейчас дежурный не назначен'
                  : text(shift, 'technician_name'),
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
            if (shift.isNotEmpty) ...[
              const SizedBox(height: 2),
              Text(
                '${dateLabel(shift['start'], c.utcOffset)} — ${dateLabel(shift['end'], c.utcOffset)}',
                style: const TextStyle(color: Color(0xFFC2D4CA)),
              ),
            ],
            if (own && shift['acknowledged_at'] == null) ...[
              const SizedBox(height: 14),
              FilledButton(
                onPressed: c.canWrite && !_busy
                    ? () async {
                        setState(() => _busy = true);
                        try {
                          await c.request(
                            'duty/${shift['id']}/acknowledge/',
                            method: 'POST',
                            data: {},
                            expectedOrganization: c.organization,
                          );
                          await c.refresh();
                        } catch (e) {
                          if (context.mounted) showError(context, e);
                        } finally {
                          if (mounted) setState(() => _busy = false);
                        }
                      }
                    : null,
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFFDCECDC),
                  foregroundColor: forest,
                ),
                child: Text(_busy ? 'Подтверждение…' : 'Принял смену'),
              ),
            ],
            if (own && shift['acknowledged_at'] != null)
              const Padding(
                padding: EdgeInsets.only(top: 10),
                child: Text(
                  '✓ Приём смены подтверждён',
                  style: TextStyle(color: Color(0xFFB7E3C6), fontSize: 12),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class DutyPage extends StatefulWidget {
  const DutyPage({super.key, required this.controller});
  final LiftController controller;
  @override
  State<DutyPage> createState() => _DutyPageState();
}

class _DutyPageState extends State<DutyPage> {
  bool _busy = false;

  Future<void> _resolve(Json swap, bool accept) async {
    setState(() => _busy = true);
    try {
      await widget.controller.request(
        'duty-swaps/${swap['id']}/${accept ? 'accept' : 'cancel'}/',
        method: 'POST',
        data: {},
        expectedOrganization: widget.controller.organization,
      );
      await _refresh();
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _swap(Json shift) async {
    final c = widget.controller, org = c.organization!;
    final target = await showModalBottomSheet<int>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 20),
              child: SectionTitle('Кто подменит?'),
            ),
            for (final t
                in c
                    .list('technicians')
                    .where(
                      (t) =>
                          t['active'] == true && t['id'] != shift['technician'],
                    ))
              ListTile(
                leading: const Icon(Icons.person_outline),
                title: Text(text(t, 'full_name')),
                onTap: () => Navigator.pop(context, t['id'] as int),
              ),
          ],
        ),
      ),
    );
    if (target == null || !mounted) return;
    final reason = await askText(
      context,
      title: 'Запросить подмену',
      label: 'Причина',
      minimum: 5,
      maximum: 1000,
      action: 'Отправить запрос',
    );
    if (reason == null) return;
    setState(() => _busy = true);
    try {
      await c.request(
        'duty/${shift['id']}/swap/',
        method: 'POST',
        data: {'technician': target, 'reason': reason},
        expectedOrganization: org,
      );
      await _refresh();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Запрос отправлен. Смена перейдёт после подтверждения сменщика.',
            ),
          ),
        );
      }
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _editDay(Json day, [Json? shift]) async {
    final c = widget.controller;
    final organization = c.organization;
    if (organization == null) return;
    final unavailable = (day['unavailable'] as List?) ?? [];
    final selected = await showDialog<int>(
      context: context,
      builder: (context) {
        int? selected =
            shift?['technician'] as int? ?? day['suggested'] as int?;
        return StatefulBuilder(
          builder: (context, update) => AlertDialog(
            title: Text('Кто дежурит ${_label(DateTime.parse(day['date']))}?'),
            content: SizedBox(
              width: 380,
              child: SingleChildScrollView(
                child: RadioGroup<int>(
                  groupValue: selected,
                  onChanged: (value) => update(() => selected = value),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      for (final technician in dutyMechanics(c))
                        RadioListTile<int>(
                          contentPadding: EdgeInsets.zero,
                          value: technician['id'] as int,
                          enabled: !unavailable.contains(technician['id']),
                          title: Text(text(technician, 'full_name')),
                          subtitle: unavailable.contains(technician['id'])
                              ? const Text('В отпуске')
                              : null,
                        ),
                    ],
                  ),
                ),
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Отмена'),
              ),
              FilledButton(
                onPressed:
                    selected == null ||
                        selected == shift?['technician'] ||
                        unavailable.contains(selected)
                    ? null
                    : () => Navigator.pop(context, selected),
                child: const Text('Сохранить'),
              ),
            ],
          ),
        );
      },
    );
    if (selected == null || !mounted) return;
    setState(() => _busy = true);
    try {
      await c.request(
        shift == null ? 'duty/' : 'duty/${shift['id']}/',
        method: shift == null ? 'POST' : 'PATCH',
        data: {
          'technician': selected,
          if (shift == null) ...{
            'start': day['start'],
            'end': day['end'],
            'kind': 'daily',
          },
        },
        expectedOrganization: organization,
      );
      c.log.record('duty_roster_assignment_saved');
      await _refresh();
      if (mounted) {
        _notice(shift == null ? 'Дежурный назначен' : 'Дежурный изменён');
      }
    } catch (error) {
      c.log.record('duty_roster_assignment_failed');
      if (mounted) showError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _notice(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  bool _future(Object? value) =>
      DateTime.tryParse('$value')?.isAfter(DateTime.now().toUtc()) == true;

  bool _canEdit(Json shift) =>
      widget.controller.me['can_manage'] == true &&
      shift['pending_swap'] != true &&
      _future(shift['start']);

  bool _canSwap(Json shift) {
    final c = widget.controller;
    return c.me['role'] != 'ADMIN' &&
        (shift['technician'] == c.me['technician'] ||
            c.me['can_manage'] == true) &&
        _future(shift['end']);
  }

  String _interval(Json shift) {
    final offset = widget.controller.utcOffset;
    return '${dateLabel(shift['start'], offset)} — ${dateLabel(shift['end'], offset)}';
  }

  DateTime get _firstFuture {
    final c = widget.controller;
    final now = c.orgNow;
    final start = text(c.me, 'duty_start', '09:00');
    final clock =
        '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}';
    return DateTime.utc(
      now.year,
      now.month,
      now.day + (clock.compareTo(start.substring(0, 5)) >= 0 ? 1 : 0),
    );
  }

  Future<void> _publish([Json? rule]) async {
    final c = widget.controller;
    final organization = c.organization;
    if (organization == null || !c.canWrite) return;
    final (monthFrom, monthTo) = _range();
    final ruleFrom = DateTime.tryParse('${rule?['from']}');
    final from = ruleFrom ?? monthFrom;
    final to =
        DateTime.tryParse('${rule?['to']}') ??
        (ruleFrom == null
            ? monthTo
            : DateTime.utc(ruleFrom.year, ruleFrom.month + 1, 0));
    if (c.me['duty_roster_review_api'] != 1) {
      final accepted = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Опубликовать месяц?'),
          content: Text(
            MaterialLocalizations.of(context).formatMonthYear(monthFrom),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Отмена'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Опубликовать'),
            ),
          ],
        ),
      );
      if (accepted != true || !mounted) return;
      setState(() => _busy = true);
      try {
        final response = await c.request(
          'duty/roster-publish/',
          method: 'POST',
          expectedOrganization: organization,
          data: {'from': dutyDate(monthFrom), 'to': dutyDate(monthTo)},
        );
        c.log.record('duty_roster_published');
        await _refresh();
        if (mounted) {
          _notice(
            'Опубликовано. Новых смен ${response['added']}, изменено ${response['updated']}.',
          );
        }
      } catch (error) {
        c.log.record('duty_roster_publish_failed');
        if (mounted) showError(context, error);
      } finally {
        if (mounted) setState(() => _busy = false);
      }
      return;
    }
    final result = await showDialog<Json>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _DutyPublishDialog(
        controller: c,
        organization: organization,
        first: _firstFuture,
        replace: rule?['people'] != null,
        from: from.isBefore(_firstFuture) ? _firstFuture : from,
        to: to,
      ),
    );
    if (result == null || !mounted) return;
    await _refresh();
    if (mounted) {
      _notice(
        'Опубликовано. Новых смен ${result['added']}, изменено ${result['updated']}.',
      );
    }
  }

  late DateTime _anchor;
  late String _selected;
  bool _loading = false;
  String? _error;
  List<Json> _days = [];
  int _loadId = 0;

  @override
  void initState() {
    super.initState();
    final now = widget.controller.orgNow;
    _anchor = DateTime.utc(now.year, now.month, now.day);
    _selected = dutyDate(_anchor);
    unawaited(_load());
  }

  (DateTime, DateTime) _range() {
    return (
      DateTime.utc(_anchor.year, _anchor.month),
      DateTime.utc(_anchor.year, _anchor.month + 1, 0),
    );
  }

  String _label(DateTime value) =>
      MaterialLocalizations.of(context).formatMediumDate(value);

  List<Json> _fallback(DateTime from, DateTime to) {
    final c = widget.controller;
    final shifts = c.list('duty');
    return [
      for (
        var day = from;
        !day.isAfter(to);
        day = day.add(const Duration(days: 1))
      )
        {
          'date': dutyDate(day),
          'shifts': shifts.where((shift) {
            final stamp = DateTime.tryParse('${shift['start']}');
            return stamp != null &&
                dutyDate(stamp.toUtc().add(Duration(minutes: c.utcOffset))) ==
                    dutyDate(day);
          }).toList(),
        },
    ];
  }

  Future<void> _load() async {
    final c = widget.controller;
    final organization = c.organization;
    final id = ++_loadId;
    final (from, to) = _range();
    setState(() {
      _loading = c.me['duty_roster_api'] == 1;
      _days = _fallback(from, to);
      _error = null;
    });
    if (c.me['duty_roster_api'] != 1 || organization == null) return;
    try {
      final data = await c.resource(
        'duty/roster/?from=${dutyDate(from)}&to=${dutyDate(to)}',
        expectedOrganization: organization,
      );
      if (mounted && id == _loadId && c.organization == organization) {
        setState(() => _days = records(data));
      }
    } catch (error) {
      c.log.record('duty_roster_load_failed');
      if (mounted && id == _loadId) setState(() => _error = error.toString());
    } finally {
      if (mounted && id == _loadId) setState(() => _loading = false);
    }
  }

  Future<void> _refresh() async {
    await widget.controller.refresh();
    if (mounted) await _load();
  }

  void _move(int amount) {
    setState(() {
      _anchor = DateTime.utc(_anchor.year, _anchor.month + amount);
      _selected = dutyDate(_anchor);
    });
    unawaited(_load());
  }

  Widget _pending(Json swap) {
    final c = widget.controller;
    return Sheet(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${text(swap, 'source_name')} → ${text(swap, 'target_name')}'),
          Text(text(swap, 'reason')),
          Text(dateLabel(swap['start'], c.utcOffset)),
          Wrap(
            spacing: 8,
            children: [
              if (swap['target'] == c.me['technician'])
                FilledButton(
                  onPressed: c.canWrite && !_busy
                      ? () => _resolve(swap, true)
                      : null,
                  child: const Text('Подтвердить подмену'),
                ),
              if (swap['target'] == c.me['technician'] ||
                  swap['source'] == c.me['technician'] ||
                  c.me['can_manage'] == true)
                OutlinedButton(
                  onPressed: c.canWrite && !_busy
                      ? () => _resolve(swap, false)
                      : null,
                  child: const Text('Отменить запрос'),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _dayCell(Json day) {
    final colors = Theme.of(context).colorScheme;
    final date = DateTime.parse(day['date']);
    final shift = records(day['shifts'] ?? []).firstOrNull;
    final name = shift == null
        ? text(day, 'suggested_name', '')
        : text(shift, 'technician_name', '');
    final word = name.split(' ').first;
    final shortName = word.characters.take(3).toString();
    final selected = _selected == day['date'];
    final draft = day['suggested_name'] != null;
    final today = day['date'] == dutyDate(widget.controller.orgNow);
    final label = name.isEmpty
        ? day['covered_from_previous'] == true
              ? 'Продолжается предыдущая смена'
              : 'Дежурный пока не назначен'
        : name;
    return Semantics(
      label: '${_label(date)}. $label${draft ? '. Есть черновик' : ''}',
      selected: selected,
      button: true,
      excludeSemantics: true,
      child: Padding(
        padding: const EdgeInsets.all(2),
        child: Material(
          color: selected
              ? colors.primaryContainer
              : draft
              ? colors.secondaryContainer
              : colors.surfaceContainerLow,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
            side: today || selected
                ? BorderSide(color: colors.primary)
                : BorderSide.none,
          ),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: () => setState(() => _selected = day['date'] as String),
            child: SizedBox(
              height: 52,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    '${date.day}',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  Text(
                    name.isNotEmpty
                        ? shortName
                        : day['covered_from_previous'] == true
                        ? '↪'
                        : '–',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 10),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _selectedDay(Json day) {
    final c = widget.controller;
    final shifts = records(day['shifts'] ?? []);
    final carry = day['covered_from_previous'] == true;
    final canCreate =
        c.me['can_manage'] == true &&
        shifts.isEmpty &&
        !carry &&
        _future(day['start']);
    final canWrite = c.canWrite && !_busy;
    return Sheet(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionTitle(_label(DateTime.parse(day['date']))),
          if (shifts.isEmpty)
            Text(
              carry
                  ? 'Продолжается предыдущая смена'
                  : 'Дежурный пока не назначен',
            ),
          for (final shift in shifts) ...[
            Text(
              text(shift, 'technician_name'),
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            Text(_interval(shift)),
            if (shift['pending_swap'] == true)
              const Text('Ожидается ответ на подмену'),
            Wrap(
              spacing: 8,
              children: [
                if (_canEdit(shift))
                  OutlinedButton(
                    onPressed: canWrite ? () => _editDay(day, shift) : null,
                    child: const Text('Изменить'),
                  ),
                if (_canSwap(shift))
                  TextButton(
                    onPressed: canWrite ? () => _swap(shift) : null,
                    child: const Text('Запросить подмену'),
                  ),
              ],
            ),
          ],
          if (day['suggested_name'] != null)
            Text('Черновик по очереди · ${day['suggested_name']}'),
          if (day['needs_assignment'] == true && shifts.isNotEmpty)
            const Text('Проверьте назначение на эту дату'),
          if (canCreate)
            FilledButton(
              onPressed: canWrite ? () => _editDay(day) : null,
              child: const Text('Назначить'),
            ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final (first, last) = _range();
    final offset = first.weekday - 1;
    final selected = _days.where((day) => day['date'] == _selected).firstOrNull;
    final swaps = c.list('duty-swaps').where((s) => s['status'] == 'PENDING');
    final manage = c.me['can_manage'] == true;
    final supported = c.me['duty_roster_api'] == 1;
    final review = c.me['duty_roster_review_api'] == 1;
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.all(18),
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          SectionTitle(
            'Дежурства',
            trailing: manage
                ? TextButton.icon(
                    onPressed: c.canWrite && !_busy
                        ? () async {
                            final rule = await Navigator.push<Json>(
                              context,
                              MaterialPageRoute<Json>(
                                builder: (_) => supported
                                    ? DutyRosterSettings(
                                        controller: c,
                                        organization: c.organization!,
                                      )
                                    : PlanDutyPage(controller: c),
                              ),
                            );
                            if (!mounted) return;
                            if (rule != null) {
                              setState(() {
                                _anchor = DateTime.parse(rule['from']);
                                _selected = dutyDate(_anchor);
                              });
                            }
                            await _load();
                            if (mounted && rule != null && review) {
                              await _publish(rule);
                            }
                          }
                        : null,
                    icon: const Icon(Icons.settings_outlined),
                    label: const Text('Настройки'),
                  )
                : null,
          ),
          DutyCard(controller: c),
          const SizedBox(height: 16),
          if (swaps.isNotEmpty) const SectionTitle('Запросы подмены'),
          for (final swap in swaps)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _pending(swap),
            ),
          Row(
            children: [
              IconButton(
                tooltip: 'Предыдущий месяц',
                onPressed: () => _move(-1),
                icon: const Icon(Icons.chevron_left),
              ),
              Expanded(
                child: Text(
                  MaterialLocalizations.of(context).formatMonthYear(first),
                  textAlign: TextAlign.center,
                ),
              ),
              IconButton(
                tooltip: 'Следующий месяц',
                onPressed: () => _move(1),
                icon: const Icon(Icons.chevron_right),
              ),
            ],
          ),
          if (_loading) const LinearProgressIndicator(),
          if (_error != null)
            ListTile(
              title: Text(_error!),
              trailing: TextButton(
                onPressed: _load,
                child: const Text('Повторить'),
              ),
            ),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(3),
              child: Column(
                children: [
                  Row(
                    children: [
                      for (final label in [
                        'Пн',
                        'Вт',
                        'Ср',
                        'Чт',
                        'Пт',
                        'Сб',
                        'Вс',
                      ])
                        Expanded(
                          child: Text(
                            label,
                            textAlign: TextAlign.center,
                            style: const TextStyle(fontSize: 11),
                          ),
                        ),
                    ],
                  ),
                  for (
                    var week = 0;
                    week < (offset + _days.length + 6) ~/ 7;
                    week++
                  )
                    Row(
                      children: [
                        for (var column = 0; column < 7; column++)
                          Expanded(
                            child:
                                week * 7 + column < offset ||
                                    week * 7 + column >= offset + _days.length
                                ? const SizedBox()
                                : _dayCell(_days[week * 7 + column - offset]),
                          ),
                      ],
                    ),
                ],
              ),
            ),
          ),
          if (selected != null) _selectedDay(selected),
          if (manage && supported && !last.isBefore(_firstFuture))
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton(
                onPressed: c.canWrite && !_busy ? _publish : null,
                child: Text(
                  review ? 'Проверить и опубликовать' : 'Опубликовать месяц',
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _DutyPublishDialog extends StatefulWidget {
  const _DutyPublishDialog({
    required this.controller,
    required this.organization,
    required this.first,
    required this.replace,
    required this.from,
    required this.to,
  });

  final LiftController controller;
  final int organization;
  final DateTime first, from, to;
  final bool replace;

  @override
  State<_DutyPublishDialog> createState() => _DutyPublishDialogState();
}

class _DutyPublishDialogState extends State<_DutyPublishDialog> {
  late DateTime _from = widget.from;
  late DateTime _to = widget.to;
  late bool _replace = widget.replace;
  bool _busy = false;
  Json? _preview;
  String? _error;

  String _label(DateTime date) =>
      MaterialLocalizations.of(context).formatShortDate(date);

  Future<void> _pick(bool start) async {
    final first = start ? widget.first : _from;
    final initial = start ? _from : _to;
    final date = await showDatePicker(
      context: context,
      firstDate: first,
      lastDate: DateTime(first.year + 5, 12, 31),
      initialDate: initial.isBefore(first) ? first : initial,
    );
    if (date == null || !mounted) return;
    setState(() {
      final value = DateTime.utc(date.year, date.month, date.day);
      if (start) {
        _from = value;
        if (_to.isBefore(value)) _to = value;
      } else {
        _to = value;
      }
      _preview = null;
      _error = null;
    });
  }

  Future<void> _submit(bool publish) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final c = widget.controller;
    try {
      final data = await c.request(
        'duty/roster-publish/',
        method: 'POST',
        expectedOrganization: widget.organization,
        data: {
          'from': dutyDate(_from),
          'to': dutyDate(_to),
          'replace_existing': _replace,
          if (publish) 'token': _preview!['token'] else 'preview': true,
        },
      );
      if (!mounted) return;
      if (publish) {
        c.log.record('duty_roster_published');
        Navigator.pop(context, Map<String, dynamic>.from(data as Map));
      } else {
        setState(() => _preview = Map<String, dynamic>.from(data as Map));
      }
    } catch (error) {
      c.log.record(
        publish ? 'duty_roster_publish_failed' : 'duty_roster_preview_failed',
      );
      if (mounted) {
        setState(() {
          _error = error.toString();
          _preview = null;
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final plan = _preview;
    final missing = plan?['missing'] as List? ?? [];
    final changes = records(plan?['changes'] ?? []);
    return PopScope(
      canPop: !_busy,
      child: AlertDialog(
        scrollable: true,
        title: const Text('Проверить и опубликовать'),
        content: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Wrap(
              spacing: 8,
              children: [
                OutlinedButton(
                  onPressed: _busy ? null : () => _pick(true),
                  child: Text('С ${_label(_from)}'),
                ),
                OutlinedButton(
                  onPressed: _busy ? null : () => _pick(false),
                  child: Text('По ${_label(_to)}'),
                ),
              ],
            ),
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Пересчитать уже назначенные суточные смены'),
              value: _replace,
              onChanged: _busy
                  ? null
                  : (value) => setState(() {
                      _replace = value ?? false;
                      _preview = null;
                    }),
            ),
            if (_replace)
              const Text(
                'Проверка включает ручные назначения. Смены с историей подмен сохранятся.',
              ),
            if (_busy) const LinearProgressIndicator(),
            if (_error != null) Text(_error!),
            if (plan != null) ...[
              Text('Новых смен ${plan['added']} · замен ${plan['updated']}'),
              if (missing.isNotEmpty)
                Text('Назначьте дежурных на даты ${missing.join(', ')}'),
              if (missing.isEmpty && changes.isEmpty)
                const Text(
                  'График уже заполнен. Изменений для публикации нет.',
                ),
              for (final change in changes)
                Text(
                  '${_label(DateTime.parse(change['date']))} · ${change['old_name'] == null ? '' : "${change['old_name']} → "}${change['new_name']}',
                ),
            ],
          ],
        ),
        actions: [
          TextButton(
            onPressed: _busy ? null : () => Navigator.pop(context),
            child: const Text('Закрыть'),
          ),
          OutlinedButton(
            onPressed: _busy || _to.isBefore(_from)
                ? null
                : () => _submit(false),
            child: const Text('Проверить даты'),
          ),
          if (changes.isNotEmpty && missing.isEmpty)
            FilledButton(
              onPressed: _busy ? null : () => _submit(true),
              child: const Text('Опубликовать'),
            ),
        ],
      ),
    );
  }
}

class PlanDutyPage extends StatefulWidget {
  const PlanDutyPage({super.key, required this.controller});
  final LiftController controller;
  @override
  State<PlanDutyPage> createState() => _PlanDutyPageState();
}

class _PlanDutyPageState extends State<PlanDutyPage> {
  late DateTime _from, _to;
  late int _org;
  final List<int> _technicians = [];
  Json? _preview;
  bool _busy = false;
  bool _replace = false;
  @override
  void initState() {
    super.initState();
    final now = widget.controller.orgNow;
    _org = widget.controller.organization!;
    _from = DateTime(now.year, now.month + 1);
    _to = DateTime(now.year, now.month + 2, 0);
  }

  String _date(DateTime value) => value.toIso8601String().substring(0, 10);
  Future<void> _pick(bool from) async {
    final date = await showDatePicker(
      context: context,
      initialDate: from ? _from : _to,
      firstDate: DateTime(2020),
      lastDate: DateTime.now().add(const Duration(days: 730)),
    );
    if (date != null) {
      setState(() {
        if (from) {
          _from = date;
        } else {
          _to = date;
        }
        _preview = null;
      });
    }
  }

  Future<void> _confirmApply() async {
    final replaced = (_preview?['replaced'] as num?)?.toInt() ?? 0;
    if (replaced > 0) {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Заменить график?'),
          content: Text(
            'Будет заменено будущих смен: $replaced. '
            'Старые назначения исчезнут из графика. Продолжить?',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Отмена'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Заменить'),
            ),
          ],
        ),
      );
      if (confirmed != true || !mounted) return;
    }
    await _plan(true);
  }

  Future<void> _plan(bool apply) async {
    setState(() => _busy = true);
    try {
      final c = widget.controller;
      if (apply) {
        await c.request(
          'duty/apply/',
          method: 'POST',
          data: {'token': _preview!['token']},
          expectedOrganization: _org,
        );
        await c.refresh();
        if (mounted) Navigator.pop(context);
      } else {
        final data = await c.request(
          'duty/preview/',
          method: 'POST',
          data: {
            'from': _date(_from),
            'to': _date(_to),
            'technicians': _technicians,
            'time': text(c.me, 'duty_start', '09:00'),
            'hours': 24,
            'kind': 'daily',
            'every': 1,
            'replace': _replace,
          },
          expectedOrganization: _org,
        );
        if (mounted) setState(() => _preview = Map<String, dynamic>.from(data));
      }
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
    builder: (context) {
      final c = widget.controller;
      return Scaffold(
        appBar: AppBar(title: const Text('Составить график')),
        body: ListView(
          padding: const EdgeInsets.all(18),
          children: [
            Sheet(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    'Суточные дежурства по очереди',
                    style: TextStyle(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton(
                    onPressed: _busy ? null : () => _pick(true),
                    child: Text(
                      'С ${dateLabel(_date(_from), 0, time: false)} ${_from.year}',
                    ),
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton(
                    onPressed: _busy ? null : () => _pick(false),
                    child: Text(
                      'По ${dateLabel(_date(_to), 0, time: false)} ${_to.year}',
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Начало смены ${text(c.me, 'duty_start', '09:00')} · ${text(c.me, 'timezone')}',
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    'Нажмите механиков в порядке чередования. Повторное нажатие убирает из очереди.',
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final t
                          in c
                              .list('technicians')
                              .where((t) => t['active'] == true))
                        FilterChip(
                          selected: _technicians.contains(t['id']),
                          label: Text(
                            '${_technicians.contains(t['id']) ? '${_technicians.indexOf(t['id'] as int) + 1}. ' : ''}${text(t, 'full_name')}',
                          ),
                          onSelected: _busy
                              ? null
                              : (v) => setState(() {
                                  if (v) {
                                    _technicians.add(t['id'] as int);
                                  } else {
                                    _technicians.remove(t['id']);
                                  }
                                  _preview = null;
                                }),
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  SwitchListTile.adaptive(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Заменить существующий график'),
                    subtitle: const Text(
                      'Только будущие смены в выбранном периоде. '
                      'Начавшиеся дежурства нельзя перезаписать.',
                    ),
                    value: _replace,
                    onChanged: _busy
                        ? null
                        : (value) => setState(() {
                            _replace = value;
                            _preview = null;
                          }),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _busy || !c.canWrite || _technicians.isEmpty
                  ? null
                  : () => _plan(false),
              child: const Text('Предпросмотр графика'),
            ),
            if (_preview != null) ...[
              const SectionTitle('Предпросмотр'),
              Text(
                'Новых смен: ${(_preview!['added'] as List).length} · будет заменено: ${_preview!['replaced']} · пропущено занятых: ${_preview!['skipped']}',
              ),
              const SizedBox(height: 12),
              for (final row in records(_preview!['added']))
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(
                    c
                            .list('technicians')
                            .where((t) => t['id'] == row['technician_id'])
                            .map((t) => text(t, 'full_name'))
                            .firstOrNull ??
                        'Механик',
                  ),
                  subtitle: Text(
                    '${dateLabel(row['start'], c.utcOffset)} — ${dateLabel(row['end'], c.utcOffset)}',
                  ),
                ),
              FilledButton(
                onPressed:
                    _busy || !c.canWrite || (_preview!['added'] as List).isEmpty
                    ? null
                    : _confirmApply,
                child: const Text('Применить график'),
              ),
            ],
            const SizedBox(height: 16),
            const Text(
              'Без переключателя существующие смены сохраняются. Для изменения текущей смены используется подтверждённая подмена.',
              style: TextStyle(fontSize: 12),
            ),
          ],
        ),
      );
    },
  );
}
