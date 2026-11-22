import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';

void openBuildingEditor(
  BuildContext context,
  LiftController controller, {
  Json? building,
}) {
  Navigator.push(
    context,
    MaterialPageRoute<void>(
      builder: (_) => _BuildingEditor(
        controller: controller,
        organization: controller.organization!,
        building: building,
      ),
    ),
  );
}

Future<bool> deleteBuilding(
  BuildContext context,
  LiftController c,
  Json building,
  int organization,
) async {
  final occupied = c
      .list('elevators')
      .any((e) => e['building'] == building['id']);
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Удалить дом?'),
      content: Text(
        occupied
            ? 'Сначала перенесите лифты на другой адрес, включая архивные.'
            : text(building, 'address'),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Закрыть'),
        ),
        if (!occupied)
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Удалить дом'),
          ),
      ],
    ),
  );
  if (confirmed != true || !context.mounted) return false;
  try {
    await c.request(
      'buildings/${building['id']}/',
      method: 'DELETE',
      expectedOrganization: organization,
    );
    await c.refresh();
    return true;
  } catch (error) {
    c.log.record('building_delete_failed');
    if (context.mounted) showError(context, error);
    return false;
  }
}

class _BuildingEditor extends StatefulWidget {
  const _BuildingEditor({
    required this.controller,
    required this.organization,
    this.building,
  });

  final LiftController controller;
  final int organization;
  final Json? building;

  @override
  State<_BuildingEditor> createState() => _BuildingEditorState();
}

class _BuildingEditorState extends State<_BuildingEditor> {
  static const _fields = <String, (String, int)>{
    'name': ('Название', 200),
    'address': ('Адрес', 300),
    'street': ('Улица', 200),
    'house': ('Номер дома', 50),
    'management_company': ('Управляющая организация', 200),
    'contact_name': ('Контактное лицо', 150),
    'contact_phone': ('Телефон', 50),
  };
  final _form = GlobalKey<FormState>();
  late final _inputs = {
    for (final field in _fields.keys)
      field: TextEditingController(
        text: text(widget.building ?? {}, field, ''),
      ),
  };
  bool _saving = false;

  @override
  void dispose() {
    for (final controller in _inputs.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    if (_saving || !_form.currentState!.validate()) return;
    setState(() => _saving = true);
    final c = widget.controller;
    final id = widget.building?['id'];
    try {
      await c.request(
        id == null ? 'buildings/' : 'buildings/$id/',
        method: id == null ? 'POST' : 'PATCH',
        data: {
          for (final field in _inputs.entries)
            field.key: field.value.text.trim(),
        },
        expectedOrganization: widget.organization,
      );
      await c.refresh();
      if (mounted) Navigator.pop(context);
    } catch (error) {
      c.log.record('building_save_failed');
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
      final enabled =
          !_saving &&
          widget.controller.canWrite &&
          widget.controller.me['can_manage'] == true;
      return Scaffold(
        appBar: AppBar(
          title: Text(
            widget.building == null ? 'Добавить дом' : 'Изменить дом',
          ),
        ),
        body: Form(
          key: _form,
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(18),
            child: Column(
              children: [
                for (final entry in _fields.entries)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: TextFormField(
                      controller: _inputs[entry.key],
                      enabled: enabled,
                      maxLength: entry.value.$2,
                      decoration: InputDecoration(
                        labelText: entry.value.$1,
                        counterText: '',
                      ),
                      validator: (value) =>
                          (entry.key == 'name' || entry.key == 'address') &&
                              (value == null || value.trim().isEmpty)
                          ? 'Заполните поле'
                          : null,
                    ),
                  ),
              ],
            ),
          ),
        ),
        bottomNavigationBar: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 8, 18, 12),
            child: FilledButton(
              onPressed: enabled ? _save : null,
              child: const Text('Сохранить'),
            ),
          ),
        ),
      );
    },
  );
}
