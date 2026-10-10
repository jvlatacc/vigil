import 'package:flutter/material.dart';

import '../api/config_api.dart';
import '../api/vigil_client.dart';
import '../auth/session.dart';
import '../onboarding/server_profile.dart';
import 'account_section.dart';
import 'notification_preferences.dart';
import 'scheme_controller.dart';
import 'security_section.dart';
import 'server_section.dart';
import '../theme/extensions.dart';
import '../theme/vigil_icons.dart';
import '../theme/vigil_typography.dart';
import 'watch_pairing.dart';

/// The Settings pane — the admin-lite subset a first-party client owns:
/// which server it talks to, the account and its MFA enrollment, the
/// server-persisted color scheme, local notification preferences, and the
/// watch-pairing entry. The console's full settings surface (integrations,
/// AI providers, federation, SLA policies — all `settings.write` admin
/// workflows) stays web-only by design.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({
    super.key,
    required this.client,
    required this.user,
    required this.profile,
    required this.scheme,
    required this.notifications,
    required this.probeServer,
    required this.onServerChanged,
    required this.onSignOut,
    required this.onMfaToggled,
    this.onPairWatch,
  });

  final VigilClient client;
  final UserProfile user;
  final ServerProfile profile;
  final SchemeController? scheme;
  final NotificationPreferencesStore notifications;

  /// Probes a candidate server URL (throws on unreachable / not Vigil) —
  /// the app root supplies it, mirroring onboarding's gate.
  final ServerUrlProbe probeServer;

  /// The user saved a (probe-passed) server profile — the app root persists
  /// it and re-authenticates against the new server.
  final ValueChanged<ServerProfile> onServerChanged;
  final VoidCallback onSignOut;
  final VoidCallback onMfaToggled;

  /// Non-null once the watch companion's token handoff lands; null keeps
  /// the pairing entry in its honest not-yet state.
  final VoidCallback? onPairWatch;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ServerSection(
                profile: profile,
                probeServer: probeServer,
                onServerChanged: onServerChanged,
              ),
              const SizedBox(height: 14),
              AccountSection(
                client: client,
                user: user,
                onSignOut: onSignOut,
              ),
              const SizedBox(height: 14),
              SecuritySection(
                client: client,
                user: user,
                onMfaToggled: onMfaToggled,
              ),
              const SizedBox(height: 14),
              if (scheme != null) _AppearanceSection(scheme: scheme!),
              const SizedBox(height: 14),
              _NotificationsSection(store: notifications),
              const SizedBox(height: 14),
              WatchPairingCard(onPairWatch: onPairWatch),
            ],
          ),
        ),
      ),
    );
  }
}

/// The Appearance row: the same server-persisted scheme the console's
/// ColorSchemeContext owns — the flip is local, persistence is the
/// controller's, and the copy says where the setting lives.
class _AppearanceSection extends StatelessWidget {
  const _AppearanceSection({required this.scheme});

  final SchemeController scheme;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    return AnimatedBuilder(
      animation: scheme,
      builder: (context, _) {
        final light = scheme.scheme == VigilScheme.light;
        return SectionCard(
          icon: VigilIcons.sun,
          title: 'Appearance',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SwitchListTile(
                key: const Key('settings-scheme-switch'),
                contentPadding: EdgeInsets.zero,
                value: light,
                onChanged: (value) =>
                    scheme.set(value ? VigilScheme.light : VigilScheme.dark),
                title: Text(
                  light ? 'Light theme' : 'Dark theme',
                  style:
                      VigilTypography.bodyStrong.copyWith(color: colors.tx0),
                ),
                subtitle: Text(
                  'Saved to your account — the console picks it up too.',
                  style: VigilTypography.meta.copyWith(color: colors.tx2),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// Local notification preferences — client-side only. Vigil has no server
/// push today, so the copy says what these actually govern.
class _NotificationsSection extends StatefulWidget {
  const _NotificationsSection({required this.store});

  final NotificationPreferencesStore store;

  @override
  State<_NotificationsSection> createState() => _NotificationsSectionState();
}

class _NotificationsSectionState extends State<_NotificationsSection> {
  NotificationPreferences? _prefs;
  bool _loaded = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final prefs = await widget.store.read();
    if (!mounted) return;
    setState(() {
      _prefs = prefs;
      _loaded = true;
    });
  }

  Future<void> _update(NotificationPreferences prefs) async {
    setState(() => _prefs = prefs);
    await widget.store.save(prefs);
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final prefs = _prefs;
    if (!_loaded || prefs == null) {
      return SectionCard(
        icon: VigilIcons.bell,
        title: 'Notifications',
        child: Text(
          'Loading…',
          style: VigilTypography.meta.copyWith(color: colors.tx3),
        ),
      );
    }
    final severityLabels = {
      for (final s in NotifySeverity.values)
        s: switch (s) {
          NotifySeverity.critical => 'Critical only',
          NotifySeverity.high => 'High and above',
          NotifySeverity.medium => 'Medium and above',
          NotifySeverity.low => 'Everything',
        },
    };
    return SectionCard(
      icon: VigilIcons.bell,
      title: 'Notifications',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SwitchListTile(
            key: const Key('notifications-switch'),
            contentPadding: EdgeInsets.zero,
            value: prefs.enabled,
            onChanged: (value) => _update(prefs.copyWith(enabled: value)),
            title: Text(
              'Local notifications',
              style: VigilTypography.bodyStrong.copyWith(color: colors.tx0),
            ),
            subtitle: Text(
              'On this device while Vigil is running. There is no server '
              'push yet, so nothing arrives while the app is closed.',
              style: VigilTypography.meta.copyWith(color: colors.tx2),
            ),
          ),
          if (prefs.enabled)
            ListTile(
              key: const Key('notifications-severity'),
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: Text(
                'Minimum severity',
                style: VigilTypography.bodyStrong.copyWith(color: colors.tx0),
              ),
              trailing: DropdownMenu<NotifySeverity>(
                key: const Key('notifications-severity-select'),
                initialSelection: prefs.minimumSeverity,
                dropdownMenuEntries: [
                  for (final s in NotifySeverity.values)
                    DropdownMenuEntry(
                      value: s,
                      label: severityLabels[s]!,
                    ),
                ],
                onSelected: (value) {
                  if (value != null) {
                    _update(prefs.copyWith(minimumSeverity: value));
                  }
                },
              ),
            ),
        ],
      ),
    );
  }
}
