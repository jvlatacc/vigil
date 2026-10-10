import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/auth/session.dart';
import 'package:vigil_flutter/auth/token_store.dart';
import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/onboarding/onboarding_flow.dart';
import 'package:vigil_flutter/onboarding/server_profile.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

import '../helpers/wired_vigil.dart';

/// The onboarding flow against a scripted transport: server-URL validation
/// against `/api/health`, first-admin bootstrap on an empty instance, and
/// the fall back to sign-in when the bootstrap window has closed.
void main() {
  final profiles = InMemoryServerProfileStore();
  final signedIn = <Session>[];

  Widget flow({
    required RoutedAdapter auth,
    required RoutedAdapter api,
  }) =>
      MaterialApp(
        theme: buildVigilThemeData(Brightness.dark),
        home: Scaffold(
          body: OnboardingFlow(
            profileStore: profiles,
            tokenStore: InMemoryTokenStore(),
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
            onFinished: (client, session) => signedIn.add(session),
          ),
        ),
      );

  Future<void> connect(WidgetTester tester, String url) async {
    await tester.enterText(find.byKey(const Key('server-url-field')), url);
    await tester.tap(find.byKey(const Key('server-url-submit')));
    await tester.pumpAndSettle();
  }

  setUp(() {
    profiles.clear();
    signedIn.clear();
  });

  testWidgets('a URL without a scheme is refused before any request',
      (tester) async {
    final auth = RoutedAdapter(defaultAuthHandler);
    final api = RoutedAdapter(defaultApiHandler);
    await tester.pumpWidget(flow(auth: auth, api: api));

    await connect(tester, 'soc.example.com:6987');

    expect(find.byKey(const Key('server-url-error')), findsOneWidget);
    expect(
      find.text('Enter the full server URL, e.g. https://soc.example.com:6987'),
      findsOneWidget,
    );
    expect(auth.requests, isEmpty);
    expect(api.requests, isEmpty);
  });

  testWidgets('an unreachable server reads as a connection failure',
      (tester) async {
    final auth = RoutedAdapter((options, r) {
      throw DioException.connectionError(
        requestOptions: options,
        reason: 'Connection refused',
      );
    });
    final api = RoutedAdapter((options, r) {
      throw DioException.connectionError(
        requestOptions: options,
        reason: 'Connection refused',
      );
    });
    await tester.pumpWidget(flow(auth: auth, api: api));

    await connect(tester, 'https://soc.example.com:6987');

    expect(find.byKey(const Key('server-url-error')), findsOneWidget);
    expect(
      find.text(
          "Couldn't reach a Vigil server at https://soc.example.com:6987."),
      findsOneWidget,
    );
  });

  testWidgets('a non-Vigil server is named as such', (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/health')) return json(200, {'hello': 'world'});
      return defaultAuthHandler(options, r);
    });
    final api = RoutedAdapter(defaultApiHandler);
    await tester.pumpWidget(flow(auth: auth, api: api));

    await connect(tester, 'https://not-vigil.example.com');

    expect(
      find.text('That URL answered, but not like a Vigil server. '
          'Check the address and port.'),
      findsOneWidget,
    );
  });

  testWidgets('a healthy server is stored and leads to sign-in',
      (tester) async {
    final auth = RoutedAdapter(defaultAuthHandler);
    final api = RoutedAdapter(defaultApiHandler);
    await tester.pumpWidget(flow(auth: auth, api: api));

    await connect(tester, 'https://soc.example.com:6987');

    expect(find.text('Sign in to Vigil'), findsOneWidget);
    expect(find.text('https://soc.example.com:6987'), findsOneWidget,
        reason: 'the pane names the server being signed into');
    expect(
      await profiles.read(),
      const ServerProfile(
        baseUrl: 'https://soc.example.com:6987',
      ),
    );
  });

  testWidgets(
      'an empty instance leads to first-admin bootstrap, which '
      'creates the account and signs in', (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/bootstrap') && r.method == 'GET') {
        return json(200, {'required': true});
      }
      return defaultAuthHandler(options, r);
    });
    final api = RoutedAdapter(defaultApiHandler);
    await tester.pumpWidget(flow(auth: auth, api: api));

    await connect(tester, 'https://soc.example.com:6987');

    expect(find.text('Create the first account'), findsOneWidget);

    await tester.enterText(
        find.byKey(const Key('bootstrap-username')), 'admin');
    await tester.enterText(
        find.byKey(const Key('bootstrap-email')), 'admin@corp.example');
    await tester.enterText(
        find.byKey(const Key('bootstrap-password')), 'correct horse');
    await tester.tap(find.byKey(const Key('bootstrap-submit')));
    await tester.pumpAndSettle();

    expect(signedIn, hasLength(1), reason: 'bootstrap signs in right away');
    expect(signedIn.single.user.username, 'jane');

    final created = auth.call('/api/auth/bootstrap')!;
    expect(created.method, 'POST');
    expect((created.body as Map)['username'], 'admin');
    expect((created.body as Map)['email'], 'admin@corp.example');
  });

  testWidgets(
      'a closed bootstrap window falls back to sign-in with the '
      "server's explanation", (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/bootstrap') && r.method == 'GET') {
        return json(200, {'required': true});
      }
      if (r.path.contains('/api/auth/bootstrap')) {
        return json(403, {'detail': 'An account already exists.'});
      }
      return defaultAuthHandler(options, r);
    });
    final api = RoutedAdapter(defaultApiHandler);
    await tester.pumpWidget(flow(auth: auth, api: api));

    await connect(tester, 'https://soc.example.com:6987');
    await tester.enterText(
        find.byKey(const Key('bootstrap-username')), 'admin');
    await tester.enterText(
        find.byKey(const Key('bootstrap-email')), 'admin@corp.example');
    await tester.enterText(
        find.byKey(const Key('bootstrap-password')), 'correct horse');
    await tester.tap(find.byKey(const Key('bootstrap-submit')));
    await tester.pumpAndSettle();

    expect(find.text('Sign in to Vigil'), findsOneWidget);
    expect(find.byKey(const Key('sign-in-error')), findsOneWidget);
    expect(find.text('An account already exists.'), findsOneWidget);
    expect(signedIn, isEmpty);
  });
}
