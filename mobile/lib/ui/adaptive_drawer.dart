import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Stable identifiers: the list order may change with role and screen height.
enum LiftMenuSection {
  home,
  tickets,
  elevators,
  duty,
  tasks,
  maintenance,
  commissioning,
  parts,
  media,
  staff,
  chat,
  settings,
}

class LiftMenuItem {
  const LiftMenuItem(this.section, this.label, this.icon);

  final LiftMenuSection section;
  final String label;
  final IconData icon;
}

/// Shows as many entries as the available drawer height allows.
/// The remaining entries are behind an inline expandable "Ещё" destination.
/// NavigationDrawer scrolls normally while expanded, including on small screens.
class AdaptiveNavigationDrawer extends StatefulWidget {
  const AdaptiveNavigationDrawer({
    super.key,
    required this.items,
    required this.selectedSection,
    required this.onSelected,
    this.onOverflowOpened,
  });

  final List<LiftMenuItem> items;
  final LiftMenuSection? selectedSection;
  final ValueChanged<LiftMenuSection> onSelected;
  final VoidCallback? onOverflowOpened;

  @override
  State<AdaptiveNavigationDrawer> createState() =>
      _AdaptiveNavigationDrawerState();
}

class _AdaptiveNavigationDrawerState extends State<AdaptiveNavigationDrawer> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, bounds) {
      // Reserve room for the heading, system insets and drawer padding.
      // Use a conservative row height for larger accessibility text.
      final height = bounds.maxHeight.isFinite
          ? bounds.maxHeight
          : MediaQuery.sizeOf(context).height;
      final textScale = MediaQuery.textScalerOf(context).scale(14) / 14;
      final rowHeight = 56.0 * math.max(1.0, textScale);
      final safeHeight = MediaQuery.paddingOf(context).vertical;
      final available = math.max(0.0, height - safeHeight - 100.0);
      final capacity = math.max(1, (available / rowHeight).floor());
      final hasOverflow = widget.items.length > capacity;
      final previewCount = hasOverflow
          ? math.max(0, capacity - 1)
          : widget.items.length;

      // -1 is the overflow toggle. Expanded items are appended underneath it.
      final visible = <int>[
        for (var i = 0; i < previewCount; i++) i,
        if (hasOverflow) -1,
        if (hasOverflow && _expanded)
          for (var i = previewCount; i < widget.items.length; i++) i,
      ];
      final selected = visible.indexWhere(
        (i) =>
            i >= 0 && widget.items[i].section == widget.selectedSection,
      );
      return NavigationDrawer(
        selectedIndex: selected < 0 ? null : selected,
        onDestinationSelected: (index) {
          final itemIndex = visible[index];
          if (itemIndex == -1) {
            if (!_expanded) widget.onOverflowOpened?.call();
            setState(() => _expanded = !_expanded);
            return;
          }
          widget.onSelected(widget.items[itemIndex].section);
          if (_expanded) setState(() => _expanded = false);
        },
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(28, 20, 20, 12),
            child: Text(
              'Разделы',
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ),
          for (final index in visible)
            NavigationDrawerDestination(
              key: ValueKey(
                index == -1
                    ? 'drawer-overflow'
                    : 'drawer-${widget.items[index].section.name}',
              ),
              icon: Icon(
                index == -1
                    ? (_expanded ? Icons.expand_less : Icons.more_horiz)
                    : widget.items[index].icon,
              ),
              label: Text(
                index == -1
                    ? (_expanded ? 'Свернуть' : 'Ещё')
                    : widget.items[index].label,
              ),
            ),
        ],
      );
    },
  );
}
