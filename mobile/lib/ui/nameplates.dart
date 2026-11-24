import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';
import 'media_widgets.dart';

class NameplatesPage extends StatefulWidget {
  const NameplatesPage({
    super.key,
    required this.controller,
    required this.project,
    required this.lift,
    required this.organization,
    this.archived = false,
  });
  final LiftController controller;
  final int project, organization;
  final Json lift;
  final bool archived;
  @override
  State<NameplatesPage> createState() => _NameplatesPageState();
}

class _NameplatesPageState extends State<NameplatesPage> {
  List<Json> _rows = [];
  bool _loading = true;
  String? _error;
  LiftController get c => widget.controller;
  String get _path =>
      'commissioning/${widget.project}/lifts/${widget.lift['id']}/nameplates/';
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final result = await c.request(
        _path,
        expectedOrganization: widget.organization,
      );
      if (mounted) {
        setState(() {
          _rows = records(result);
          _error = null;
        });
      }
    } catch (e) {
      c.log.record('nameplates_load_failed');
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _add() async {
    final input = TextEditingController();
    final photos = <XFile>[];
    var busy = false;
    String? error;
    String? operation;
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, update) => PopScope(
          canPop: !busy,
          child: AlertDialog(
            title: const Text('Шильдик устройства безопасности'),
            content: SizedBox(
              width: 440,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextField(
                      controller: input,
                      enabled: !busy,
                      maxLength: 1000,
                      minLines: 2,
                      maxLines: 5,
                      decoration: const InputDecoration(
                        labelText: 'Что за шильдик',
                        hintText: 'Например: ограничитель скорости',
                      ),
                      onChanged: (_) {
                        operation = null;
                        update(() {});
                      },
                    ),
                    Wrap(
                      spacing: 8,
                      children: [
                        for (final camera in [true, false])
                          TextButton.icon(
                            onPressed: busy
                                ? null
                                : () async {
                                    try {
                                      final picker = ImagePicker();
                                      final picked = camera
                                          ? [
                                              await picker.pickImage(
                                                source: ImageSource.camera,
                                                maxWidth: 2560,
                                                maxHeight: 2560,
                                                imageQuality: 90,
                                              ),
                                            ].whereType<XFile>().toList()
                                          : await picker.pickMultiImage(
                                              limit: 5,
                                              maxWidth: 2560,
                                              maxHeight: 2560,
                                              imageQuality: 90,
                                            );
                                      if (photos.length + picked.length >
                                          maxMultipartFiles) {
                                        throw const ApiError(
                                          'До 5 фотографий за загрузку.',
                                        );
                                      }
                                      for (final file in picked) {
                                        if (await file.length() > maxFileBytes) {
                                          throw const ApiError(
                                            'Фото должно быть до 100 МБ.',
                                          );
                                        }
                                      }
                                      if (context.mounted) {
                                        update(() {
                                          photos.addAll(picked);
                                          operation = null;
                                        });
                                      }
                                    } catch (e) {
                                      if (context.mounted) {
                                        update(() => error = '$e');
                                      }
                                    }
                                  },
                            icon: Icon(
                              camera
                                  ? Icons.camera_alt_outlined
                                  : Icons.photo_library_outlined,
                            ),
                            label: Text(camera ? 'Снять фото' : 'Из галереи'),
                          ),
                      ],
                    ),
                    for (final photo in photos)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(
                          photo.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        trailing: IconButton(
                          tooltip: 'Убрать фото',
                          onPressed: busy
                              ? null
                              : () => update(() {
                                  photos.remove(photo);
                                  operation = null;
                                }),
                          icon: const Icon(Icons.close),
                        ),
                      ),
                    if (error != null)
                      Text(
                        error!,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    if (busy) const LinearProgressIndicator(),
                  ],
                ),
              ),
            ),
            actions: [
              TextButton(
                onPressed: busy ? null : () => Navigator.pop(context),
                child: const Text('Отмена'),
              ),
              FilledButton(
                onPressed: busy || input.text.trim().isEmpty || photos.isEmpty
                    ? null
                    : () async {
                        update(() {
                          busy = true;
                          error = null;
                        });
                        try {
                          operation ??= c.newOperationId();
                          await c.postCommissioningPhotos(
                            _path,
                            {
                              'description': input.text.trim(),
                              'operation_id': operation!,
                            },
                            [
                              for (final photo in photos)
                                (
                                  bytes: await photo.readAsBytes(),
                                  name: photo.name,
                                ),
                            ],
                            expectedOrganization: widget.organization,
                          );
                          c.log.record('nameplates_uploaded');
                          if (context.mounted) Navigator.pop(context);
                          await _load();
                        } catch (e) {
                          c.log.record('nameplates_upload_failed');
                          if (context.mounted) {
                            update(() {
                              error = '$e';
                              busy = false;
                            });
                          }
                        }
                      },
                child: const Text('Сохранить'),
              ),
            ],
          ),
        ),
      ),
    );
    // Dialog route finishes its dismissal animation after this future resolves.
    Future<void>.delayed(const Duration(seconds: 1), input.dispose);
  }

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: c,
    organization: widget.organization,
    builder: (context) => Scaffold(
      appBar: AppBar(
        title: const Text('Шильдики'),
        actions: [
          IconButton(
            tooltip: 'Обновить',
            onPressed: _load,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              text(widget.lift, 'label'),
              style: Theme.of(context).textTheme.titleLarge,
            ),
            if (_loading) const LinearProgressIndicator(),
            if (_error != null)
              Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            if (!_loading && _rows.isEmpty && _error == null)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Text('Шильдики ещё не добавлены.'),
              ),
            for (final row in _rows)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      PrivateMedia(
                        key: ValueKey(row['id']),
                        controller: c,
                        organization: widget.organization,
                        attachment: row,
                      ),
                      SelectableText(
                        text(row, 'description'),
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        '${text(row, 'author')} · ${dateLabel(row['created_at'], c.utcOffset)}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
      bottomNavigationBar: widget.lift['can_edit'] == true && !widget.archived
          ? SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: FilledButton.icon(
                  onPressed: c.canWrite ? _add : null,
                  icon: const Icon(Icons.add_a_photo_outlined),
                  label: const Text('Прикрепить фото шильдика'),
                ),
              ),
            )
          : null,
    ),
  );
}
