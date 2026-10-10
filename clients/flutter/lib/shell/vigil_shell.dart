import 'package:flutter/material.dart';

import '../approvals/approvals_controller.dart';
import '../approvals/fused_decision_toast.dart';
import '../auth/session.dart';
import '../api/config_api.dart';
import '../decisions/decisions_screen.dart';
import '../home/home_screen.dart';
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
    required this.initialScreen,
    required this.onSignOut,
    this.scheme,
    this.approvals,
  });

  final UserProfile user;

  /// The approvals controller behind Home and Decisions; null keeps the
  /// honest placeholder panes (tests instantiate the shell without a data
  /// client). Lifecycle pause/resume is wired to this controller.
  final ApprovalsController? approvals;

  /// Where the shell opens — the landing destination, or the deep-linked
  /// screen (already permission-checked by the app root).
  final VigilScreen initialScreen;

  /// The server-persisted color scheme; null hides the app-bar toggle.
  final SchemeController? scheme;

  final VoidCallback onSignOut;

  @override
  State<VigilShell> createState() => _VigilShellState();
}

class _VigilShellState extends State<VigilShell>
    with WidgetsBindingObserver {
  /// 600 dp — the console's breakpoint between stacked and side-by-side
  /// layouts; phones navigate by bar, tablets/desktop by rail.
  static const double _railBreakpoint = 600;

  List<VigilScreen> get _visible =>
      visibleDestinations(widget.user.permissions);

  late VigilScreen _screen = _initialScreen();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  /// Lifecycle-aware polling: paused/hidden stops the schedule, resumed
  /// polls immediately and rearms the 20 s cadence.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        widget.approvals?.resume();
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
        widget.approvals?.pause();
      default:
        break;
    }
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
    return NavigationBar(
      selectedIndex: _visible.indexOf(_screen),
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
    final approvals = widget.approvals;
    if (_screen == VigilScreen.home) {
      return approvals == null
          ? _homePane(colors)
          : _toastOverlay(
              HomeScreen(
                controller: approvals,
                onReview: _visible.contains(VigilScreen.decisions)
                    ? () => _select(VigilScreen.decisions)
                    : null,
                onOpenCase: _visible.contains(VigilScreen.cases)
                    ? () => _select(VigilScreen.cases)
                    : null,
              ),
            );
    }
    if (_screen == VigilScreen.decisions && approvals != null) {
      return _toastOverlay(DecisionsScreen(controller: approvals));
    }
    return _placeholderPane(colors, _screen);
  }

  /// The fused-decision toast rides above the pane content — bottom of the
  /// screen, clear of the phone's navigation bar.
  Widget _toastOverlay(Widget child) {
    final approvals = widget.approvals;
    if (approvals == null) return child;
    final wide = MediaQuery.sizeOf(context).width >= _railBreakpoint;
    return Stack(
      children: [
        child,
        Positioned(
          left: 16,
          right: 16,
          bottom: wide ? 16 : 96,
          child: FusedDecisionToast(controller: approvals),
        ),
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
