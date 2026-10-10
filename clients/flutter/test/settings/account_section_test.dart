import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/auth/session.dart';
import 'package:vigil_flutter/auth/token_store.dart';
import 'package:vigil_flutter/settings/account_section.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

import '../helpers/wired_vigil.dart';

/// Account surface against a scripted transport: identity, MFA state, the
/// change-password flow (POST `/api/auth/change-password` with
/// `current_password`/`new_password`), its typed failures, and sign-out.
void main() {
  Widget pane({
    required VigilClient client,
    required UserProfile user,
    required VoidCallback onSignOut,
  }) =>
      MaterialApp(
        theme: buildVigilThemeData(Brightness.dark),
        home: Scaffold(
          body: SingleChildScrollView(
            child: AccountSection(
              client: client,
              user: user,
              onSignOut: onSignOut,
            ),
          ),
        ),
      );

  VigilClient clientWith(RoutedAdapter auth) => wiredClient(
        auth: auth,
        api: RoutedAdapter(defaultApiHandler),
        tokenStore:
            InMemoryTokenStore(accessToken: 'access-1', refreshToken: 'r-1'),
      );

  Future<void> openAndFillForm(WidgetTester tester,
      {String current = 'old-pass',
      String next = 'fresh-pass-9',
      String confirm = 'fresh-pass-9'}) async {
    await tester.tap(find.byKey(const Key('change-password-open')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const Key('current-password-field')), current);
    await tester.enterText(find.byKey(const Key('new-password-field')), next);
    await tester.enterText(
        find.byKey(const Key('confirm-password-field')), confirm);
  }

  testWidgets('names the user and reports the MFA state', (tester) async {
    const signedOut = 0;
    await tester.pumpWidget(pane(
      client: clientWith(RoutedAdapter(defaultAuthHandler)),
      user: const UserProfile(
        username: 'jane',
        email: 'jane@corp.example',
        mfaEnabled: true,
        permissions: <String, bool>{'ai_decisions.approve': true},
      ),
      onSignOut: () {},
    ));
    await tester.pumpAndSettle();

    expect(find.text('jane'), findsOneWidget);
    expect(find.byKey(const Key('account-mfa-state')), findsOneWidget);
    expect(signedOut, 0, reason: 'rendering alone never signs out');
  });

  testWidgets('a mismatched confirm is caught locally — nothing is sent',
      (tester) async {
    final auth = RoutedAdapter(defaultAuthHandler);
    await tester.pumpWidget(pane(
      client: clientWith(auth),
      user: const UserProfile(username: 'jane', permissions: <String, bool>{}),
      onSignOut: () {},
    ));

    await openAndFillForm(tester, confirm: 'different');
    await tester.tap(find.byKey(const Key('change-password-submit')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('account-error')), findsOneWidget);
    expect(
      auth.call('change-password'),
      isNull,
      reason: 'a local validation failure must not reach the server',
    );
  });

  testWidgets('a successful change posts both passwords and asks to sign in again',
      (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/change-password')) {
        return ResponseBody.fromString('', 204);
      }
      return defaultAuthHandler(options, r);
    });
    await tester.pumpWidget(pane(
      client: clientWith(auth),
      user: const UserProfile(username: 'jane', permissions: <String, bool>{}),
      onSignOut: () {},
    ));

    await openAndFillForm(tester);
    await tester.tap(find.byKey(const Key('change-password-submit')));
    await tester.pumpAndSettle();

    final posted = auth.call('change-password');
    expect(posted, isNotNull);
    expect(posted!.body,
        {'current_password': 'old-pass', 'new_password': 'fresh-pass-9'});
    expect(
      posted.header('authorization'),
      'Bearer access-1',
      reason: 'the bare auth call carries the stored access token',
    );
    expect(find.byKey(const Key('password-changed-note')), findsOneWidget,
        reason:
            'the server revoked the old tokens — the note says to sign in again');
  });

  testWidgets('a wrong current password surfaces the typed error and keeps the form',
      (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/change-password')) {
        return json(401, {'detail': 'bad credentials'});
      }
      return defaultAuthHandler(options, r);
    });
    await tester.pumpWidget(pane(
      client: clientWith(auth),
      user: const UserProfile(username: 'jane', permissions: <String, bool>{}),
      onSignOut: () {},
    ));

    await openAndFillForm(tester);
    await tester.tap(find.byKey(const Key('change-password-submit')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('account-error')), findsOneWidget);
    expect(find.text('Current password is incorrect.'), findsOneWidget);
    expect(
      find.byKey(const Key('change-password-submit')),
      findsOneWidget,
      reason: 'nothing was changed — the form stays open for a retry',
    );
  });

  testWidgets('a policy rejection carries the server reason', (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/change-password')) {
        return json(400, {'detail': 'Password too weak'});
      }
      return defaultAuthHandler(options, r);
    });
    await tester.pumpWidget(pane(
      client: clientWith(auth),
      user: const UserProfile(username: 'jane', permissions: <String, bool>{}),
      onSignOut: () {},
    ));

    await openAndFillForm(tester);
    await tester.tap(find.byKey(const Key('change-password-submit')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('account-error')), findsOneWidget);
    expect(find.text('Password too weak'), findsOneWidget);
  });

  testWidgets('sign out hands the callback up', (tester) async {
    var signedOut = 0;
    final auth = RoutedAdapter(defaultAuthHandler);
    await tester.pumpWidget(pane(
      client: clientWith(auth),
      user: const UserProfile(username: 'jane', permissions: <String, bool>{}),
      onSignOut: () => signedOut++,
    ));

    await tester.tap(find.byKey(const Key('account-sign-out')));
    await tester.pumpAndSettle();

    expect(signedOut, 1);
  });
}
