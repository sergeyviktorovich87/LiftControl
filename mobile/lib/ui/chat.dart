import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';
import 'media_widgets.dart';
import 'media_library.dart';
import 'tickets.dart';
import 'extras.dart';
import 'dart:async';
import 'message_receipts.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({
    super.key,
    required this.controller,
    this.messageId,
    this.quoteKind,
    this.quoteId,
    this.quoteTitle,
    this.commissioning = false,
  });
  final LiftController controller;
  final bool commissioning;
  final int? messageId;
  final String? quoteKind;
  final int? quoteId;
  final String? quoteTitle;
  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final _input = TextEditingController();
  late final int _org;
  final _files = <XFile>[];
  bool _busy = false;
  bool _loadingMessages = false, _markingRead = false;
  int _readThrough = 0;
  final _delivered = <int>{};
  Timer? _poll;
  String? _loadError;
  String? _operationId;
  List<Json> _roomRows = [];
  Json? _selected;
  Json? _quote;
  bool get _canRecord => widget.commissioning
      ? c.canWrite && c.me['can_commissioning'] == true
      : c.me['media_api'] == 1
      ? c.canRecord
      : c.canWrite;
  LiftController get c => widget.controller;
  String get _path => widget.commissioning ? 'commissioning/chat/' : 'chat/';
  bool get _isVisible =>
      mounted &&
      ModalRoute.of(context)?.isCurrent != false &&
      (WidgetsBinding.instance.lifecycleState ?? AppLifecycleState.resumed) ==
          AppLifecycleState.resumed;
  List<Json> get _rows => widget.messageId != null
      ? [?_selected]
      : widget.commissioning
      ? _roomRows
      : c.list('chat');

  @override
  void initState() {
    super.initState();
    _org = c.organization!;
    if (widget.quoteKind != null && widget.quoteId != null) {
      _quote = {
        'kind': widget.quoteKind,
        'id': widget.quoteId,
        'title': widget.quoteTitle ?? 'Карточка',
      };
    }
    if (!widget.commissioning && widget.messageId == null) {
      c.addListener(_scheduleRead);
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_reload());
    });
    if (widget.messageId == null) {
      _poll = Timer.periodic(const Duration(seconds: 8), (_) {
        if (_isVisible && c.canWrite && !_busy) unawaited(_reload());
      });
    }
  }

  Future<void> _reload() async {
    if (_loadingMessages || !mounted || c.organization != _org) return;
    _loadingMessages = true;
    try {
      final id = widget.messageId;
      if (id != null || widget.commissioning) {
        final path = id == null ? _path : '$_path$id/';
        final value = widget.commissioning
            ? await c.request(path, expectedOrganization: _org)
            : await c.resource(path, expectedOrganization: _org);
        if (!mounted || c.organization != _org) return;
        setState(() {
          _loadError = null;
          if (id == null) {
            _roomRows = records(value);
          } else {
            _selected = Map<String, dynamic>.from(value as Map);
          }
        });
      } else {
        await c.refresh();
      }
      _scheduleRead();
    } catch (e) {
      c.log.record('chat_load_failed', route: _path);
      if (mounted) {
        setState(() {
          _loadError = '$e';
          if (e is ApiError && (e.status == 403 || e.status == 404)) {
            _roomRows = [];
            _selected = null;
          }
        });
      }
    } finally {
      _loadingMessages = false;
    }
  }

  void _scheduleRead() {
    if (!mounted ||
        _markingRead ||
        !c.canWrite ||
        c.organization != _org ||
        c.me['notification_counts_api'] != 1) {
      return;
    }
    if (c.me['message_receipts_api'] == 1) {
      final ids = _rows
          .where(
            (r) => r['delivery_state'] == null && r['author'] != c.me['id'],
          )
          .map((r) => r['id'])
          .whereType<int>()
          .where((id) => !_delivered.contains(id))
          .toList();
      if (ids.isEmpty) return;
      _markingRead = true;
      unawaited(
        c
            .request(
              'notifications/receipts/',
              method: 'POST',
              expectedOrganization: _org,
              data: {
                'target': widget.commissioning ? 'commissioning_chat' : 'chat',
                'ids': ids.take(200).toList(),
              },
            )
            .then((_) {
              _delivered.addAll(ids.take(200));
            })
            .catchError((Object e) {
              c.log.record('chat_delivery_failed');
            })
            .whenComplete(() {
              _markingRead = false;
            }),
      );
      return;
    }
    final through = _rows
        .where((row) => row['delivery_state'] == null)
        .map((row) => row['id'])
        .whereType<int>()
        .fold(_readThrough, (last, id) => id > last ? id : last);
    if (through <= _readThrough) return;
    _markingRead = true;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      try {
        if (!_isVisible || c.organization != _org) return;
        await c.request(
          'notifications/read-chat/',
          method: 'POST',
          expectedOrganization: _org,
          data: {
            'target': widget.commissioning ? 'commissioning_chat' : 'chat',
            'through': through,
            'only': widget.messageId != null,
          },
        );
        _readThrough = through;
        unawaited(c.refreshNotificationCounts());
      } catch (_) {
        c.log.record('chat_read_sync_failed', route: _path);
      } finally {
        _markingRead = false;
      }
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  @override
  void dispose() {
    _poll?.cancel();
    c.removeListener(_scheduleRead);
    _input.dispose();
    super.dispose();
  }

  Future<void> _chooseQuote() async {
    final next = await showModalBottomSheet<Json>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            const ListTile(title: Text('Цитировать заявку или запчасть')),
            for (final ticket in c.list('tickets'))
              ListTile(
                leading: const Icon(Icons.assignment_outlined),
                title: Text('#${ticket['id']} · ${text(ticket, 'title')}'),
                subtitle: Text(text(ticket, 'address')),
                onTap: () => Navigator.pop(sheetContext, {
                  'kind': 'ticket',
                  'id': ticket['id'],
                  'title': text(ticket, 'title'),
                }),
              ),
            for (final part in c.list('parts'))
              ListTile(
                leading: const Icon(Icons.inventory_2_outlined),
                title: Text('#${part['id']} · ${text(part, 'part')}'),
                subtitle: Text(text(part, 'address')),
                onTap: () => Navigator.pop(sheetContext, {
                  'kind': 'part',
                  'id': part['id'],
                  'title': text(part, 'part'),
                }),
              ),
          ],
        ),
      ),
    );
    if (next != null && mounted) setState(() => _quote = next);
  }

  Future<void> _openQuote(Json reference) async {
    final id = reference['id'];
    if (id is! int) return;
    if (reference['kind'] == 'ticket') {
      openTicket(context, c, id);
      return;
    }
    if (reference['kind'] == 'part') {
      try {
        final result = await c.resource(
          'parts/$id/',
          expectedOrganization: _org,
        );
        if (!mounted) return;
        Navigator.push(
          context,
          MaterialPageRoute<void>(
            builder: (_) => PartForm(
              controller: c,
              item: Map<String, dynamic>.from(result),
            ),
          ),
        );
      } catch (e) {
        if (mounted) showError(context, e);
      }
    }
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
              if (!widget.commissioning) ...[
                ('video-camera', 'Снять видео', Icons.videocam_outlined),
                (
                  'video-gallery',
                  'Видео из галереи',
                  Icons.video_library_outlined,
                ),
              ],
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
      if (next.length > maxMultipartFiles) {
        throw const ApiError('До 5 вложений на сообщение.');
      }
      for (final file in next) {
        if (await file.length() > maxFileBytes) {
          throw const ApiError('Размер вложения должен быть до 100 МБ.');
        }
      }
      if (mounted && c.organization == _org) {
        setState(() {
          _operationId = null;
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
    if (_busy || _input.text.trim().isEmpty && _files.isEmpty && _quote == null) {
      return;
    }
    setState(() => _busy = true);
    try {
      final operation = widget.commissioning
          ? _operationId ??= c.newOperationId()
          : null;
      if (_files.isEmpty) {
        await c.request(
          _path,
          method: 'POST',
          data: {
            'body': _input.text.trim(),
            'operation_id': ?operation,
            if (_quote?['kind'] == 'ticket') 'linked_ticket': _quote?['id'],
            if (_quote?['kind'] == 'part') 'linked_part': _quote?['id'],
          },
          expectedOrganization: _org,
        );
      } else if (!widget.commissioning && c.me['media_api'] == 1) {
        await c.queueChatFiles(
          [
            for (final file in _files)
              (name: file.name, read: file.readAsBytes),
          ],
          expectedOrganization: _org,
          body: _input.text.trim(),
          linkedTicket: _quote?['kind'] == 'ticket'
              ? (_quote?['id'] as int?)
              : null,
          linkedPart: _quote?['kind'] == 'part'
              ? (_quote?['id'] as int?)
              : null,
        );
      } else {
        final files = [
          for (final file in _files)
            (bytes: await file.readAsBytes(), name: file.name),
        ];
        await c.uploadMedia(
          _path,
          files,
          _org,
          field: widget.commissioning ? 'photos' : 'files',
          fields: {
            'body': _input.text.trim(),
            'operation_id': ?operation,
            if (_quote?['kind'] == 'ticket')
              'linked_ticket': '${_quote?['id']}',
            if (_quote?['kind'] == 'part') 'linked_part': '${_quote?['id']}',
          },
        );
      }
      if (mounted) {
        _input.clear();
        setState(() {
          _files.clear();
          _quote = null;
          _operationId = null;
        });
      }
      if (widget.commissioning) {
        c.log.record('commissioning_chat_sent');
        await _reload();
      } else if (c.me['media_api'] != 1) {
        await c.refresh();
      }
    } catch (e) {
      c.log.record('chat_send_failed', route: _path);
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
      if (widget.commissioning && c.me['can_commissioning'] != true) {
        return Scaffold(
          appBar: AppBar(),
          body: const EmptyState(
            'Чат недоступен',
            'Проверьте доступ к наладке.',
          ),
        );
      }
      final rows = _rows;
      return Scaffold(
        appBar: AppBar(
          title: Text(widget.commissioning ? 'Чат наладчиков' : 'Чат бригады'),
          actions: [
            if (!widget.commissioning)
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
                    builder: (_) => ChatPage(
                      controller: c,
                      commissioning: widget.commissioning,
                    ),
                  ),
                ),
                child: const Text('Весь чат'),
              ),
            IconButton(
              tooltip: 'Обновить',
              onPressed: _reload,
              icon: const Icon(Icons.sync),
            ),
          ],
        ),
        body: SafeArea(
          child: Column(
            children: [
              if (_loadError != null)
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(
                    _loadError!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
              Expanded(
                child: rows.isEmpty
                    ? EmptyState(
                        'Сообщений пока нет',
                        widget.commissioning
                            ? 'Чат видят сотрудники с доступом к наладке.'
                            : 'Чат видят сотрудники этой организации.',
                        icon: Icons.chat_bubble_outline,
                      )
                    : ListView.builder(
                        reverse: true,
                        padding: const EdgeInsets.all(14),
                        itemCount: rows.length,
                        itemBuilder: (context, index) {
                          final row = rows[rows.length - index - 1],
                              own = row['author'] == c.me['id'];
                          final bubble = Align(
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
                                  if (row['reference'] is Map)
                                    ListTile(
                                      contentPadding: EdgeInsets.zero,
                                      leading: Icon(
                                        row['reference']['kind'] == 'ticket'
                                            ? Icons.assignment_outlined
                                            : Icons.inventory_2_outlined,
                                      ),
                                      title: Text(
                                        '${row['reference']['kind'] == 'ticket' ? 'Заявка' : 'Запчасть'} #${row['reference']['id']} · ${row['reference']['title']}',
                                      ),
                                      subtitle: Text(
                                        '${row['reference']['address']} · ${row['reference']['status']}',
                                      ),
                                      onTap: () => _openQuote(
                                        Map<String, dynamic>.from(
                                          row['reference'],
                                        ),
                                      ),
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
                                  if (own && row['receipt'] is Map)
                                    Text(
                                      receiptLabel(row['receipt'] as Map),
                                      style: TextStyle(
                                        fontSize: 11,
                                        color:
                                            (row['receipt']['read'] as int? ??
                                                    0) >
                                                0
                                            ? Theme.of(
                                                context,
                                              ).colorScheme.primary
                                            : null,
                                      ),
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
                          if (own ||
                              row['id'] is! int ||
                              (row['id'] as int) <= 0) {
                            return bubble;
                          }
                          return ReceiptSeen(
                            key: ValueKey(row['id']),
                            controller: c,
                            organization: _org,
                            target: widget.commissioning
                                ? 'commissioning_chat'
                                : 'chat',
                            id: row['id'] as int,
                            child: bubble,
                          );
                        },
                      ),
              ),
              if (_quote != null)
                ListTile(
                  leading: const Icon(Icons.link_outlined),
                  title: Text(
                    '${_quote?['kind'] == 'ticket' ? 'Заявка' : 'Запчасть'} #${_quote?['id']}',
                  ),
                  subtitle: Text(text(_quote!, 'title')),
                  trailing: IconButton(
                    icon: const Icon(Icons.close),
                    tooltip: 'Убрать ссылку',
                    onPressed: _busy
                        ? null
                        : () => setState(() => _quote = null),
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
                                  : () => setState(() {
                                      _files.removeAt(index);
                                      _operationId = null;
                                    }),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              if (!widget.commissioning && c.me['field_ops_api'] == 1)
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 14),
                  child: Text(
                    'Фото до 100 МБ; видео до 100 МБ и 3 минут.',
                    style: TextStyle(fontSize: 11),
                  ),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(8, 8, 8, 12),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    if (!widget.commissioning)
                      IconButton(
                        tooltip: 'Цитировать заявку или запчасть',
                        onPressed: _canRecord && !_busy ? _chooseQuote : null,
                        icon: const Icon(Icons.link_outlined),
                      ),
                    if (widget.commissioning || c.me['field_ops_api'] == 1)
                      IconButton(
                        tooltip: widget.commissioning
                            ? 'Прикрепить фото'
                            : 'Фото и видео',
                        onPressed: _canRecord && !_busy ? _pick : null,
                        icon: const Icon(Icons.attach_file),
                      ),
                    Expanded(
                      child: TextField(
                        key: const Key('chat_message'),
                        controller: _input,
                        enabled: !_busy,
                        onChanged: (_) => _operationId = null,
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
