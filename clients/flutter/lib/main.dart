import 'package:flutter/material.dart';

import 'design/galleries.dart';
import 'theme/extensions.dart';
import 'theme/vigil_colors.dart';
import 'theme/vigil_icon.dart';
import 'theme/vigil_icons.dart';
import 'theme/vigil_typography.dart';
import 'theme/vigil_theme.dart';

void main() => runApp(const VigilApp());

class VigilApp extends StatelessWidget {
  const VigilApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Vigil',
      debugShowCheckedModeBanner: false,
      theme: buildVigilThemeData(Brightness.light),
      darkTheme: buildVigilThemeData(Brightness.dark),
      // Dark-first, like the console; server-persisted scheme arrives with
      // the settings port.
      themeMode: ThemeMode.dark,
      home: const NeedsYouHome(),
    );
  }
}

/// First-wave Home — "What needs a person" — as a shell placeholder: the
/// needs-you feed API lands with the approvals task; today the shell proves
/// the design system end to end (fonts, tokens, icons, nav).
class NeedsYouHome extends StatefulWidget {
  const NeedsYouHome({super.key});

  @override
  State<NeedsYouHome> createState() => _NeedsYouHomeState();
}

class _NeedsYouHomeState extends State<NeedsYouHome> {
  int _index = 0;

  static const _destinations = [
    ('home', 'Home'),
    ('cases', 'Cases'),
    ('chat', 'Ask Vigil'),
    ('settings', 'Settings'),
  ];

  VigilIconData _iconFor(String name) => VigilIcons.byName[name]!;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final wide = MediaQuery.sizeOf(context).width >= 600;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: colors.bg0,
        elevation: 0,
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                color: colors.dtRed,
                borderRadius: BorderRadius.circular(
                    context.vigilMetrics.radiusPillSm - 3),
              ),
              alignment: Alignment.center,
              child: Text(
                'V',
                style: VigilTypography.label.copyWith(color: colors.dtSilver),
              ),
            ),
            const SizedBox(width: 8),
            const Text('What needs a person',
                style: VigilTypography.sectionTitle),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Design system',
            icon: const VigilIcon(VigilIcons.wall),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                  builder: (_) => const DesignSystemScreen()),
            ),
          ),
        ],
      ),
      body: wide ? _withRail(colors) : _pane(colors),
      bottomNavigationBar: wide ? null : _bottomBar(colors),
    );
  }

  /// Bottom bar on phones, navigation rail on tablets/desktop (>= 600 dp),
  /// mirroring the console's narrow-screen rules.
  Widget _bottomBar(VigilColors colors) {
    return NavigationBar(
      selectedIndex: _index,
      onDestinationSelected: (i) => setState(() => _index = i),
      destinations: [
        for (final (iconName, label) in _destinations)
          NavigationDestination(
            icon: VigilIcon(_iconFor(iconName)),
            selectedIcon: VigilIcon(_iconFor(iconName), color: colors.ac),
            label: label,
          ),
      ],
    );
  }

  Widget _withRail(VigilColors colors) {
    return Row(
      children: [
        NavigationRail(
          selectedIndex: _index,
          onDestinationSelected: (i) => setState(() => _index = i),
          labelType: NavigationRailLabelType.all,
          destinations: [
            for (final (iconName, label) in _destinations)
              NavigationRailDestination(
                icon: VigilIcon(_iconFor(iconName)),
                selectedIcon: VigilIcon(_iconFor(iconName), color: colors.ac),
                label: Text(label),
              ),
          ],
        ),
        const VerticalDivider(width: 1, thickness: 1),
        Expanded(child: _pane(colors)),
      ],
    );
  }

  Widget _pane(VigilColors colors) {
    if (_index != 0) {
      final label = _destinations[_index].$2;
      return Center(
        child: Text(
          '$label lands with its port task.',
          style: VigilTypography.meta.copyWith(color: colors.tx2),
        ),
      );
    }
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          VigilIcon(VigilIcons.check, size: 32, color: colors.good),
          const SizedBox(height: 12),
          Text(
            'Nothing needs a person right now',
            style: VigilTypography.bodyStrong.copyWith(color: colors.tx0),
          ),
          const SizedBox(height: 6),
          Text(
            'Approvals and escalations land here at the console cadence.',
            textAlign: TextAlign.center,
            style: VigilTypography.meta.copyWith(color: colors.tx2),
          ),
        ],
      ),
    );
  }
}

/// Browsable design-system galleries (tokens, icons, type ramp) — the same
/// widgets the goldens capture.
class DesignSystemScreen extends StatelessWidget {
  const DesignSystemScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    Widget section(String title, Widget child) => Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title,
                  style:
                      VigilTypography.sectionTitle.copyWith(color: colors.tx0)),
              const SizedBox(height: 12),
              child,
            ],
          ),
        );
    return Scaffold(
      appBar: AppBar(
          title:
              const Text('Design system', style: VigilTypography.sectionTitle)),
      body: ListView(
        children: [
          section('Colors — .vg-dark',
              const SwatchGallery(colors: VigilColors.dark)),
          section('Colors — .vg-light',
              const SwatchGallery(colors: VigilColors.light)),
          section('Icons', const IconGallery()),
          section('Type ramp', const TypeRampGallery()),
        ],
      ),
    );
  }
}
