import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';
import 'media_widgets.dart';
import 'media_library.dart';
import 'dart:async';

class ChatPage extends StatefulWidget {
  const ChatPage({super.key, required this.controller, this.messageId});
  final LiftController controller;
  final int? messageId;
  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final _input = TextEditingController();
  late final int _org;
  final _files = <XFile>[];
  bool _busy = false;
  Json? _selected;
  bool get _canRecord => c.me['media_api'] == 1 ? c.canRecord : c.canWrite;
  LiftController get c => widget.controller;
  @override
  void initState() {
    super.initState();
    _org = c.organization!;
    if (widget.messageId != null) unawaited(_loadMessage());
  }

  Future<void> _loadMessage() async {
    try {
      final value = await c.resource(
        'chat/${widget.messageId}/',
        expectedOrganization: _org,
      );
      if (mounted) setState(() => _selected = Map<String, dynamic>.from(value));
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  Future<void> _pick() async {
    final source = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final item in [
              ('photo-camera', 'Сделать фото', Icons.camera_alt_outlined),
              (
                'photo-gallery',
                'Фото из галереи',
                Icons.photo_library_outlined,
              ),
              ('video-camera', 'Снять видео', Icons.videocam_outlined),
              (
                'video-gallery',
                'Видео из галереи',
                Icons.video_library_outlined,
              ),
            ])
              ListTile(
                leading: Icon(item.$3),
                title: Text(item.$2),
                onTap: () => Navigator.pop(context, item.$1),
              ),
          ],
        ),
      ),
    );
    if (source == null || !mounted || !_canRecord) return;
    setState(() => _busy = true);
    try {
      final picker = ImagePicker();
      List<XFile> picked = [];
      if (source == 'photo-gallery') {
        picked = await picker.pickMultiImage(
          maxWidth: 1920,
          maxHeight: 1920,
          imageQuality: 78,
        );
      } else if (source == 'photo-camera') {
        final file = await picker.pickImage(
          source: ImageSource.camera,
          maxWidth: 1920,
          maxHeight: 1920,
          imageQuality: 78,
        );
        if (file != null) picked = [file];
      } else {
        final file = await picker.pickVideo(
          source: source == 'video-camera'
              ? ImageSource.camera
              : ImageSource.gallery,
          maxDuration: const Duration(minutes: 3),
        );
        if (file != null) picked = [file];
      }
      if (picked.isNotEmpty && source.startsWith('photo-')) {
        c.log.record('photo_prepared');
      }
      final next = [..._files, ...picked];
      var size = 0;
      for (final file in next) {
        size += await file.length();
      }
      if (next.length > 5 || size > 20 * 1024 * 1024) {
        throw const ApiError('До 5 вложений и 20 МБ на сообщение.');
      }
      if (mounted && c.organization == _org) {
        setState(() {
          _files.clear();
          _files.addAll(next);
        });
      }
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _send() async {
    if (_busy || _input.text.trim().isEmpty && _files.isEmpty) return;
    setState(() => _busy = true);
    try {
      if (_files.isEmpty) {
        await c.request(
          'chat/',
          method: 'POST',
          data: {'body': _input.text.trim()},
          expectedOrganization: _org,
        );
      } else {
        final files = [
          for (final file in _files)
            (bytes: await file.readAsBytes(), name: file.name),
        ];
        await c.uploadMedia(
          'chat/',
          files,
          _org,
          fields: {'body': _input.text.trim()},
        );
      }
      if (mounted) {
        _input.clear();
        setState(_files.clear);
      }
      if (c.me['media_api'] != 1) await c.refresh();
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => ScopePage(
    controller: c,
    organization: _org,
    builder: (context) {
      final rows = widget.messageId == null
          ? c.list('chat')
          : _selected == null
          ? <Json>[]
          : [_selected!];
      return Scaffold(
        appBar: AppBar(
          title: const Text('Чат бригады'),
          actions: [
            IconButton(
              tooltip: 'Вложения чата',
              onPressed: () => Navigator.push(
                context,
                MaterialPageRoute<void>(
                  builder: (_) => MediaPage(controller: c, chat: true),
                ),
              ),
              icon: const Icon(Icons.photo_library_outlined),
            ),
            if (widget.messageId != null)
              TextButton(
                onPressed: () => Navigator.pushReplacement(
                  context,
                  MaterialPageRoute<void>(
                    builder: (_) => ChatPage(controller: c),
                  ),
                ),
                child: const Text('Весь чат'),
              ),
            IconButton(
              tooltip: 'Обновить',
              onPressed: c.refresh,
              icon: const Icon(Icons.sync),
            ),
          ],
        ),
        body: SafeArea(
          child: Column(
            children: [
              Expanded(
                child: rows.isEmpty
                    ? const EmptyState(
                        'Сообщений пока нет',
                        'Чат видят сотрудники этой организации.',
                        icon: Icons.chat_bubble_outline,
                      )
                    : ListView.builder(
                        reverse: true,
                        padding: const EdgeInsets.all(14),
                        itemCount: rows.length,
                        itemBuilder: (context, index) {
                          final row = rows[rows.length - index - 1],
                              own = row['author'] == c.me['id'];
                          return Align(
                            alignment: own
                                ? Alignment.centerRight
                                : Alignment.centerLeft,
                            child: Container(
                              constraints: const BoxConstraints(maxWidth: 560),
                              margin: const EdgeInsets.only(bottom: 12),
                              padding: const EdgeInsets.all(15),
                              decoration: BoxDecoration(
                                color: own
                                    ? Theme.of(context).colorScheme.primary
                                          .withValues(alpha: 0.12)
                                    : Theme.of(context).colorScheme.surface,
                                borderRadius: BorderRadius.circular(18),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    text(row, 'author_name'),
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w700,
                                      fontSize: 12,
                                    ),
                                  ),
                                  if (row['delivery_state'] != null)
                                    Text(
                                      '${row['delivery_state']}',
                                      style: const TextStyle(fontSize: 11),
                                    ),
                                  if (text(row, 'body', '').isNotEmpty)
                                    SelectableText(text(row, 'body')),
                                  for (final attachment in records(
                                    row['attachments'] ?? [],
                                  ))
                                    PrivateMedia(
                                      key: ValueKey(attachment['id']),
                                      controller: c,
                                      organization: _org,
                                      attachment: attachment,
                                    ),
                                  const SizedBox(height: 6),
                                  Text(
                                    dateLabel(row['created_at'], c.utcOffset),
                                    style: Theme.of(
                                      context,
                                    ).textTheme.bodySmall,
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
              ),
              if (_files.isNotEmpty)
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 100),
                  child: SingleChildScrollView(
                    child: Wrap(
                      children: [
                        for (var index = 0; index < _files.length; index++)
                          Padding(
                            padding: const EdgeInsets.only(left: 8),
                            child: InputChip(
                              label: ConstrainedBox(
                                constraints: const BoxConstraints(
                                  maxWidth: 180,
                                ),
                                child: Text(
                                  _files[index].name,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              onDeleted: _busy
                                  ? null
                                  : () =>
                                        setState(() => _files.removeAt(index)),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              if (c.me['field_ops_api'] == 1)
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 14),
                  child: Text(
                    'Фото до 10 МБ; видео до 20 МБ и 3 минут.',
                    style: TextStyle(fontSize: 11),
                  ),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(8, 8, 8, 12),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    if (c.me['field_ops_api'] == 1)
                      IconButton(
                        tooltip: 'Фото и видео',
                        onPressed: _canRecord && !_busy ? _pick : null,
                        icon: const Icon(Icons.attach_file),
                      ),
                    Expanded(
                      child: TextField(
                        key: const Key('chat_message'),
                        controller: _input,
                        enabled: !_busy,
                        minLines: 1,
                        maxLines: 5,
                        maxLength: 4000,
                        decoration: const InputDecoration(
                          hintText: 'Сообщение',
                          counterText: '',
                        ),
                      ),
                    ),
                    const SizedBox(width: 7),
                    IconButton.filled(
                      tooltip: 'Отправить',
                      onPressed: _canRecord && !_busy ? _send : null,
                      icon: _busy
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.send_outlined),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    },
  );
}
