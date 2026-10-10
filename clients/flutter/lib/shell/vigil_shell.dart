import 'package:flutter/material.dart';

import '../auth/session.dart';
import '../api/config_api.dart';
import '../api/vigil_client.dart';
import '../screens/cases/cases_screen.dart';
import '../screens/findings/findings_screen.dart';
import '../screens/shared/approval_fuse.dart';
import '../screens/triage/triage_screen.dart';
import '../settings/scheme_controller.dart';
import '../theme/extensions.dart';
import '../theme/vigil_colors.dart';
import '../theme/vigil_icon.dart';
import '../theme/vigil_icons.dart';
import '../theme/vigil_typography.dart';
import 'screens.dart';

/// The adaptive app shell: bottom navigation bar on phones (< 600 dp), a
/// navigation rail on tablets and desktop. Destinations come from
/// [visibleDestinations] — the console's SCREEN_PERMS gating, one to one —
/// so a screen the user's role can't reach is absent from the nav entirely.
class VigilShell extends StatefulWidget {
  const VigilShell({
    super.key,
    required this.user,
    required this.client,
    required this.initialScreen,
    required this.onSignOut,
    this.initialCaseId,
    this.scheme,
  });

  final UserProfile user;

  /// The authenticated client — the data plane for the ported screens.
  final VigilClient client;

  /// Where the shell opens — the landing destination, or the deep-linked
  /// screen (already permission-checked by the app root).
  final VigilScreen initialScreen;

  /// `?case=<id>` — a deep-linked case the Cases screen opens on arrival.
  final String? initialCaseId;

  /// The server-persisted color scheme; null hides the app-bar toggle.
  final SchemeController? scheme;

  final VoidCallback onSignOut;

  @override
  State<VigilShell> createState() => _VigilShellState();
}

class _VigilShellState extends State<VigilShell> {
  /// 600 dp — the console's breakpoint between stacked and side-by-side
  /// layouts; phones navigate by bar, tablets/desktop by rail.
  static const double _railBreakpoint = 600;

  List<VigilScreen> get _visible =>
      visibleDestinations(widget.user.permissions);

  late VigilScreen _screen = _initialScreen();

  /// The shell's undo fuse — owned here so a reversible approval keeps
  /// ticking while the user reads another screen (the console's toast
  /// fuses are owned by the shell too).
  late final FuseController _fuse = FuseController(onEvent: _onFuseEvent);

  /// A case handed over by a deep link or another screen's case door —
  /// the Cases screen remounts ([_casesKey]) to open it.
  String? _pendingCaseId;
  int _casesKey = 0;

  @override
  void dispose() {
    _fuse.dispose();
    super.dispose();
  }

