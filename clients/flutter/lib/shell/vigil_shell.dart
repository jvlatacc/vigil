import 'package:flutter/material.dart';

import '../auth/session.dart';
import '../api/config_api.dart';
import '../chat/ask_vigil_pane.dart';
import '../chat/chat_session.dart';
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
    required this.chatSession,
    required this.initialScreen,
    required this.onSignOut,
    this.scheme,
  });

  final UserProfile user;

  /// The Ask Vigil state — owned above the shell so the dock and the
  /// phone's sheet share one live transcript across opens.
  final ChatSession chatSession;

  /// Where the shell opens — the landing destination, or the deep-linked
  /// screen (already permission-checked by the app root).
  final VigilScreen initialScreen;

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

  /// The console's fixed chat dock width (`CHAT_WIDTH` in SocConsole.tsx).
  static const double _chatDockWidth = 400;

  List<VigilScreen> get _visible =>
      visibleDestinations(widget.user.permissions);

  late VigilScreen _screen = _initialScreen();

  /// Whether the Ask Vigil dock is open on wide layouts (phones use the
  /// modal sheet instead — the console's narrow-screen overlay rule).
  bool _askOpen = false;

  VigilScreen _initialScreen() {
    if (canSeeScreen(widget.initialScreen, widget.user.permissions)) {
      return widget.initialScreen;
    }
    // Landing fallback: the first destination the role can see. Ask Vigil is
    // ungated, so this list is never empty.
    return _visible.first;
  }

  /// Ask Vigil is a dock, not a screen: selecting it opens (or toggles) the
  /// 400 px dock beside the current pane on wide layouts, and opens the
  /// modal sheet on phones. A deep link to `/ask` still lands on an
  /// inline, full-height pane via [_screen].
  void _select(VigilScreen screen) {
    if (screen == VigilScreen.ask) {
      if (_screen == VigilScreen.ask) return;
      final wide = MediaQuery.sizeOf(context).width >= _railBreakpoint;
      if (wide) {
        setState(() => _askOpen = !_askOpen);
      } else {
        _openAskSheet();
      }
      return;
    }
    setState(() => _screen = screen);
  }

  Future<void> _openAskSheet() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (sheetContext) => Padding(
        // Keep the composer above the keyboard.
        padding: EdgeInsets.only(
            bottom: MediaQuery.viewInsetsOf(sheetContext).bottom),
        child: SizedBox(
          height: MediaQuery.sizeOf(sheetContext).height * 0.92,
          child: AskVigilPane(session: widget.chatSession),
        ),
      ),
    );
  }

  /// The nav selection: the open dock highlights the Ask entry.
  int get _selectedIndex => (_askOpen || _screen == VigilScreen.ask)
      ? _visible.indexOf(VigilScreen.ask)
      : _visible.indexOf(_screen);

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
    return NavigationBar(
      selectedIndex: _selectedIndex,
      onDestinationSelected: (i) => _select(_visible[i]),
      destinations: [
        for (final screen in _visible)
          NavigationDestination(
            key: Key('nav-${screen.name}'),
            icon: VigilIcon(screen.icon),
            selectedIcon: VigilIcon(screen.icon, color: colors.ac),
            label: screen.navLabel,
            tooltip: screen.appBarTitle,
          ),
      ],
    );
  }

  Widget _withRail(VigilColors colors) {
    // NavigationRail asserts at least two destinations; a viewer whose
    // permissions leave a single ungated surface gets the pane full-width
    // instead of a rail that cannot be built.
    final showRail = _visible.length >= 2;
    return Row(
      children: [
        if (showRail) ...[
          NavigationRail(
            selectedIndex: _selectedIndex,
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
        ],
        Expanded(child: _pane(colors)),
        if (_askOpen && _screen != VigilScreen.ask) ...[
          VerticalDivider(width: 1, thickness: 1, color: colors.ln0),
          SizedBox(
            width: _chatDockWidth,
            child: AskVigilPane(
              session: widget.chatSession,
              onClose: () => setState(() => _askOpen = false),
            ),
          ),
        ],
      ],
    );
  }

  Widget _pane(VigilColors colors) {
    // Deep-linked /ask renders as a full-height pane; nav never selects it
    // (the dock and sheet own that path).
    if (_screen == VigilScreen.ask) {
      return AskVigilPane(session: widget.chatSession);
    }
    if (_screen == VigilScreen.home) return _homePane(colors);
    return _placeholderPane(colors, _screen);
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
