import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'common.dart';

/// Stable identifiers for the sections available to each role.
enum LiftMenuSection {
  home,
  tickets,
  elevators,
  documents,
  duty,
  tasks,
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

/// Shows every available section in the NavigationDrawer's scrollable list.
class AdaptiveNavigationDrawer extends StatelessWidget {
  const AdaptiveNavigationDrawer({
    super.key,
    required this.items,
    required this.selectedSection,
    required this.onSelected,
    this.unread = const {},
  });

  final List<LiftMenuItem> items;
  final LiftMenuSection? selectedSection;
  final ValueChanged<LiftMenuSection> onSelected;
  final Map<LiftMenuSection, int> unread;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, bounds) {
      const headingPadding = EdgeInsets.fromLTRB(28, 20, 20, 12);
      const tilePadding = EdgeInsets.symmetric(horizontal: 12);
      final textScaler = MediaQuery.textScalerOf(context);
      final safePadding = MediaQuery.paddingOf(context);
      final headingHeight = headingPadding.vertical + textScaler.scale(28);
      final width = math.min(
        bounds.maxWidth,
        DrawerTheme.of(context).width ?? 304.0,
      );
      // NavigationDrawer adds a 16 dp inset, a 24 dp icon and a 12 dp gap.
      const iconSpace = 16.0 + 24.0 + 12.0;
      final labelWidth = math.max(
        0.0,
        width -
            safePadding.horizontal -
            tilePadding.horizontal -
            iconSpace -
            12.0,
      );
      final selected = items.indexWhere(
        (item) => item.section == selectedSection,
      );
      return NavigationDrawer(
        tilePadding: tilePadding,
        selectedIndex: selected < 0 ? null : selected,
        onDestinationSelected: (index) => onSelected(items[index].section),
        children: [
          SizedBox(
            height: headingHeight,
            child: Padding(
              padding: headingPadding,
              child: Text(
                'Разделы',
                style: Theme.of(context).textTheme.titleLarge,
              ),
            ),
          ),
          for (final item in items)
            NavigationDrawerDestination(
              key: ValueKey('drawer-${item.section.name}'),
              icon: Icon(item.icon),
              label: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: labelWidth),
                child: Row(
                  children: [
                    Expanded(child: Text(
                      item.label,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    )),
                    if ((unread[item.section] ?? 0) > 0) ...[
                      const SizedBox(width: 6),
                      unreadBadge(unread[item.section]!),
                    ],
                  ],
                ),
              ),
            ),
        ],
      );
    },
  );
}
