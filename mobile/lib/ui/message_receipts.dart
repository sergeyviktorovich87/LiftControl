import 'dart:async';
import 'package:flutter/material.dart';
import '../core/controller.dart';

String receiptLabel(Map receipt) {
  final total = receipt['total'] as int? ?? 0;
  final read = receipt['read'] as int? ?? 0;
  final delivered = receipt['delivered'] as int? ?? 0;
  if (total == 0) return '✓ Отправлено';
  if (read > 0) return '✓✓ Прочитали $read из $total';
  if (delivered > 0) return '✓✓ Доставлено $delivered из $total';
  return '✓ Отправлено · ожидает доставки';
}

/// Acknowledges only a rendered item intersecting its scroll viewport.
class ReceiptSeen extends StatefulWidget {
  const ReceiptSeen({
    super.key,
    required this.controller,
    required this.organization,
    required this.target,
    required this.id,
    required this.child,
  });
  final LiftController controller;
  final int organization, id;
  final String target;
  final Widget child;
  @override
  State<ReceiptSeen> createState() => _ReceiptSeenState();
}

class _ReceiptSeenState extends State<ReceiptSeen> {
  Timer? _timer;
  bool _busy = false;
  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(milliseconds: 900), (_) => _check());
  }

  Future<void> _check() async {
    final c = widget.controller;
    if (widget.id <= 0 ||
        _busy ||
        !mounted ||
        !c.canWrite ||
        c.organization != widget.organization ||
        c.me['message_receipts_api'] != 1 ||
        ModalRoute.of(context)?.isCurrent != true ||
        (WidgetsBinding.instance.lifecycleState ?? AppLifecycleState.resumed) !=
            AppLifecycleState.resumed) {
      return;
    }
    final box = context.findRenderObject();
    final viewport = Scrollable.maybeOf(context)?.context.findRenderObject();
    if (box is! RenderBox ||
        !box.hasSize ||
        viewport is! RenderBox ||
        !viewport.hasSize) {
      return;
    }
    final bounds = box.localToGlobal(Offset.zero) & box.size;
    final visible = viewport.localToGlobal(Offset.zero) & viewport.size;
    if (!bounds.overlaps(visible) || bounds.intersect(visible).height < 16) {
      return;
    }
    _busy = true;
    try {
      await c.request(
        'notifications/receipts/',
        method: 'POST',
        expectedOrganization: widget.organization,
        data: {
          'target': widget.target,
          'ids': [widget.id],
          'read': true,
        },
      );
      _timer?.cancel();
      unawaited(c.refreshNotificationCounts());
    } catch (_) {
      c.log.record('message_receipt_failed', route: widget.target);
    } finally {
      _busy = false;
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
