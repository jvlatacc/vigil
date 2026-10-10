import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/auth/session.dart';
import 'package:vigil_flutter/onboarding/sign_in_pane.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

import '../helpers/wired_vigil.dart';

/// Sign-in surface against a scripted transport: the MFA step, typed
/// credential errors, and the lockout countdown from the server's
/// `Retry-After` (services/api/routers/auth.py login contract).
void main() {
  Widget pane({
    required VigilClient client,
    required ValueChanged<Session> onSignedIn,
  }) =>
      MaterialApp(
        theme: buildVigilThemeData(Brightness.dark),
        home: Scaffold(
          body: SignInPane(client: client, onSignedIn: onSignedIn),
        ),
      );

  Future<void> enterCredentials(
    WidgetTester tester, {
    String username = 'jane',
    String password = 'correct horse',
  }) async {
    await tester.enterText(find.byKey(const Key('sign-in-username')), username);
    await tester.enterText(find.byKey(const Key('sign-in-password')), password);
  }

  testWidgets('empty submit asks for both fields and sends nothing',
      (tester) async {
    final auth = RoutedAdapter(defaultAuthHandler);
    final api = RoutedAdapter(defaultApiHandler);
    final signedIn = <Session>[];
    await tester.pumpWidget(pane(
      client: wiredClient(auth: auth, api: api),
      onSignedIn: signedIn.add,
    ));

    await tester.tap(find.byKey(const Key('sign-in-submit')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('sign-in-error')), findsOneWidget);
    expect(find.text('Enter your username and password.'), findsOneWidget);
    expect(auth.requests, isEmpty, reason: 'no credentials, no login call');
  });

  testWidgets('wrong credentials show the typed error', (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/login')) {
        return json(401, {'detail': 'bad credentials'});
      }
      return defaultAuthHandler(options, r);
    });
    final api = RoutedAdapter(defaultApiHandler);
    final signedIn = <Session>[];
    await tester.pumpWidget(pane(
      client: wiredClient(auth: auth, api: api),
      onSignedIn: signedIn.add,
    ));

    await enterCredentials(tester);
    await tester.tap(find.byKey(const Key('sign-in-submit')));
    await tester.pumpAndSettle();

    expect(signedIn, isEmpty);
    expect(find.text('Invalid username/email or password'), findsOneWidget);
  });

  testWidgets('a 401 with X-MFA-Required reveals the code field, and the '
      'retry carries mfa_code', (tester) async {
    var loginCalls = 0;
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/login')) {
        loginCalls++;
        if (loginCalls == 1) {
          return json(401, {'detail': 'MFA required'},
              headers: {'x-mfa-required': 'true'});
        }
        return json(200, loginBody());
      }
      return defaultAuthHandler(options, r);
    });
    final api = RoutedAdapter(defaultApiHandler);
    final signedIn = <Session>[];
    await tester.pumpWidget(pane(
      client: wiredClient(auth: auth, api: api),
      onSignedIn: signedIn.add,
    ));

    await enterCredentials(tester);
    await tester.tap(find.byKey(const Key('sign-in-submit')));
    await tester.pumpAndSettle();

    // The MFA step is visible, the button invites the code.
    expect(find.byKey(const Key('sign-in-mfa')), findsOneWidget);
    expect(find.text('Verify and sign in'), findsOneWidget);
    expect(signedIn, isEmpty);

    await tester.enterText(find.byKey(const Key('sign-in-mfa')), '123456');
    await tester.tap(find.byKey(const Key('sign-in-submit')));
    await tester.pumpAndSettle();

    expect(signedIn, hasLength(1), reason: 'the MFA retry signs in');
    final login = auth.call('/api/auth/login')!;
    expect((login.body as Map)['mfa_code'], '123456',
        reason: 'the retry carries the TOTP code');
    expect(signedIn.single.user.username, 'jane');
  });

  testWidgets('a wrong TOTP code reads as invalid MFA, keeping the field',
      (tester) async {
    var loginCalls = 0;
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/login')) {
        loginCalls++;
        if (loginCalls == 1) {
          return json(401, {'detail': 'MFA required'},
              headers: {'x-mfa-required': 'true'});
        }
        return json(401, {'detail': 'bad code'});
      }
      return defaultAuthHandler(options, r);
    });
    final api = RoutedAdapter(defaultApiHandler);
    await tester.pumpWidget(pane(
      client: wiredClient(auth: auth, api: api),
      onSignedIn: (_) {},
    ));

    await enterCredentials(tester);
    await tester.tap(find.byKey(const Key('sign-in-submit')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('sign-in-mfa')), '000000');
    await tester.tap(find.byKey(const Key('sign-in-submit')));
    await tester.pumpAndSettle();

    expect(find.text('Invalid MFA code.'), findsOneWidget);
    expect(find.byKey(const Key('sign-in-mfa')), findsOneWidget,
        reason: 'the field stays open for another try');
  });

  testWidgets('a 423 with Retry-After counts down and releases the button',
      (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/login')) {
        return json(423, {'detail': 'locked'}, headers: {'retry-after': '90'});
      }
      return defaultAuthHandler(options, r);
    });
    final api = RoutedAdapter(defaultApiHandler);
    await tester.pumpWidget(pane(
      client: wiredClient(auth: auth, api: api),
      onSignedIn: (_) {},
    ));

    await enterCredentials(tester);
    await tester.tap(find.byKey(const Key('sign-in-submit')));
    await tester.pumpAndSettle();

    expect(find.text('Account locked — retry in 1 min 30s.'), findsOneWidget);
    final FilledButton locked =
        tester.widget(find.byKey(const Key('sign-in-submit')));
    expect(locked.onPressed, isNull, reason: 'the lock disables sign-in');

    await tester.pump(const Duration(seconds: 60));
    expect(find.text('Account locked — retry in 30s.'), findsOneWidget);

    await tester.pump(const Duration(seconds: 30));
    expect(find.byKey(const Key('sign-in-error')), findsNothing,
        reason: 'the countdown clears the lock');
    final FilledButton released =
        tester.widget(find.byKey(const Key('sign-in-submit')));
    expect(released.onPressed, isNotNull);
  });

  testWidgets('a 423 without Retry-After shows the lock without a countdown',
      (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/login')) return json(423, {});
      return defaultAuthHandler(options, r);
    });
    final api = RoutedAdapter(defaultApiHandler);
    await tester.pumpWidget(pane(
      client: wiredClient(auth: auth, api: api),
      onSignedIn: (_) {},
    ));

    await enterCredentials(tester);
    await tester.tap(find.byKey(const Key('sign-in-submit')));
    await tester.pumpAndSettle();

    expect(
      find.text('Account locked due to repeated failed sign-in attempts.'),
      findsOneWidget,
    );
  });
}