  void _onFuseEvent(FuseEvent event) {
    final error = event.error;
    final text = error != null
        ? 'The decision could not be recorded — it was not applied.'
        : (event.doneText ?? 'Done.');
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(text)));
  }

  /// Another screen's case door (triage rows, findings) hands the case id
  /// over; Cases opens it, keeping the console's one-case deep-link
  /// semantics between screens.
  void _openCase(String caseId) {
    setState(() {
      _screen = VigilScreen.cases;
      _pendingCaseId = caseId;
      _casesKey += 1;
    });
  }

  VigilScreen _initialScreen() {
    if (canSeeScreen(widget.initialScreen, widget.user.permissions)) {
      return widget.initialScreen;
    }
    // Landing fallback: the first destination the role can see. Ask Vigil is
    // ungated, so this list is never empty.
    return _visible.first;
  }

  void _select(VigilScreen screen) => setState(() => _screen = screen);

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final wide = MediaQuery.sizeOf(context).width >= _railBreakpoint;
    return Scaffold(
      appBar: _appBar(context, colors),
      body: _visible.isEmpty
          ? _noAccessPane(colors)
          : (wide ? _withRail(colors) : _pane(colors)),
      bottomNavigationBar: wide || _visible.isEmpty ? null : _bottomBar(colors),
    );
  }

  PreferredSizeWidget _appBar(BuildContext context, VigilColors colors) {
    final scheme = widget.scheme;
    return AppBar(
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
              borderRadius:
                  BorderRadius.circular(context.vigilMetrics.radiusPillSm - 3),
            ),
            alignment: Alignment.center,
            child: Text(
              'V',
              style: VigilTypography.label.copyWith(color: colors.dtSilver),
            ),
          ),
          const SizedBox(width: 8),
          Text(_screen.appBarTitle, style: VigilTypography.sectionTitle),
        ],
      ),
      actions: [
        if (scheme != null)
          IconButton(
            key: const Key('scheme-toggle'),
            tooltip: scheme.scheme == VigilScheme.light
                ? 'Switch to dark theme'
                : 'Switch to light theme',
            icon: VigilIcon(
              scheme.scheme == VigilScheme.light
                  ? VigilIcons.moon
                  : VigilIcons.sun,
            ),
            onPressed: () => scheme.set(
              scheme.scheme == VigilScheme.light
                  ? VigilScheme.dark
                  : VigilScheme.light,
            ),
          ),
        PopupMenuButton<String>(
          key: const Key('account-menu'),
          tooltip: 'Account',
          icon: const VigilIcon(VigilIcons.user),
          onSelected: (value) {
            if (value == 'sign-out') widget.onSignOut();
          },
          itemBuilder: (context) => [
            PopupMenuItem<String>(
              enabled: false,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    widget.user.username ?? 'Signed in',
                    style: VigilTypography.meta
                        .copyWith(color: context.vigilColors.tx0),
                  ),
                  if (widget.user.email != null)
                    Text(
                      widget.user.email!,
                      style: VigilTypography.meta
                          .copyWith(color: context.vigilColors.tx2),
                    ),
                ],
              ),
            ),
            const PopupMenuDivider(),
            const PopupMenuItem<String>(
              value: 'sign-out',
              key: Key('sign-out-item'),
              child: Text('Sign out'),
            ),
          ],
        ),
      ],
    );
  }

  Widget _noAccessPane(VigilColors colors) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            VigilIcon(VigilIcons.lock, size: 32, color: colors.tx3),
            const SizedBox(height: 12),
            Text(
              'No screens available for this role',
              style: VigilTypography.bodyStrong.copyWith(color: colors.tx0),
            ),
            const SizedBox(height: 6),
            Text(
              'Sign in with an account that has access.',
              style: VigilTypography.meta.copyWith(color: colors.tx2),
            ),
          ],
        ),
      );

  Widget _bottomBar(VigilColors colors) {
    // The console's PRIMARY/MORE split (`SocConsole.tsx`): four human-work
    // destinations on the bar, the rest under More — seven destinations
    // clip a phone bottom bar. The rail (wide) shows everything.
    const barCount = 4;
    final inBar = _visible.take(barCount).toList();
    final overflow = _visible.skip(barCount).toList();
    final selected = inBar.indexOf(_screen);
    return NavigationBar(
      selectedIndex: selected < 0 ? inBar.length : selected,
      onDestinationSelected: (i) {
        if (i < inBar.length) return _select(inBar[i]);
        _showMoreSheet(colors, overflow);
      },
      destinations: [
        for (final screen in inBar)
          NavigationDestination(
            key: Key('nav-${screen.name}'),
            icon: VigilIcon(screen.icon),
            selectedIcon: VigilIcon(screen.icon, color: colors.ac),
            label: screen.navLabel,
            tooltip: screen.appBarTitle,
          ),
        if (overflow.isNotEmpty)
          NavigationDestination(
            key: const Key('nav-more'),
            icon: const VigilIcon(VigilIcons.more),
            selectedIcon: VigilIcon(VigilIcons.more, color: colors.ac),
            label: 'More',
            tooltip: 'More screens',
          ),
      ],
    );
  }

  /// The destinations that don't fit the phone bar — the console's
  /// "More" menu (`SocConsole.tsx` MORE_KEYS), as a bottom sheet.
  void _showMoreSheet(VigilColors colors, List<VigilScreen> overflow) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: colors.bg1,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final screen in overflow)
              ListTile(
                key: Key('nav-more-${screen.name}'),
                leading: VigilIcon(
                  screen.icon,
                  color: _screen == screen ? colors.ac : colors.tx1,
                ),
                title: Text(
                  screen.navLabel,
                  style: VigilTypography.body
                      .copyWith(color: _screen == screen ? colors.ac : colors.tx0),
                ),
                onTap: () {
                  Navigator.of(sheetContext).pop();
                  _select(screen);
                },
              ),
          ],
        ),
      ),
    );
  }

  Widget _withRail(VigilColors colors) {
    return Row(
      children: [
        NavigationRail(
          selectedIndex: _visible.indexOf(_screen),
          onDestinationSelected: (i) => _select(_visible[i]),
          labelType: NavigationRailLabelType.all,
          destinations: [
            for (final screen in _visible)
              NavigationRailDestination(
                icon: VigilIcon(screen.icon),
                selectedIcon: VigilIcon(screen.icon, color: colors.ac),
                label: Text(screen.navLabel),
              ),
          ],
        ),
        const VerticalDivider(width: 1, thickness: 1),
        Expanded(child: _pane(colors)),
      ],
    );
  }

  Widget _pane(VigilColors colors) {
    final pane = switch (_screen) {
      VigilScreen.cases => CasesScreen(
          key: ValueKey('cases-$_casesKey'),
          client: widget.client,
          fuse: _fuse,
          initialCaseId: _pendingCaseId,
        ),
      VigilScreen.findings => FindingsScreen(client: widget.client),
      VigilScreen.triage =>
        TriageScreen(client: widget.client, onOpenCase: _openCase),
      VigilScreen.home => _homePane(colors),
      _ => _placeholderPane(colors, _screen),
    };
    // The fuse banner docks above the shell's bottom chrome; when idle it
    // collapses to nothing.
    return Column(
      children: [
        Expanded(child: pane),
        FusedActionBanner(controller: _fuse),
      ],
    );
  }

  /// Home — "What needs a person". The needs-you feed arrives with the
  /// approvals port task; until then the honest empty state stands.
  Widget _homePane(VigilColors colors) {
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

  Widget _placeholderPane(VigilColors colors, VigilScreen screen) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          VigilIcon(screen.icon, size: 32, color: colors.tx3),
          const SizedBox(height: 12),
          Text(
            screen.subtitle,
            textAlign: TextAlign.center,
            style: VigilTypography.bodyStrong.copyWith(color: colors.tx0),
          ),
          const SizedBox(height: 6),
          Text(
            '${screen.navLabel} lands with its port task.',
            style: VigilTypography.meta.copyWith(color: colors.tx2),
          ),
        ],
      ),
    );
  }
}

