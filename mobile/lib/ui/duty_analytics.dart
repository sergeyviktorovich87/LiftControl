import 'dart:async';

import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';

class DutyAnalyticsPage extends StatefulWidget {
  const DutyAnalyticsPage({
    super.key,
    required this.controller,
    required this.organization,
  });

  final LiftController controller;
  final int organization;

  @override
  State<DutyAnalyticsPage> createState() => _DutyAnalyticsPageState();
}

class _DutyAnalyticsPageState extends State<DutyAnalyticsPage> {
  LiftController get c => widget.controller;
  late final _today = c.orgNow;
  late DateTimeRange _period = DateTimeRange(
    start: DateTime(_today.year, _today.month),
    end: DateTime(_today.year, _today.month, _today.day),
  );
  Json? _report;
  String _error = '';
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  String _date(DateTime value) => value.toIso8601String().substring(0, 10);

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = '';
    });
    try {
      final report = await c.request(
        'analytics/duty/?from=${_date(_period.start)}&to=${_date(_period.end)}',
        expectedOrganization: widget.organization,
      );
      if (mounted && c.organization == widget.organization) {
        setState(() => _report = Map<String, dynamic>.from(report as Map));
      }
    } catch (error) {
      c.log.record('duty_analytics_load_failed');
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _choosePeriod() async {
    final selected = await showDateRangePicker(
      context: context,
      firstDate: DateTime(2000),
      lastDate: DateTime(_today.year + 2),
      initialDateRange: _period,
    );
    if (selected == null || !mounted) return;
    if (selected.duration.inDays >= 366) {
      showError(context, const ApiError('Выберите период до 366 дней.'));
      return;
    }
    setState(() {
      _period = selected;
      _report = null;
    });
    await _load();
  }

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: c,
    organization: widget.organization,
    builder: (context) {
      if (c.me['role'] != 'ADMIN') {
        return Scaffold(
          appBar: AppBar(title: const Text('Аналитика')),
          body: const Center(child: Text('Доступно администратору')),
        );
      }
      final people = records(_report?['technicians'] ?? []);
      final swaps = records(_report?['swaps'] ?? []);
      final localizations = MaterialLocalizations.of(context);
      return Scaffold(
        appBar: AppBar(
          title: const Text('Аналитика'),
          actions: [
            IconButton(
              tooltip: 'Обновить',
              onPressed: _loading ? null : _load,
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        body: ListView(
          padding: const EdgeInsets.all(18),
          children: [
            const SectionTitle('Дежурство'),
            OutlinedButton.icon(
              onPressed: _loading ? null : _choosePeriod,
              icon: const Icon(Icons.date_range_outlined),
              label: Text(
                '${localizations.formatShortDate(_period.start)} — '
                '${localizations.formatShortDate(_period.end)}',
              ),
            ),
            if (_loading) const LinearProgressIndicator(),
            if (_error.isNotEmpty) Text(_error),
            for (final person in people)
              Card(
                child: ListTile(
                  title: Text(text(person, 'name')),
                  subtitle: Text(
                    'Завершено смен: ${person['completed']} · '
                    'В графике: ${person['planned']}\n'
                    'Подменил: ${person['swaps_in']} · '
                    'Подменили его: ${person['swaps_out']}',
                  ),
                ),
              ),
            if (_report != null) ...[
              const SectionTitle('Принятые подмены'),
              if (swaps.isEmpty) const Text('За этот период подмен не было.'),
              for (final swap in swaps)
                ListTile(
                  title: Text(
                    '${text(swap, 'source')} → ${text(swap, 'target')}',
                  ),
                  subtitle: Text(dateLabel(swap['start'], c.utcOffset)),
                ),
            ],
          ],
        ),
      );
    },
  );
}
