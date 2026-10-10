import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/app.dart';
import 'package:vigil_flutter/auth/token_store.dart';
import 'package:vigil_flutter/onboarding/server_profile.dart';
import 'package:vigil_flutter/shell/vigil_shell.dart';

import 'helpers/wired_vigil.dart';

/// The app root's boot decisions against a scripted transport: onboarding
/// on a fresh install, shell on a stored session (with the server-persisted
/// scheme), the deep-link permission check, revoked sessions, and boot
/// failures with retry.
void main() {
  Widget app({
    required RoutedAdapter auth,
    required RoutedAdapter api,
    ServerProfileStore? profiles,
    TokenStore? tokens,
    String? initialRoute,
    Object? keySeed,
  }) =>
      VigilApp(
        // A key forces a fresh element/state when one test pumps several
        // app instances back to back — same-type unkeyed roots reuse the
        // first instance's captured stores and boot result.
        key: keySeed == null ? null : ValueKey(keySeed),
        profileStore: profiles ?? InMemoryServerProfileStore(),
        tokenStore: tokens ?? InMemoryTokenStore(),
        clientFactory: ({
          required baseUrl,
          required tokenStore,
          required userAgent,
        }) =>
            VigilClient(
              baseUrl: baseUrl,
              tokenStore: tokenStore,
              userAgent: userAgent,
              authAdapter: auth,
              apiAdapter: api,
            ),
        initialRoute: initialRoute,
      );

  Future<void> readySession(
    WidgetTester tester, {
    required RoutedAdapter auth,
    required RoutedAdapter api,
    Map<String, bool> permissions = const {},
    String? initialRoute,
    Object? keySeed,
  }) async {
    final profiles = InMemoryServerProfileStore(
      profile: const ServerProfile(baseUrl: testBaseUrl),
    );
    final tokens = InMemoryTokenStore()
      ..save(accessToken: 'access-1', refreshToken: 'refresh-1');
    await tester.pumpWidget(app(
      auth: auth,
      api: api,
      profiles: profiles,
      tokens: tokens,
      initialRoute: initialRoute,
      keySeed: keySeed,
    ));
    await tester.pumpAndSettle();
  }

  testWidgets('a fresh install lands on onboarding', (tester) async {
    final auth = RoutedAdapter(defaultAuthHandler);
    final api = RoutedAdapter(defaultApiHandler);
    await tester.pumpWidget(
        app(auth: auth, api: api, profiles: InMemoryServerProfileStore()));
    await tester.pumpAndSettle();

    expect(find.text('Connect to Vigil'), findsOneWidget);
  });

  testWidgets('a stored session opens the shell with the server-persisted '
      'scheme', (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/me')) {
        return json(200, userBody(permissions: {
          'ai_decisions.approve': true,
          'cases.read': true,
          'settings.read': true,
        }));
      }
      return defaultAuthHandler(options, r);
    });
    final api = RoutedAdapter((options, r) {
      if (r.path.contains('/api/config/theme') && r.method == 'GET') {
        return json(200, {'theme': 'light'});
      }
      return defaultApiHandler(options, r);
    });
    await readySession(tester, auth: auth, api: api);

    expect(
      find.descendant(
        of: find.byType(AppBar),
        matching: find.text('What needs a person'),
      ),
      findsOneWidget,
    );
    final MaterialApp material =
        tester.widget(find.byType(MaterialApp));
    expect(material.themeMode, ThemeMode.light,
        reason: 'the server-persisted scheme wins over the dark default');
  });

  testWidgets('the scheme toggle flips locally and persists to the server',
      (tester) async {
    // The server says light; the tap must flip to dark locally and POST
    // the new scheme.
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/me')) {
        return json(200, userBody(permissions: {
          'ai_decisions.approve': true,
          'cases.read': true,
          'settings.read': true,
        }));
      }
      return defaultAuthHandler(options, r);
    });
    final api = RoutedAdapter((options, r) {
      if (r.path.contains('/api/config/theme') && r.method == 'GET') {
        return json(200, {'theme': 'light'});
      }
      return defaultApiHandler(options, r);
    });
    await readySession(tester, auth: auth, api: api);

    await tester.tap(find.byKey(const Key('scheme-toggle')));
    await tester.pumpAndSettle();

    final post = api.call('/api/config/theme')!;
    expect(post.method, 'POST');
    expect((post.body as Map)['theme'], 'dark');
    final MaterialApp material =
        tester.widget(find.byType(MaterialApp));
    expect(material.themeMode, ThemeMode.dark);
  });

  testWidgets('every gated deep link lands on the denial screen',
      (tester) async {
    // The console's SCREEN_PERMS map, walked entry by entry at the layer
    // that enforces it: a route the role cannot see must never open the
    // screen — it lands on the explanatory denial instead.
    const gatedRoutes = {
      '/home': 'No access to Home',
      '/decisions': 'No access to AI Decisions',
      '/cases': 'No access to Cases',
      '/settings': 'No access to Settings',
    };
    for (final entry in gatedRoutes.entries) {
      final auth = RoutedAdapter((options, r) {
        if (r.path.contains('/api/auth/me')) return json(200, userBody());
        return defaultAuthHandler(options, r);
      });
      final api = RoutedAdapter(defaultApiHandler);
      await readySession(
        tester,
        auth: auth,
        api: api,
        initialRoute: entry.key,
        keySeed: entry.key,
      );

      expect(find.byType(PermissionDeniedScreen), findsOneWidget,
          reason: '${entry.key} is gated by the console map');
      expect(find.text(entry.value), findsOneWidget,
          reason: 'the denial names the screen');
    }
  });

  testWidgets('a revoked session falls back to sign-in', (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/me')) return json(401, {'detail': 'expired'});
      if (r.path.contains('/api/auth/refresh')) {
        return json(401, {'detail': 'blacklisted'});
      }
      return defaultAuthHandler(options, r);
    });
    final api = RoutedAdapter(defaultApiHandler);
    await readySession(tester, auth: auth, api: api);

    expect(find.text('Sign in to Vigil'), findsOneWidget);
  });

  testWidgets('a boot failure shows the error pane and Retry re-runs it',
      (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/me')) {
        throw DioException.connectionError(
          requestOptions: options,
          reason: 'Connection refused',
        );
      }
      return defaultAuthHandler(options, r);
    });
    final api = RoutedAdapter(defaultApiHandler);
    await readySession(tester, auth: auth, api: api);

    expect(find.text('Vigil could not reach its server'), findsOneWidget);

    await tester.tap(find.byKey(const Key('boot-retry')));
    await tester.pumpAndSettle();

    // Still failing — the retry re-ran the boot (a second /auth/me call).
    expect(find.text('Vigil could not reach its server'), findsOneWidget);
    expect(
      auth.requests.where((r) => r.path.contains('/api/auth/me')).length,
      2,
    );
  });

  testWidgets('sign-out revokes server-side and returns to sign-in',
      (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/me')) {
        return json(200, userBody(permissions: {
          'ai_decisions.approve': true,
          'cases.read': true,
          'settings.read': true,
        }));
      }
      return defaultAuthHandler(options, r);
    });
    final api = RoutedAdapter(defaultApiHandler);
    await readySession(tester, auth: auth, api: api);

    await tester.tap(find.byKey(const Key('account-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('sign-out-item')));
    await tester.pumpAndSettle();

    final logout = auth.call('/api/auth/logout')!;
    expect(logout.method, 'POST');
    expect((logout.body as Map)['refresh_token'], 'refresh-1',
        reason: 'bearer clients revoke via the body refresh token');
    expect(logout.header('authorization'), 'Bearer access-1');
    expect(find.text('Sign in to Vigil'), findsOneWidget);
  });
}
