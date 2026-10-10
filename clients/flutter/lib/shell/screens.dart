import '../theme/vigil_icon.dart';
import '../theme/vigil_icons.dart';

/// Screens this shell routes between; "Ask Vigil" is the console's chat
/// dock name, never "Chat".
enum VigilScreen { home, decisions, cases, ask, settings }

/// Home's gate — console `shell/landing.ts`: people without it don't land
/// on Home. Same string as the decisions entry below; the console keeps the
/// two spelled out in `SCREEN_PERMS` and we mirror that shape.
const String homePerm = 'ai_decisions.approve';

/// The only permission check in the app, mirroring the console's
/// SCREEN_PERMS map one to one (clients/web/src/shell/SocConsole.tsx:74):
/// screens absent here are ungated. Read against the same permission map
/// the console gets from `/auth/me`.
const Map<VigilScreen, String> screenPerms = {
  VigilScreen.cases: 'cases.read',
  VigilScreen.decisions: 'ai_decisions.approve',
  VigilScreen.home: homePerm,
  VigilScreen.settings: 'settings.read',
};

/// Whether a user with [permissions] can reach [screen] — the console's
/// rule: a screen is visible iff its SCREEN_PERMS entry is absent (ungated)
/// or the user holds the key. Role changes re-gate on the next `/auth/me`
/// refresh; no privilege escalation is attempted client-side.
bool canSeeScreen(VigilScreen screen, Map<String, bool> permissions) {
  final perm = screenPerms[screen];
  return perm == null || permissions[perm] == true;
}

/// The destinations a user with [permissions] sees, in nav order — gated
/// screens are hidden from navigation, not disabled.
List<VigilScreen> visibleDestinations(Map<String, bool> permissions) =>
    VigilScreen.values
        .where((screen) => canSeeScreen(screen, permissions))
        .toList();

/// Parses a named deep-link route (`/decisions`) to its screen. Returns
/// null for the root, unknown routes (the shell falls back to its default
/// destination) — callers still gate the result with [canSeeScreen].
VigilScreen? screenFromRoute(String? route) {
  if (route == null || route.isEmpty || route == '/') return null;
  final name = route.startsWith('/') ? route.substring(1) : route;
  for (final screen in VigilScreen.values) {
    if (screen.name == name) return screen;
  }
  return null;
}

/// Names and icons from the console's `TITLES`/`NAV` registries
/// (clients/web/src/data/data.ts).
extension VigilScreenInfo on VigilScreen {
  /// Nav label — the console's NAV entry ("AI Decisions", "Ask Vigil").
  String get navLabel => switch (this) {
        VigilScreen.home => 'Home',
        VigilScreen.decisions => 'AI Decisions',
        VigilScreen.cases => 'Cases',
        VigilScreen.ask => 'Ask Vigil',
        VigilScreen.settings => 'Settings',
      };

  /// App-bar title — Home is literally titled "What needs a person" (the
  /// console's home subtitle and the spec's screen name).
  String get appBarTitle => switch (this) {
        VigilScreen.home => 'What needs a person',
        VigilScreen.decisions => 'AI Decisions',
        VigilScreen.cases => 'Cases',
        VigilScreen.ask => 'Ask Vigil',
        VigilScreen.settings => 'Settings',
      };

  /// The console's screen subtitle, used as placeholder copy until the
  /// screen's port task lands.
  String get subtitle => switch (this) {
        VigilScreen.home => 'Approvals and escalations land here at the '
            'console cadence.',
        VigilScreen.decisions =>
          'Review and provide feedback for AI decisions',
        VigilScreen.cases => 'Manage investigation cases',
        VigilScreen.ask => 'Investigate alongside Vigil',
        VigilScreen.settings =>
          'Configure Vigil — AI, integrations, users and platform',
      };

  VigilIconData get icon => switch (this) {
        VigilScreen.home => VigilIcons.home,
        VigilScreen.decisions => VigilIcons.gavel,
        VigilScreen.cases => VigilIcons.cases,
        VigilScreen.ask => VigilIcons.chat,
        VigilScreen.settings => VigilIcons.settings,
      };

  /// The permission key gating this screen, or null when ungated.
  String? get requiredPerm => screenPerms[this];
}
