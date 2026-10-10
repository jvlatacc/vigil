import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/api/config_api.dart';
import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/auth/session.dart';
import 'package:vigil_flutter/auth/token_store.dart';
import 'package:vigil_flutter/onboarding/server_profile.dart';
import 'package:vigil_flutter/settings/notification_preferences.dart';
import 'package:vigil_flutter/settings/scheme_controller.dart';
import 'package:vigil_flutter/settings/settings_screen.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

import '../helpers/wired_vigil.dart';

/// The settings pane as composed: theme persistence through the server's
/// `/api/config/theme` (console parity — [SchemeController] mirrors
/// ColorSchemeContext), local notification preferences (no server push
/// exists), and the watch-pairing entry point in its honest not-yet state.
void main() {
  Widget pane({
    required VigilClient client,
    required SchemeController scheme,
    required NotificationPreferencesStore notifications,
  }) =>
      MaterialApp(
        theme: buildVigilThemeData(Brightness.dark),
        home: Scaffold(
          body: SingleChildScrollView(
            child: SettingsScreen(
              client: client,
              user: const UserProfile(
                username: 'jane',
                email: 'jane@corp.example',
                permissions: <String, bool>{'settings.read': true},
              ),
              profile: const ServerProfile(baseUrl: 'https://soc.example.com'),
              scheme: scheme,
              notifications: notifications,
              probeServer: (url) async => {'version': '1'},
              onServerChanged: (_) {},
              onSignOut: () {},
              onMfaToggled: () {},
            ),
          ),
        ),
      );

  VigilClient clientWith(RoutedAdapter api) => wiredClient(
        auth: RoutedAdapter(defaultAuthHandler),
        api: api,
        tokenStore:
            InMemoryTokenStore(accessToken: 'access-1', refreshToken: 'r-1'),
      );

  /// The pane is a long scroll view — a control below the fold is in the
  /// tree but unhittable until scrolled into view.
  Future<void> tapControl(WidgetTester tester, Key key) async {
    await tester.ensureVisible(find.byKey(key));
    await tester.tap(find.byKey(key));
    await tester.pumpAndSettle();
  }

  test('theme: a stored light scheme loads from the server', () async {
    final api = RoutedAdapter((options, r) {
      if (r.path.contains('/api/config/theme')) {
        return json(200, {'theme': 'light'});
      }
      return defaultApiHandler(options, r);
    });
    final scheme = SchemeController(configApi: clientWith(api).config);
    await scheme.load();

    expect(scheme.scheme, VigilScheme.light,
        reason: 'the server-persisted scheme is the console parity contract');
  });

  testWidgets('theme: flipping the switch persists light to the server',
      (tester) async {
    final posts = <Object?>[];
    final api = RoutedAdapter((options, r) {
      if (r.path.contains('/api/config/theme') && r.method == 'POST') {
        posts.add(r.body);
        return json(200, {'theme': 'light'});
      }
      if (r.path.contains('/api/config/theme')) {
        return json(200, {'theme': 'dark'});
      }
      return defaultApiHandler(options, r);
    });
    final client = clientWith(api);
    final scheme = SchemeController(configApi: client.config);
    await tester.pumpWidget(pane(
      client: client,
      scheme: scheme,
      notifications: InMemoryNotificationPreferencesStore(),
    ));
    await tester.pumpAndSettle();

    await tapControl(tester, const Key('settings-scheme-switch'));

    expect(scheme.scheme, VigilScheme.light, reason: 'the flip is local-first');
    expect(
      posts,
      [
        {'theme': 'light'}
      ],
      reason: 'console parity: the same /api/config/theme POST the web '
          'console sends (configApi.setTheme)',
    );
  });

  testWidgets('theme: a refused POST still flips locally — viewer parity',
      (tester) async {
    final api = RoutedAdapter((options, r) {
      if (r.path.contains('/api/config/theme') && r.method == 'POST') {
        return json(403, {'detail': 'settings.write required'});
      }
      if (r.path.contains('/api/config/theme')) {
        return json(200, {'theme': 'dark'});
      }
      return defaultApiHandler(options, r);
    });
    final client = clientWith(api);
    final scheme = SchemeController(configApi: client.config);
    await tester.pumpWidget(pane(
      client: client,
      scheme: scheme,
      notifications: InMemoryNotificationPreferencesStore(),
    ));
    await tester.pumpAndSettle();

    await tapControl(tester, const Key('settings-scheme-switch'));

    expect(scheme.scheme, VigilScheme.light,
        reason:
            'the console flips locally when settings.write is refused; '
            'nothing here may crash or block the visual change');
  });

  testWidgets('notifications: the switch persists locally only', (tester) async {
    final store = InMemoryNotificationPreferencesStore();
    final api = RoutedAdapter(defaultApiHandler);
    await tester.pumpWidget(pane(
      client: clientWith(api),
      scheme: SchemeController(),
      notifications: store,
    ));
    await tester.pumpAndSettle();

    await tapControl(tester, const Key('notifications-switch'));

    final saved = await store.read();
    expect(saved.enabled, true);
    expect(
      api.call('notifications'),
      isNull,
      reason:
          'no server push exists — notification preferences never leave the device',
    );
  });

  testWidgets('watch pairing: the entry point names its honest not-yet state',
      (tester) async {
    await tester.pumpWidget(pane(
      client: clientWith(RoutedAdapter(defaultApiHandler)),
      scheme: SchemeController(),
      notifications: InMemoryNotificationPreferencesStore(),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('watch-card')), findsOneWidget);
  });
}
