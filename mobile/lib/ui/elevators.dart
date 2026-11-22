import 'dart:async';

import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';
import 'tickets.dart';
import 'journal.dart';
import 'platform_bridge.dart';
import 'staff.dart';
import 'media_library.dart';
import 'lift_documents.dart';
import 'extras.dart' show PartForm;
import 'building_editor.dart';

String _searchable(String value) =>
    value.toLowerCase().replaceAll(RegExp(r'[^а-яёa-z0-9]'), '');
void openElevator(
  BuildContext context,
  LiftController c,
  Json e, {
  bool inspection = false,
}) => Navigator.push(
  context,
  MaterialPageRoute<void>(
    builder: (_) => ElevatorPage(
      controller: c,
      id: e['id'] as int,
      organization: c.organization!,
      inspection: inspection,
    ),
  ),
);

class ElevatorsPage extends StatefulWidget {
  const ElevatorsPage({super.key, required this.controller});
  final LiftController controller;
  @override
  State<ElevatorsPage> createState() => _ElevatorsPageState();
}

class _ElevatorsPageState extends State<ElevatorsPage> {
  String _search = '';
  bool _mine = false, _archive = false;
  @override
  Widget build(BuildContext context) {
    final c = widget.controller, query = _searchable(_search);
    final elevators = c
        .list('elevators')
        .where(
          (e) =>
              (_archive || e['active'] == true) &&
              (!_mine || e['assigned_technician'] == c.me['technician']) &&
              _searchable('${e['address']} ${liftLabel(e)}').contains(query),
        )
        .toList();
    final buildingIds = elevators.map((e) => e['building']).toSet();
    final buildings = c
        .list('buildings')
        .where(
          (b) =>
              buildingIds.contains(b['id']) ||
              (c.me['can_manage'] == true &&
                  !_mine &&
                  _searchable('${b['address']} ${b['name']}').contains(query)),
        )
        .toList();
    final streets = <String, List<Json>>{};
    for (final b in buildings) {
      final street = text(b, 'street', 'Без указанной улицы');
      (streets[street] ??= []).add(b);
    }
    return RefreshIndicator(
      onRefresh: c.refresh,
      child: ListView(
        padding: const EdgeInsets.all(18),
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          const SectionTitle('Объекты и лифты'),
          if (c.me['can_manage'] == true)
            OutlinedButton.icon(
              onPressed: c.canWrite
                  ? () => openBuildingEditor(context, c)
                  : null,
              icon: const Icon(Icons.add),
              label: const Text('Добавить дом'),
            ),
          TextField(
            decoration: const InputDecoration(
              hintText: 'Улица, дом или номер лифта',
              prefixIcon: Icon(Icons.search),
            ),
            onChanged: (v) => setState(() => _search = v),
          ),
          const SizedBox(height: 12),
          FilterChip(
            label: const Text('Показывать архив'),
            selected: _archive,
            onSelected: (v) => setState(() => _archive = v),
          ),
          if (c.me['technician'] != null)
            Align(
              alignment: Alignment.centerLeft,
              child: FilterChip(
                label: const Text('Закреплённые за мной'),
                selected: _mine,
                onSelected: (v) => setState(() => _mine = v),
              ),
            ),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Text(
              '${buildings.length} объектов · ${elevators.length} лифтов',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
          if (streets.isEmpty)
            const Sheet(
              child: EmptyState(
                'Объектов нет',
                'Проверьте выбранную организацию или измените поиск.',
                icon: Icons.elevator_outlined,
              ),
            ),
          for (final entry in streets.entries)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Card(
                child: ExpansionTile(
                  key: ValueKey(
                    '${c.organization}_${entry.key}_${query.isNotEmpty}',
                  ),
                  initiallyExpanded: query.isNotEmpty,
                  tilePadding: const EdgeInsets.symmetric(
                    horizontal: 18,
                    vertical: 6,
                  ),
                  shape: const Border(),
                  collapsedShape: const Border(),
                  leading: Icon(
                    Icons.location_city_outlined,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  title: Text(
                    entry.key,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  subtitle: Text('Объектов: ${entry.value.length}'),
                  children: [
                    for (final b in entry.value)
                      ListTile(
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 22,
                          vertical: 5,
                        ),
                        title: Text(text(b, 'address')),
                        subtitle: Text(
                          'Лифтов: ${elevators.where((e) => e['building'] == b['id']).length}',
                        ),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () => Navigator.push(
                          context,
                          MaterialPageRoute<void>(
                            builder: (_) => BuildingPage(
                              controller: c,
                              id: b['id'] as int,
                              organization: c.organization!,
                              showArchived: _archive,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class BuildingPage extends StatelessWidget {
  const BuildingPage({
    this.showArchived = false,
    super.key,
    required this.controller,
    required this.id,
    required this.organization,
  });
  final LiftController controller;
  final int id, organization;
  final bool showArchived;
  @override
  Widget build(BuildContext context) => ScopePage(
    controller: controller,
    organization: organization,
    builder: (context) {
      final b = controller
              .list('buildings')
              .firstWhere((b) => b['id'] == id, orElse: () => {}),
          lifts = controller
              .list('elevators')
              .where(
                (e) =>
                    e['building'] == id &&
                    (showArchived || e['active'] == true),
              )
              .toList();
      return Scaffold(
        appBar: AppBar(title: const Text('Объект')),
        body: ListView(
          padding: const EdgeInsets.all(18),
          children: [
            Sheet(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    text(b, 'address'),
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(text(b, 'name')),
                  if (text(b, 'management_company', '').isNotEmpty) ...[
                    const Divider(),
                    Text(text(b, 'management_company')),
                  ],
                  if (text(b, 'contact_name', '').isNotEmpty) ...[
                    const SizedBox(height: 8),
                    SelectableText(
                      '${text(b, 'contact_name')} · ${text(b, 'contact_phone')}',
                    ),
                  ],
                ],
              ),
            ),
            if (controller.me['can_manage'] == true && b.isNotEmpty)
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton.icon(
                    onPressed: controller.canWrite
                        ? () => Navigator.push(
                            context,
                            MaterialPageRoute<void>(
                              builder: (_) => _EditElevatorPage(
                                controller: controller,
                                elevator: {
                                  'building': id,
                                  'address': b['address'],
                                },
                                organization: organization,
                              ),
                            ),
                          )
                        : null,
                    icon: const Icon(Icons.add),
                    label: const Text('Добавить лифт'),
                  ),
                  OutlinedButton(
                    onPressed: controller.canWrite
                        ? () => openBuildingEditor(
                            context,
                            controller,
                            building: b,
                          )
                        : null,
                    child: const Text('Изменить дом'),
                  ),
                  OutlinedButton(
                    onPressed: controller.canWrite
                        ? () async {
                            if (await deleteBuilding(
                                  context,
                                  controller,
                                  b,
                                  organization,
                                ) &&
                                context.mounted) {
                              Navigator.pop(context);
                            }
                          }
                        : null,
                    child: const Text('Удалить дом'),
                  ),
                ],
              ),
            SectionTitle('Лифты · ${lifts.length}'),
            for (final e in lifts)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: LiftTile(
                  elevator: e,
                  onTap: () => openElevator(context, controller, e),
                ),
              ),
          ],
        ),
      );
    },
  );
}

class LiftTile extends StatelessWidget {
  const LiftTile({super.key, required this.elevator, required this.onTap});
  final Json elevator;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Card(
    child: ListTile(
      contentPadding: const EdgeInsets.all(16),
      leading: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Icon(
          Icons.elevator_outlined,
          color: Theme.of(context).colorScheme.primary,
        ),
      ),
      title: Text(
        entranceLabel(elevator),
        style: Theme.of(
          context,
        ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
      ),
      subtitle: Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Учётный номер: ${inventoryLabel(elevator)}'),
            if (text(elevator, 'factory_number', '').isNotEmpty ||
                text(elevator, 'model', '').isNotEmpty)
              Text(
                [
                  if (text(elevator, 'factory_number', '').isNotEmpty)
                    'Зав. ${elevator['factory_number']}',
                  if (text(elevator, 'model', '').isNotEmpty)
                    text(elevator, 'model'),
                ].join(' · '),
              ),
            Text(text(elevator, 'technician_name', 'Механик не назначен')),
            if (elevator['stopped_at'] != null) const Text('Лифт остановлен'),
            if (elevator['active'] == false) const Text('Архив'),
          ],
        ),
      ),
      isThreeLine: true,
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    ),
  );
}

class ElevatorPage extends StatefulWidget {
  const ElevatorPage({
    super.key,
    required this.controller,
    required this.id,
    required this.organization,
    this.inspection = false,
  });
  final LiftController controller;
  final int id, organization;
  final bool inspection;
  @override
  State<ElevatorPage> createState() => _ElevatorPageState();
}

class _ElevatorPageState extends State<ElevatorPage> {
  List<Json> _documents = [];
  String _error = '';
  bool _loading = true, _opening = false;
  @override
  void initState() {
    super.initState();
    unawaited(_loadDocuments());
  }

  Future<void> _loadDocuments() async {
    try {
      final data = await widget.controller.resource(
        'elevators/${widget.id}/documents/',
        expectedOrganization: widget.organization,
      );
      if (mounted) {
        setState(() {
          _documents = records(data);
          _error = '';
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openDocument(Json d) async {
    setState(() => _opening = true);
    try {
      final bytes = await widget.controller.download(
        d['url'],
        widget.organization,
        pdf: true,
      );
      await PlatformBridge.openPdf(bytes);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: widget.controller,
    organization: widget.organization,
    builder: (context) {
      final c = widget.controller,
          e = c
              .list('elevators')
              .firstWhere((e) => e['id'] == widget.id, orElse: () => {});
      final tickets =
          c.list('tickets').where((t) => t['elevator'] == widget.id).toList()
            ..sort((a, b) => (b['id'] as int).compareTo(a['id'] as int));
      final maintenance = c
          .list('maintenance')
          .where((m) => m['elevator'] == widget.id && m['completed_at'] == null)
          .toList();
      final hasInspections = c.me['lift_documents_api'] == 1;
      return DefaultTabController(
        length: hasInspections ? 6 : 5,
        initialIndex: hasInspections && widget.inspection ? 5 : 0,
        child: Scaffold(
          appBar: AppBar(
            title: Text('Лифт ${liftLabel(e)}'),
            actions: [
              IconButton(
                tooltip: 'Фото и видео лифта',
                icon: const Icon(Icons.photo_library_outlined),
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute<void>(
                    builder: (_) =>
                        MediaPage(controller: c, elevator: widget.id),
                  ),
                ),
              ),
            ],
            bottom: TabBar(
              isScrollable: true,
              tabAlignment: TabAlignment.start,
              tabs: [
                const Tab(text: 'Карточка'),
                const Tab(text: 'Заявки'),
                const Tab(text: 'План ТО'),
                const Tab(text: 'Журнал ТО'),
                const Tab(text: 'Документация'),
                if (hasInspections) const Tab(text: 'Освидетельствование'),
              ],
            ),
          ),
          body: TabBarView(
            children: [
              ListView(
                key: const ValueKey('lift-passport'),
                padding: const EdgeInsets.all(18),
                children: [
                  Sheet(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          text(e, 'address'),
                          style: Theme.of(context).textTheme.titleLarge
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        const Divider(),
                        if (e['stopped_at'] != null) ...[
                          const StatusPill('STOPPED'),
                          const SizedBox(height: 8),
                          _info('Причина остановки', text(e, 'stop_reason')),
                          const Divider(),
                        ],
                        Text(
                          entranceLabel(e),
                          style: Theme.of(context).textTheme.titleLarge
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        _info('Учётный номер', inventoryLabel(e)),
                        _info(
                          'Заводской номер',
                          text(e, 'factory_number', 'Не указан'),
                        ),
                        if (e['next_inspection_on'] != null)
                          _info(
                            'Освидетельствование',
                            inspectionDateLabel(e['next_inspection_on']),
                          ),
                        _info(
                          'Производитель',
                          text(e, 'manufacturer', 'Не указан'),
                        ),
                        _info('Модель', text(e, 'model', 'Не указана')),
                        _info(
                          'Остановок лифта',
                          text(e, 'floors', 'Не указано'),
                        ),
                        _info(
                          'Этажность здания',
                          text(e, 'building_floors', 'Не указана'),
                        ),
                        _info(
                          'Ответственный',
                          text(e, 'technician_name', 'Не назначен'),
                        ),
                        if (text(e, 'documentation_tags', '').isNotEmpty)
                          _info(
                            'Теги документации',
                            text(e, 'documentation_tags'),
                          ),
                        if (text(e, 'notes', '').isNotEmpty) ...[
                          const Divider(),
                          SelectableText(text(e, 'notes')),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      if (c.me['can_manage'] == true && e.isNotEmpty)
                        OutlinedButton(
                          onPressed: c.canWrite
                              ? () async {
                                  await Navigator.push(
                                    context,
                                    MaterialPageRoute<void>(
                                      builder: (_) => _EditElevatorPage(
                                        controller: c,
                                        elevator: e,
                                        organization: widget.organization,
                                      ),
                                    ),
                                  );
                                  if (mounted) await _loadDocuments();
                                }
                              : null,
                          child: const Text('Изменить сведения'),
                        ),
                      if (c.me['can_create_ticket'] == true && e.isNotEmpty)
                        OutlinedButton.icon(
                          onPressed: c.canCreateTicket
                              ? () => Navigator.push(
                                  context,
                                  MaterialPageRoute<void>(
                                    builder: (_) => CreateTicketPage(
                                      controller: c,
                                      elevator: e,
                                    ),
                                  ),
                                )
                              : null,
                          icon: const Icon(Icons.add),
                          label: const Text('Создать заявку'),
                        ),
                      if (e.isNotEmpty)
                        OutlinedButton.icon(
                          onPressed: c.canWrite
                              ? () => Navigator.push(
                                  context,
                                  MaterialPageRoute<void>(
                                    builder: (_) => PartForm(
                                      controller: c,
                                      initialElevator: e,
                                    ),
                                  ),
                                )
                              : null,
                          icon: const Icon(Icons.inventory_2_outlined),
                          label: const Text('Нужна запчасть'),
                        ),
                      if (c.me['can_manage_access'] == true &&
                          e['active'] == true)
                        OutlinedButton(
                          onPressed: c.canWrite
                              ? () async {
                                  final saved = await archiveRecord(
                                    context,
                                    c,
                                    'elevators',
                                    e,
                                    widget.organization,
                                  );
                                  if (saved && context.mounted) {
                                    Navigator.pop(context);
                                  }
                                }
                              : null,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: Theme.of(
                              context,
                            ).colorScheme.error,
                          ),
                          child: const Text('Удалить из списка'),
                        ),
                    ],
                  ),
                ],
              ),
              ListView(
                padding: const EdgeInsets.all(18),
                children: [
                  if (tickets.isEmpty)
                    const EmptyState(
                      'Заявок пока нет',
                      'Вся история обращений по этому лифту будет здесь.',
                    ),
                  for (final t in tickets)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: TicketTile(
                        t,
                        controller: c,
                        onTap: () => openTicket(context, c, t['id'] as int),
                      ),
                    ),
                ],
              ),
              ListView(
                padding: const EdgeInsets.all(18),
                children: [
                  FilledButton.icon(
                    onPressed: c.canWrite && e['active'] == true
                        ? () => Navigator.push(
                            context,
                            MaterialPageRoute<void>(
                              builder: (_) =>
                                  MaintenanceForm(controller: c, elevator: e),
                            ),
                          )
                        : null,
                    icon: const Icon(Icons.add),
                    label: const Text('Запланировать работу'),
                  ),
                  const SizedBox(height: 16),
                  if (maintenance.isEmpty)
                    const EmptyState(
                      'Запланированных работ нет',
                      'Добавьте работу по ТО для этого лифта.',
                    ),
                  for (final m in maintenance)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: MaintenanceTile(controller: c, item: m),
                    ),
                ],
              ),
              ElevatorMaintenanceJournal(
                controller: c,
                elevatorId: widget.id,
                organization: widget.organization,
              ),
              ListView(
                padding: const EdgeInsets.all(18),
                children: [
                  const Text(
                    'Документы подобраны из общей библиотеки по тегам или производителю и модели.',
                  ),
                  const SizedBox(height: 14),
                  if (_loading)
                    const Center(child: CircularProgressIndicator()),
                  if (_error.isNotEmpty) ...[
                    Text(_error),
                    TextButton(
                      onPressed: _loadDocuments,
                      child: const Text('Повторить'),
                    ),
                  ],
                  if (!_loading && _documents.isEmpty)
                    const EmptyState(
                      'Документов пока нет',
                      'В библиотеке ещё нет подходящей документации.',
                      icon: Icons.folder_open_outlined,
                    ),
                  for (final d in _documents)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Card(
                        child: ListTile(
                          leading: const Icon(Icons.picture_as_pdf_outlined),
                          title: Text(text(d, 'title')),
                          subtitle: Text(
                            text(d, 'documentation_tags', '').isNotEmpty
                                ? text(d, 'documentation_tags')
                                : '${text(d, 'manufacturer', '')} ${text(d, 'model', '')}',
                          ),
                          trailing: const Icon(Icons.open_in_new),
                          onTap: _opening ? null : () => _openDocument(d),
                        ),
                      ),
                    ),
                  if (_opening) const LinearProgressIndicator(),
                ],
              ),
              if (hasInspections)
                ElevatorInspection(
                  controller: c,
                  elevator: widget.id,
                  organization: widget.organization,
                ),
            ],
          ),
        ),
      );
    },
  );
  Widget _info(String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 7),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: Text(label)),
        const SizedBox(width: 16),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ),
      ],
    ),
  );
}

class _EditElevatorPage extends StatefulWidget {
  const _EditElevatorPage({
    required this.controller,
    required this.elevator,
    required this.organization,
  });

  final LiftController controller;
  final Json elevator;
  final int organization;

  @override
  State<_EditElevatorPage> createState() => _EditElevatorPageState();
}

class _EditElevatorPageState extends State<_EditElevatorPage> {
  static const _fields = [
    (key: 'entrance', label: 'Подъезд', limit: 50, max: null),
    (key: 'inventory_number', label: 'Учётный номер', limit: 100, max: null),
    (key: 'factory_number', label: 'Заводской номер', limit: 100, max: null),
    (key: 'manufacturer', label: 'Производитель', limit: 150, max: null),
    (key: 'model', label: 'Модель', limit: 150, max: null),
    (key: 'floors', label: 'Остановок', limit: null, max: 32767),
    (
      key: 'building_floors',
      label: 'Этажность здания',
      limit: null,
      max: 32767,
    ),
    (
      key: 'capacity_kg',
      label: 'Грузоподъёмность, кг',
      limit: null,
      max: 2147483647,
    ),
    (
      key: 'documentation_tags',
      label: 'Теги документации через запятую',
      limit: 640,
      max: null,
    ),
    (key: 'notes', label: 'Примечания', limit: null, max: null),
  ];

  final _form = GlobalKey<FormState>();
  late final _inputs = {
    for (final field in _fields)
      field.key: TextEditingController(
        text: widget.elevator[field.key]?.toString() ?? '',
      ),
  };
  late int? _building = widget.elevator['building'] as int?;
  late bool _noInventory =
      widget.elevator['inventory_number_missing'] == true ||
      text(widget.elevator, 'inventory_number', '').toLowerCase() == 'нет';
  late int? _technician = widget.elevator['assigned_technician'] as int?;
  bool _saving = false;

  @override
  void dispose() {
    for (final controller in _inputs.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    final c = widget.controller;
    if (_saving ||
        !c.canWrite ||
        c.me['can_manage'] != true ||
        !_form.currentState!.validate()) {
      return;
    }

    final id = widget.elevator['id'];
    final changes = <String, dynamic>{
      if (_noInventory != (widget.elevator['inventory_number_missing'] == true))
        'inventory_number_missing': _noInventory,
      if (id == null || _building != widget.elevator['building'])
        'building': _building,
      if (_technician != widget.elevator['assigned_technician'])
        'assigned_technician': _technician,
    };
    for (final field in _fields) {
      if (field.key == 'inventory_number' && _noInventory) continue;
      final input = _inputs[field.key]!.text;
      if (input == (widget.elevator[field.key]?.toString() ?? '')) continue;
      final value = input.trim();
      changes[field.key] = field.max == null ? value : int.tryParse(value);
    }
    if (changes.isEmpty) {
      Navigator.pop(context);
      return;
    }

    setState(() => _saving = true);
    try {
      await c.request(
        id == null ? 'elevators/' : 'elevators/$id/',
        method: id == null ? 'POST' : 'PATCH',
        data: changes,
        expectedOrganization: widget.organization,
      );
      await c.refresh();
      if (mounted) Navigator.pop(context);
    } catch (error) {
      c.log.record('elevator_edit_failed');
      if (mounted) showError(context, error);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: widget.controller,
    organization: widget.organization,
    builder: (context) {
      final c = widget.controller;
      final enabled = !_saving && c.canWrite && c.me['can_manage'] == true;
      final buildings = {
        widget.elevator['building'] as int: text(widget.elevator, 'address'),
        for (final row in c.list('buildings'))
          row['id'] as int: text(row, 'address'),
      };
      final technicians = {
        if (widget.elevator['assigned_technician'] case final int id)
          id: text(widget.elevator, 'technician_name', 'Текущий механик'),
        for (final row in c.list('technicians'))
          if (row['active'] == true) row['id'] as int: text(row, 'full_name'),
      };

      return Scaffold(
        appBar: AppBar(
          title: Text(
            widget.elevator['id'] == null
                ? 'Добавить лифт'
                : 'Изменить сведения',
          ),
        ),
        bottomNavigationBar: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 8, 18, 12),
            child: FilledButton(
              onPressed: enabled ? _save : null,
              child: Text(_saving ? 'Сохранение…' : 'Сохранить'),
            ),
          ),
        ),
        body: Form(
          key: _form,
          child: SafeArea(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Autocomplete<MapEntry<int, String>>(
                    initialValue: TextEditingValue(
                      text: buildings[_building] ?? '',
                    ),
                    displayStringForOption: (row) => row.value,
                    optionsBuilder: (input) {
                      final query = _searchable(input.text);
                      return buildings.entries
                          .where(
                            (row) => _searchable(row.value).contains(query),
                          )
                          .take(25);
                    },
                    onSelected: (row) => setState(() => _building = row.key),
                    fieldViewBuilder: (context, controller, focus, submit) =>
                        TextFormField(
                          controller: controller,
                          focusNode: focus,
                          enabled: enabled,
                          decoration: const InputDecoration(
                            labelText: 'Дом',
                            hintText: 'Начните вводить адрес',
                          ),
                          onChanged: (value) {
                            if (value != buildings[_building]) _building = null;
                          },
                          onFieldSubmitted: (_) => submit(),
                          validator: (_) => _building == null
                              ? 'Выберите адрес из списка'
                              : null,
                        ),
                  ),
                  const SizedBox(height: 12),
                  for (final field in _fields.where(
                    (field) => field.key != 'notes',
                  )) ...[
                    _input(
                      field,
                      enabled &&
                          (field.key != 'inventory_number' || !_noInventory),
                    ),
                    if (field.key == 'inventory_number')
                      CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Учётного номера нет'),
                        value: _noInventory,
                        onChanged: enabled
                            ? (value) =>
                                  setState(() => _noInventory = value ?? false)
                            : null,
                      ),
                  ],
                  DropdownButtonFormField<int>(
                    initialValue: _technician ?? 0,
                    isExpanded: true,
                    decoration: const InputDecoration(
                      labelText: 'Ответственный механик',
                    ),
                    items: [
                      const DropdownMenuItem(
                        value: 0,
                        child: Text('Не назначен'),
                      ),
                      for (final entry in technicians.entries)
                        DropdownMenuItem(
                          value: entry.key,
                          child: Text(
                            entry.value,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                    ],
                    onChanged: enabled
                        ? (value) => setState(
                            () => _technician = value == 0 ? null : value,
                          )
                        : null,
                  ),
                  const SizedBox(height: 12),
                  _input(_fields.last, enabled),
                ],
              ),
            ),
          ),
        ),
      );
    },
  );

  Widget _input(
    ({String key, String label, int? limit, int? max}) field,
    bool enabled,
  ) {
    final max = field.max;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextFormField(
        controller: _inputs[field.key],
        enabled: enabled,
        maxLength: field.limit,
        minLines: field.key == 'notes' ? 2 : 1,
        maxLines: field.key == 'notes' ? 5 : 1,
        keyboardType: max != null
            ? TextInputType.number
            : field.key == 'notes'
            ? TextInputType.multiline
            : TextInputType.text,
        decoration: InputDecoration(labelText: field.label, counterText: ''),
        validator: max == null
            ? null
            : (input) {
                final value = input?.trim() ?? '';
                if (value.isEmpty) return null;
                final number = int.tryParse(value);
                return number == null || number < 1 || number > max
                    ? 'Укажите целое число от 1 до $max'
                    : null;
              },
      ),
    );
  }
}