/// The explanatory empty state a gated deep link lands on (the console's
/// rule: gated screens hide from navigation, and direct links don't pretend
/// to load). No privilege escalation is attempted — the way out is signing
/// in with an account that holds the permission.
class PermissionDeniedScreen extends StatelessWidget {
  const PermissionDeniedScreen({
    super.key,
    required this.screen,
    required this.user,
    required this.onSignOut,
  });

  final VigilScreen screen;
  final UserProfile user;
  final VoidCallback onSignOut;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final who = user.username ?? user.email ?? 'this account';
    return Scaffold(
      appBar: AppBar(
        backgroundColor: colors.bg0,
        elevation: 0,
        title: Text(screen.appBarTitle, style: VigilTypography.sectionTitle),
      ),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            VigilIcon(VigilIcons.lock, size: 32, color: colors.tx3),
            const SizedBox(height: 12),
            Text(
              'No access to ${screen.navLabel}',
              style: VigilTypography.bodyStrong.copyWith(color: colors.tx0),
            ),
            const SizedBox(height: 6),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 32),
              child: Text(
                "Signed in as $who. Your role doesn't include the "
                "'${screen.requiredPerm}' permission — ask an administrator "
                'to grant it, or sign in with a different account.',
                textAlign: TextAlign.center,
                style: VigilTypography.meta.copyWith(color: colors.tx2),
              ),
            ),
            const SizedBox(height: 20),
            FilledButton.tonal(
              key: const Key('denied-sign-out'),
              onPressed: onSignOut,
              child: const Text('Sign out'),
            ),
          ],
        ),
      ),
    );
  }
}
