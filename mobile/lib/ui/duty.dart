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

  Future<void> _openDay(Json day, List<Json> shifts, bool canCreate) async {
    if (canCreate || (shifts.length == 1 && _canEdit(shifts.single))) {
      await _editDay(day, shifts.isEmpty ? null : shifts.single);
      return;
    }
    final selection = await showModalBottomSheet<({Json shift, bool swap})>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
          children: [
            SectionTitle(_label(DateTime.parse(day['date']))),
            if (shifts.isEmpty)
              Text(
                day['covered_from_previous'] == true
                    ? 'Продолжается предыдущая смена.'
                    : 'Дежурный пока не назначен.',
              ),
            for (final shift in shifts) ...[
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(text(shift, 'technician_name')),
                subtitle: Text(_interval(shift)),
                trailing: _canEdit(shift)
                    ? TextButton(
                        onPressed: () =>
                            Navigator.pop(context, (shift: shift, swap: false)),
                        child: const Text('Изменить'),
                      )
                    : null,
              ),
              if (_canSwap(shift))
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton(
                    onPressed: () =>
                        Navigator.pop(context, (shift: shift, swap: true)),
                    child: const Text('Запросить подмену'),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
    if (!mounted || selection == null) return;
    if (selection.swap) {
      await _swap(selection.shift);
    } else {
      await _editDay(day, selection.shift);
    }
  }

  String _interval(Json shift) {
    final offset = widget.controller.utcOffset;
    return '${dateLabel(shift['start'], offset)} — ${dateLabel(shift['end'], offset)}';
  }

  Future<void> _publish() async {
    final c = widget.controller;
    final organization = c.organization;
    if (organization == null) return;
    final (from, to) = _range(month: true);
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Опубликовать месяц?'),
        content: Text(
          '${MaterialLocalizations.of(context).formatMonthYear(from)}. '
          'Назначения по очереди вступят в силу. Ручные смены и история подмен сохранятся.',
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
      final result = await c.request(
        'duty/roster-publish/',
        method: 'POST',
        expectedOrganization: organization,
        data: {'from': dutyDate(from), 'to': dutyDate(to)},
      );
      c.log.record('duty_roster_published');
      await _refresh();
      if (mounted) {
        _notice(
          'Опубликовано. Новых смен ${result['added']}, изменено ${result['updated']}.',
        );
      }
    } catch (error) {
      c.log.record('duty_roster_publish_failed');
      if (mounted) showError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  late DateTime _anchor;
  bool _month = false;
  bool _loading = false;
  String? _error;
  List<Json> _days = [];
  int _loadId = 0;

  @override
  void initState() {
    super.initState();
    final now = widget.controller.orgNow;
    _anchor = DateTime.utc(now.year, now.month, now.day);
    unawaited(_load());
  }

  (DateTime, DateTime) _range({required bool month}) {
    if (month) {
      return (
        DateTime.utc(_anchor.year, _anchor.month),
        DateTime.utc(_anchor.year, _anchor.month + 1, 0),
      );
    }
    final first = _anchor.subtract(Duration(days: _anchor.weekday - 1));
    return (first, first.add(const Duration(days: 6)));
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
    final (from, to) = _range(month: _month);
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
      _anchor = _month
          ? DateTime.utc(_anchor.year, _anchor.month + amount)
          : _anchor.add(Duration(days: 7 * amount));
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

  Widget _dayTile(Json day) {
    final c = widget.controller;
    final date = DateTime.parse(day['date']);
    final shifts = records(day['shifts'] ?? []);
    final shift = shifts.firstOrNull;
    final carry = day['covered_from_previous'] == true;
    final name = shift == null
        ? text(
            day,
            'suggested_name',
            carry ? 'Продолжается предыдущая смена' : 'Нет дежурного',
          )
        : text(shift, 'technician_name');
    final canCreate =
        c.me['can_manage'] == true &&
        shifts.isEmpty &&
        !carry &&
        _future(day['start']);
    final editable = shifts.length == 1 && _canEdit(shifts.single);
    final suggestion = day['suggested_name'] != null;
    final vacant =
        (shift == null && !suggestion && !carry) ||
        day['needs_assignment'] == true;
    final summary = day['needs_assignment'] == true && shift != null
        ? 'Требуется замена'
        : suggestion
        ? (shift == null
              ? 'По очереди · до публикации'
              : 'При публикации · ${day['suggested_name']}')
        : shift != null
        ? _interval(shift)
        : '';
    return ListTile(
      tileColor: vacant
          ? Theme.of(context).colorScheme.surfaceContainerLow
          : null,
      leading: SizedBox(
        width: 38,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('${date.day}', style: Theme.of(context).textTheme.titleMedium),
            Text(['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][date.weekday - 1]),
          ],
        ),
      ),
      title: Text(name),
      subtitle: summary.isEmpty ? null : Text(summary),
      trailing: Text(
        canCreate
            ? 'Назначить'
            : editable
            ? 'Изменить'
            : 'Открыть',
        style: TextStyle(
          color: Theme.of(context).colorScheme.primary,
          fontWeight: FontWeight.w600,
        ),
      ),
      onTap: _busy || (canCreate || editable) && !c.canWrite
          ? null
          : () => _openDay(day, shifts, canCreate),
    );
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final (first, last) = _range(month: _month);
    final swaps = c.list('duty-swaps').where((s) => s['status'] == 'PENDING');
    final manage = c.me['can_manage'] == true;
    final supported = c.me['duty_roster_api'] == 1;
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
                            await Navigator.push(
                              context,
                              MaterialPageRoute<void>(
                                builder: (_) => supported
                                    ? DutyRosterSettings(
                                        controller: c,
                                        organization: c.organization!,
                                      )
                                    : PlanDutyPage(controller: c),
                              ),
                            );
                            if (mounted) await _load();
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
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: false, label: Text('Неделя')),
              ButtonSegment(value: true, label: Text('Месяц')),
            ],
            selected: {_month},
            onSelectionChanged: (values) {
              setState(() => _month = values.single);
              unawaited(_load());
            },
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              IconButton(
                tooltip: 'Предыдущий период',
                onPressed: () => _move(-1),
                icon: const Icon(Icons.chevron_left),
              ),
              Expanded(
                child: Text(
                  _month
                      ? MaterialLocalizations.of(context).formatMonthYear(first)
                      : '${_label(first)} — ${_label(last)}',
                  textAlign: TextAlign.center,
                ),
              ),
              IconButton(
                tooltip: 'Следующий период',
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
            child: Column(children: [for (final day in _days) _dayTile(day)]),
          ),
          if (manage &&
              supported &&
              !_range(month: true).$2.isBefore(
                DateTime.utc(c.orgNow.year, c.orgNow.month, c.orgNow.day),
              ))
            Align(
              alignment: Alignment.centerRight,
              child: OutlinedButton(
                onPressed: c.canWrite && !_busy ? _publish : null,
                child: const Text('Опубликовать месяц'),
              ),
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
