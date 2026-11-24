import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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
  final _scroll = ScrollController();
  final _focus = FocusNode();
  Json? _reply, _pinned;
  bool _searching = false;
  String _query = '';
  int _lastMessageId = 0, _newMessages = 0;
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
    _scroll.addListener(() {
      if (_scroll.offset < 80 && _newMessages > 0) {
        setState(() => _newMessages = 0);
      }
    });
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
      if (!widget.commissioning && c.me['chat_design_api'] == 1) {
        final pin = await c.request('chat/pinned/', expectedOrganization: _org);
        if (mounted && c.organization == _org) {
          setState(
            () => _pinned = pin is Map && pin['message'] is Map
                ? Map<String, dynamic>.from(pin['message'] as Map)
                : null,
          );
        }
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
    _scroll.dispose();
    _focus.dispose();
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
              if (!widget.commissioning)
                ('card', 'Карточка заявки или запчасти', Icons.link_outlined),
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
    if (source == 'card') {
      await _chooseQuote();
      return;
    }
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
    if (_busy ||
        _input.text.trim().isEmpty && _files.isEmpty && _quote == null) {
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
            if (_reply != null && !widget.commissioning)
              'reply_to': _reply!['id'],
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
          replyTo: _reply?['id'] as int?,
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
            if (_reply != null && !widget.commissioning)
              'reply_to': '${_reply!['id']}',
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
          _reply = null;
          _operationId = null;
        });
      }
      if (_scroll.hasClients) _scroll.jumpTo(0);
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

  String _time(dynamic value) {
    final date = DateTime.tryParse(
      '$value',
    )?.toUtc().add(Duration(minutes: c.utcOffset));
    return date == null
        ? ''
        : '${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';
  }

  String _day(dynamic value) {
    final date = DateTime.tryParse(
      '$value',
    )?.toUtc().add(Duration(minutes: c.utcOffset));
    return date == null
        ? ''
        : '${date.day.toString().padLeft(2, '0')}.${date.month.toString().padLeft(2, '0')}.${date.year}';
  }

  void _replyTo(Json row) {
    if (widget.commissioning ||
        c.me['chat_design_api'] != 1 ||
        (row['id'] as int? ?? 0) <= 0) {
      return;
    }
    setState(() => _reply = row);
    _focus.requestFocus();
  }

  Future<void> _messageActions(Json row) async {
    final action = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (!widget.commissioning &&
                c.me['chat_design_api'] == 1 &&
                (row['id'] as int? ?? 0) > 0)
              ListTile(
                leading: const Icon(Icons.reply),
                title: const Text('Ответить'),
                onTap: () => Navigator.pop(context, 'reply'),
              ),
            if (text(row, 'body', '').isNotEmpty)
              ListTile(
                leading: const Icon(Icons.copy),
                title: const Text('Копировать'),
                onTap: () => Navigator.pop(context, 'copy'),
              ),
            if (!widget.commissioning &&
                c.me['chat_design_api'] == 1 &&
                c.me['can_export_chat'] == true &&
                (row['id'] as int? ?? 0) > 0)
              ListTile(
                leading: const Icon(Icons.push_pin_outlined),
                title: Text(row['pinned'] == true ? 'Открепить' : 'Закрепить'),
                onTap: () => Navigator.pop(context, 'pin'),
              ),
          ],
        ),
      ),
    );
    if (!mounted) return;
    if (action == 'reply') _replyTo(row);
    if (action == 'copy') {
      await Clipboard.setData(ClipboardData(text: text(row, 'body', '')));
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Текст скопирован')));
      }
    }
    if (action == 'pin') {
      try {
        await c.request(
          'chat/${row['id']}/pin/',
          method: 'POST',
          data: {'pinned': row['pinned'] != true},
          expectedOrganization: _org,
        );
        await _reload();
      } catch (e) {
        if (mounted) showError(context, e);
      }
    }
  }

  void _openMessage(int id) {
    Navigator.push(
      context,
      MaterialPageRoute<void>(
        builder: (_) => ChatPage(
          controller: c,
          messageId: id,
          commissioning: widget.commissioning,
        ),
      ),
    );
  }

  void _syncViewport(List<Json> rows) {
    final maxId = rows
        .map((r) => r['id'])
        .whereType<int>()
        .fold(0, (a, b) => a > b ? a : b);
    if (_lastMessageId > 0 &&
        maxId > _lastMessageId &&
        _scroll.hasClients &&
        _scroll.offset > 80 &&
        !_searching) {
      final offset = _scroll.offset, extent = _scroll.position.maxScrollExtent;
      _newMessages += rows
          .where(
            (r) =>
                (r['id'] as int? ?? 0) > _lastMessageId &&
                r['author'] != c.me['id'],
          )
          .length;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _scroll.hasClients) {
          _scroll.jumpTo(
            (offset + _scroll.position.maxScrollExtent - extent).clamp(
              0,
              _scroll.position.maxScrollExtent,
            ),
          );
        }
      });
    }
    _lastMessageId = maxId;
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
      final scheme = Theme.of(context).colorScheme;
      final dark = Theme.of(context).brightness == Brightness.dark;
      final blue = dark ? const Color(0xff8fc2ff) : const Color(0xff1269cc);
      final canvas = dark ? const Color(0xff172433) : const Color(0xffeef3fa);
      _syncViewport(_rows);
      final rows = _rows
          .where(
            (row) =>
                !_searching ||
                _query.isEmpty ||
                '${row['body']} ${row['author_name']}'.toLowerCase().contains(
                  _query.toLowerCase(),
                ),
          )
          .toList();
      final canSend =
          _canRecord &&
          !_busy &&
          (_input.text.trim().isNotEmpty ||
              _files.isNotEmpty ||
              _quote != null);
      return Scaffold(
        backgroundColor: canvas,
        appBar: AppBar(
          backgroundColor: scheme.surface,
          titleSpacing: 0,
          title: Row(
            children: [
              CircleAvatar(
                radius: 18,
                backgroundColor: blue,
                child: Icon(
                  Icons.groups_outlined,
                  color: dark ? Colors.black : Colors.white,
                  size: 21,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.commissioning ? 'Чат наладчиков' : 'Чат',
                      style: const TextStyle(
                        fontSize: 19,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      text(c.me, 'organization', ''),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 12,
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          actions: [
            PopupMenuButton<String>(
              tooltip: 'Меню чата',
              onSelected: (value) {
                if (value == 'search') {
                  setState(() {
                    _searching = !_searching;
                    _query = '';
                  });
                }
                if (value == 'refresh') _reload();
                if (value == 'media') {
                  Navigator.push(
                    context,
                    MaterialPageRoute<void>(
                      builder: (_) => MediaPage(controller: c, chat: true),
                    ),
                  );
                }
              },
              itemBuilder: (_) => [
                const PopupMenuItem(
                  value: 'search',
                  child: Text('Поиск в чате'),
                ),
                if (!widget.commissioning)
                  const PopupMenuItem(value: 'media', child: Text('Вложения')),
                const PopupMenuItem(value: 'refresh', child: Text('Обновить')),
              ],
            ),
          ],
        ),
        body: SafeArea(
          top: false,
          child: Column(
            children: [
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
              if (_searching)
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 6, 12, 6),
                  child: TextField(
                    autofocus: true,
                    decoration: InputDecoration(
                      hintText: 'Текст или автор',
                      prefixIcon: const Icon(Icons.search),
                      suffixIcon: IconButton(
                        tooltip: 'Закрыть поиск',
                        onPressed: () => setState(() {
                          _searching = false;
                          _query = '';
                        }),
                        icon: const Icon(Icons.close),
                      ),
                    ),
                    onChanged: (value) => setState(() => _query = value),
                  ),
                ),
              if (_pinned != null)
                Material(
                  color: dark
                      ? const Color(0xff203f60)
                      : const Color(0xffe0edff),
                  child: InkWell(
                    onTap: () => _openMessage(_pinned!['id'] as int),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 10,
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.push_pin, size: 18, color: blue),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              'Закреплено · ${text(_pinned!, 'body', 'Вложение')}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(color: blue, fontSize: 13),
                            ),
                          ),
                          Icon(Icons.chevron_right, color: blue, size: 18),
                        ],
                      ),
                    ),
                  ),
                ),
              if (_loadError != null)
                Padding(
                  padding: const EdgeInsets.all(10),
                  child: Text(
                    _loadError!,
                    style: TextStyle(color: scheme.error),
                  ),
                ),
              Expanded(
                child: Stack(
                  children: [
                    if (rows.isEmpty)
                      EmptyState(
                        _searching ? 'Ничего не найдено' : 'Сообщений пока нет',
                        _searching
                            ? 'Поиск по загруженной переписке.'
                            : 'Общий чат сотрудников организации.',
                        icon: Icons.chat_bubble_outline,
                      )
                    else
                      ListView.builder(
                        controller: _scroll,
                        reverse: true,
                        padding: const EdgeInsets.fromLTRB(10, 16, 10, 18),
                        itemCount: rows.length,
                        itemBuilder: (context, index) {
                          final row = rows[rows.length - index - 1],
                              own = row['author'] == c.me['id'];
                          final date = _day(row['created_at']);
                          final showDay =
                              index == rows.length - 1 ||
                              _day(
                                    rows[rows.length - index - 2]['created_at'],
                                  ) !=
                                  date;
                          final reply = row['reply'] is Map
                              ? Map<String, dynamic>.from(row['reply'] as Map)
                              : null;
                          final bubble = GestureDetector(
                            onLongPress: () => _messageActions(row),
                            onHorizontalDragEnd: (details) {
                              if ((details.primaryVelocity ?? 0) > 200) {
                                _replyTo(row);
                              }
                            },
                            child: Container(
                              padding: const EdgeInsets.fromLTRB(12, 9, 12, 7),
                              decoration: BoxDecoration(
                                color: own
                                    ? (dark
                                          ? const Color(0xff234f7e)
                                          : const Color(0xffd5e8ff))
                                    : scheme.surface,
                                borderRadius: BorderRadius.circular(17),
                                border: Border.all(
                                  color: dark
                                      ? const Color(0xff334860)
                                      : const Color(0xffdbe4ef),
                                ),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  if (!own)
                                    Padding(
                                      padding: const EdgeInsets.only(bottom: 4),
                                      child: Text(
                                        text(row, 'author_name'),
                                        style: TextStyle(
                                          fontWeight: FontWeight.w700,
                                          fontSize: 13,
                                          color: blue,
                                        ),
                                      ),
                                    ),
                                  if (reply != null)
                                    InkWell(
                                      onTap: () =>
                                          _openMessage(reply['id'] as int),
                                      child: Container(
                                        width: double.infinity,
                                        margin: const EdgeInsets.only(
                                          bottom: 6,
                                        ),
                                        padding: const EdgeInsets.all(8),
                                        decoration: BoxDecoration(
                                          border: Border(
                                            left: BorderSide(
                                              width: 3,
                                              color: blue,
                                            ),
                                          ),
                                          color: scheme.surface.withValues(
                                            alpha: 0.35,
                                          ),
                                        ),
                                        child: Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              text(reply, 'author_name'),
                                              style: TextStyle(
                                                color: blue,
                                                fontWeight: FontWeight.w600,
                                                fontSize: 12,
                                              ),
                                            ),
                                            Text(
                                              text(reply, 'body'),
                                              maxLines: 2,
                                              overflow: TextOverflow.ellipsis,
                                              style: const TextStyle(
                                                fontSize: 12,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  if (row['reference'] is Map)
                                    ListTile(
                                      contentPadding: EdgeInsets.zero,
                                      dense: true,
                                      leading: const Icon(Icons.link),
                                      title: Text(
                                        '${row['reference']['kind'] == 'ticket' ? 'Заявка' : 'Запчасть'} #${row['reference']['id']} · ${row['reference']['title']}',
                                      ),
                                      onTap: () => _openQuote(
                                        Map<String, dynamic>.from(
                                          row['reference'] as Map,
                                        ),
                                      ),
                                    ),
                                  if (text(row, 'body', '').isNotEmpty)
                                    Text(
                                      text(row, 'body'),
                                      style: const TextStyle(
                                        fontSize: 16,
                                        height: 1.35,
                                      ),
                                    ),
                                  for (final attachment in records(
                                    row['attachments'] ?? [],
                                  ))
                                    PrivateMedia(
                                      key: ValueKey(attachment['id']),
                                      controller: c,
                                      organization: _org,
                                      attachment: attachment,
                                    ),
                                  const SizedBox(height: 5),
                                  Row(
                                    mainAxisSize: MainAxisSize.min,
                                    mainAxisAlignment: MainAxisAlignment.end,
                                    children: [
                                      Text(
                                        _time(row['created_at']),
                                        style: TextStyle(
                                          fontSize: 11,
                                          color: scheme.onSurfaceVariant,
                                        ),
                                      ),
                                      if (row['pinned'] == true)
                                        const Padding(
                                          padding: EdgeInsets.only(left: 4),
                                          child: Icon(Icons.push_pin, size: 12),
                                        ),
                                      if (own && row['receipt'] is Map)
                                        Padding(
                                          padding: const EdgeInsets.only(
                                            left: 5,
                                          ),
                                          child: Tooltip(
                                            message: receiptLabel(
                                              row['receipt'] as Map,
                                            ),
                                            child: Icon(
                                              (row['receipt']['read'] as int? ??
                                                              0) >
                                                          0 ||
                                                      (row['receipt']['delivered']
                                                                  as int? ??
                                                              0) >
                                                          0
                                                  ? Icons.done_all
                                                  : Icons.check,
                                              size: 16,
                                              color:
                                                  (row['receipt']['read']
                                                              as int? ??
                                                          0) >
                                                      0
                                                  ? blue
                                                  : scheme.onSurfaceVariant,
                                            ),
                                          ),
                                        ),
                                    ],
                                  ),
                                  if (row['delivery_state'] != null)
                                    Text(
                                      '${row['delivery_state']}',
                                      style: const TextStyle(fontSize: 11),
                                    ),
                                  if (own && row['receipt'] is Map)
                                    Text(
                                      receiptLabel(row['receipt'] as Map),
                                      style: TextStyle(
                                        fontSize: 10,
                                        color: scheme.onSurfaceVariant,
                                      ),
                                    ),
                                ],
                              ),
                            ),
                          );
                          final content = Padding(
                            padding: const EdgeInsets.only(bottom: 10),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisAlignment: own
                                  ? MainAxisAlignment.end
                                  : MainAxisAlignment.start,
                              children: [
                                if (!own) ...[
                                  CircleAvatar(
                                    radius: 15,
                                    backgroundColor: dark
                                        ? const Color(0xff203f60)
                                        : const Color(0xffd6e8fc),
                                    child: Text(
                                      text(row, 'author_name').substring(0, 1),
                                      style: TextStyle(
                                        color: blue,
                                        fontSize: 14,
                                      ),
                                    ),
                                  ),
                                  const SizedBox(width: 6),
                                ],
                                ConstrainedBox(
                                  constraints: BoxConstraints(
                                    maxWidth:
                                        MediaQuery.sizeOf(context).width *
                                        (own ? 0.85 : 0.80),
                                  ),
                                  child: bubble,
                                ),
                              ],
                            ),
                          );
                          final seen = own || (row['id'] as int? ?? 0) <= 0
                              ? content
                              : ReceiptSeen(
                                  key: ValueKey(row['id']),
                                  controller: c,
                                  organization: _org,
                                  target: widget.commissioning
                                      ? 'commissioning_chat'
                                      : 'chat',
                                  id: row['id'] as int,
                                  child: content,
                                );
                          return Column(
                            key: ValueKey('chat-${row['id']}'),
                            children: [
                              if (showDay)
                                Padding(
                                  padding: const EdgeInsets.only(
                                    top: 2,
                                    bottom: 18,
                                  ),
                                  child: Chip(
                                    label: Text(
                                      date,
                                      style: const TextStyle(fontSize: 11),
                                    ),
                                    side: BorderSide.none,
                                    visualDensity: VisualDensity.compact,
                                    backgroundColor: dark
                                        ? const Color(0xff24364a)
                                        : const Color(0xffdae4f0),
                                  ),
                                ),
                              seen,
                            ],
                          );
                        },
                      ),
                    if (_newMessages > 0)
                      Positioned(
                        right: 12,
                        bottom: 12,
                        child: Badge(
                          label: Text('$_newMessages'),
                          child: FloatingActionButton.small(
                            heroTag: null,
                            tooltip: 'Новые сообщения',
                            onPressed: () {
                              _scroll.animateTo(
                                0,
                                duration: const Duration(milliseconds: 200),
                                curve: Curves.easeOut,
                              );
                              setState(() => _newMessages = 0);
                            },
                            child: const Icon(Icons.arrow_downward),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              Material(
                color: scheme.surface,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (_reply != null)
                      ListTile(
                        dense: true,
                        leading: Icon(Icons.reply, color: blue),
                        title: Text(text(_reply!, 'author_name'), maxLines: 1),
                        subtitle: Text(
                          text(_reply!, 'body', 'Вложение'),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        trailing: IconButton(
                          tooltip: 'Отменить ответ',
                          onPressed: () => setState(() => _reply = null),
                          icon: const Icon(Icons.close),
                        ),
                      ),
                    if (_quote != null)
                      ListTile(
                        dense: true,
                        leading: const Icon(Icons.link),
                        title: Text(text(_quote!, 'title'), maxLines: 1),
                        trailing: IconButton(
                          tooltip: 'Убрать карточку',
                          onPressed: () => setState(() => _quote = null),
                          icon: const Icon(Icons.close),
                        ),
                      ),
                    if (_files.isNotEmpty)
                      ConstrainedBox(
                        constraints: const BoxConstraints(maxHeight: 90),
                        child: SingleChildScrollView(
                          child: Wrap(
                            children: [
                              for (final file in _files)
                                InputChip(
                                  label: SizedBox(
                                    width: 150,
                                    child: Text(
                                      file.name,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                  onDeleted: _busy
                                      ? null
                                      : () => setState(() {
                                          _files.remove(file);
                                          _operationId = null;
                                        }),
                                ),
                            ],
                          ),
                        ),
                      ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(4, 8, 8, 10),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          IconButton(
                            tooltip: 'Прикрепить',
                            onPressed: _canRecord && !_busy ? _pick : null,
                            icon: const Icon(Icons.attach_file),
                          ),
                          Expanded(
                            child: TextField(
                              key: const Key('chat_message'),
                              controller: _input,
                              focusNode: _focus,
                              enabled: !_busy,
                              onChanged: (_) =>
                                  setState(() => _operationId = null),
                              minLines: 1,
                              maxLines: 5,
                              maxLength: 4000,
                              decoration: InputDecoration(
                                hintText: 'Сообщение',
                                counterText: '',
                                isDense: true,
                                contentPadding: const EdgeInsets.symmetric(
                                  horizontal: 16,
                                  vertical: 12,
                                ),
                                filled: true,
                                fillColor: canvas,
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(24),
                                  borderSide: BorderSide.none,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 5),
                          IconButton.filled(
                            tooltip: 'Отправить',
                            style: IconButton.styleFrom(
                              backgroundColor: blue,
                              foregroundColor: dark
                                  ? Colors.black
                                  : Colors.white,
                            ),
                            onPressed: canSend ? _send : null,
                            icon: _busy
                                ? const SizedBox(
                                    width: 20,
                                    height: 20,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Icon(Icons.send_rounded),
                          ),
                        ],
                      ),
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
