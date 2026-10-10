import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/auth/session.dart';
import 'package:vigil_flutter/auth/token_store.dart';
import 'package:vigil_flutter/settings/security_section.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

import '../helpers/fake_adapter.dart';
import '../helpers/wired_vigil.dart';

/// Security surface against a scripted transport — the MFA enrollment flow
/// end to end (setup → secret/URI → TOTP verify → one-time recovery codes),
/// regeneration, the disable flow, and every typed failure the backend
/// answers with (services/api/routers/auth.py MFA contract).
void main() {
  Widget pane({
    required VigilClient client,
    required UserProfile user,
    required VoidCallback onMfaToggled,
  }) =>
      MaterialApp(
        theme: buildVigilThemeData(Brightness.dark),
        home: Scaffold(
          body: SingleChildScrollView(
            child: SecuritySection(
              client: client,
              user: user,
              onMfaToggled: onMfaToggled,
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

  ResponseBody setupOk(RequestOptions options, RecordedRequest r) {
    if (r.path.contains('/api/auth/mfa/setup')) {
      return json(200, {
        'secret': 'JBSWY3DPEHPK3PXP',
        'qr_uri':
            'otpauth://totp/Vigil:jane@corp.example?secret=JBSWY3DPEHPK3PXP&issuer=Vigil',
      });
    }
    return defaultAuthHandler(options, r);
  }

  testWidgets('an unenrolled account offers Set up MFA and says so',
      (tester) async {
    await tester.pumpWidget(pane(
      client: clientWith(RoutedAdapter(defaultAuthHandler)),
      user: const UserProfile(username: 'jane', mfaEnabled: false,
          permissions: <String, bool>{'settings.read': true}),
      onMfaToggled: () {},
    ));
    await tester.pumpAndSettle();

    expect(find.text('MFA is not enrolled for this account.'), findsOneWidget);
    expect(find.byKey(const Key('mfa-setup')), findsOneWidget);
    expect(find.byKey(const Key('mfa-regenerate')), findsNothing);
  });

  testWidgets('enrollment: setup reveals the secret and otpauth URI',
      (tester) async {
    final auth = RoutedAdapter(setupOk);
    await tester.pumpWidget(pane(
      client: clientWith(auth),
      user: const UserProfile(
        username: 'jane',
        mfaEnabled: false,
        permissions: <String, bool>{'settings.read': true},
      ),
      onMfaToggled: () {},
    ));

    await tester.tap(find.byKey(const Key('mfa-setup')));
    await tester.pumpAndSettle();

    expect(find.text('JBSWY3DPEHPK3PXP'), findsOneWidget,
        reason: 'the secret is shown for manual authenticator entry');
    expect(find.byKey(const Key('mfa-qr-uri')), findsOneWidget);
    expect(find.byKey(const Key('mfa-code-field')), findsOneWidget);
  });

  testWidgets('enrollment: a wrong code stays in the form with the typed error',
      (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/mfa/verify')) {
        return json(400, {'detail': 'invalid code'});
      }
      return setupOk(options, r);
    });
    await tester.pumpWidget(pane(
      client: clientWith(auth),
      user: const UserProfile(username: 'jane', mfaEnabled: false,
          permissions: <String, bool>{'settings.read': true}),
      onMfaToggled: () {},
    ));

    await tester.tap(find.byKey(const Key('mfa-setup')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('mfa-code-field')), '000000');
    await tester.tap(find.byKey(const Key('mfa-verify')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('security-error')), findsOneWidget);
    expect(find.text('Invalid MFA code.'), findsOneWidget);
    expect(find.byKey(const Key('mfa-code-field')), findsOneWidget,
        reason: 'MFA stays off — the enrollment form is still open');
  });

  testWidgets('enrollment: verifying enables MFA and shows one-time codes',
      (tester) async {
    var toggled = 0;
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/mfa/verify')) {
        return json(200, {
          'recovery_codes': ['4f1a-9c2b', '77e0-d3aa'],
        });
      }
      return setupOk(options, r);
    });
    await tester.pumpWidget(pane(
      client: clientWith(auth),
      user: const UserProfile(username: 'jane', mfaEnabled: false,
          permissions: <String, bool>{'settings.read': true}),
      onMfaToggled: () => toggled++,
    ));

    await tester.tap(find.byKey(const Key('mfa-setup')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('mfa-code-field')), '123456');
    await tester.tap(find.byKey(const Key('mfa-verify')));
    await tester.pumpAndSettle();

    final posted = auth.call('mfa/verify');
    expect(posted!.body, {'code': '123456'});
    expect(find.byKey(const Key('recovery-codes-note')), findsOneWidget);
    expect(find.text('4f1a-9c2b'), findsOneWidget,
        reason: 'recovery codes are shown exactly once');
    expect(find.text('77e0-d3aa'), findsOneWidget);
    expect(toggled, 1, reason: 'the parent refreshes /auth/me after the flip');
  });

  testWidgets('an enrolled account offers regeneration and disable',
      (tester) async {
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/mfa/recovery-codes')) {
        return json(200, {
          'recovery_codes': ['aa11-bb22'],
        });
      }
      return defaultAuthHandler(options, r);
    });
    await tester.pumpWidget(pane(
      client: clientWith(auth),
      user: const UserProfile(
        username: 'jane',
        mfaEnabled: true,
        permissions: <String, bool>{'settings.read': true},
      ),
      onMfaToggled: () {},
    ));
    await tester.pumpAndSettle();

    expect(
      find.text('MFA enabled — a TOTP code is required at sign-in.'),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const Key('mfa-regenerate')));
    await tester.pumpAndSettle();

    expect(find.text('aa11-bb22'), findsOneWidget);
    expect(find.byKey(const Key('recovery-codes-note')), findsOneWidget);
  });

  testWidgets('regenerating after MFA was disabled elsewhere resyncs to the server',
      (tester) async {
    var toggled = 0;
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/mfa/recovery-codes')) {
        return json(400, {'detail': 'MFA is not enabled'});
      }
      return defaultAuthHandler(options, r);
    });
    await tester.pumpWidget(pane(
      client: clientWith(auth),
      user: const UserProfile(
        username: 'jane',
        mfaEnabled: true,
        permissions: <String, bool>{'settings.read': true},
      ),
      onMfaToggled: () => toggled++,
    ));

    await tester.tap(find.byKey(const Key('mfa-regenerate')));
    await tester.pumpAndSettle();

    expect(toggled, 1,
        reason: 'the server disabled MFA under us — the parent resyncs /auth/me '
            'instead of the section arguing with it');
    expect(find.byKey(const Key('security-error')), findsNothing);
    expect(find.byKey(const Key('recovery-codes-note')), findsNothing,
        reason: 'no codes exist — the card falls back to the server\'s truth');
  });

  testWidgets('disable confirms, deletes the enrollment, and refreshes the user',
      (tester) async {
    var toggled = 0;
    final auth = RoutedAdapter((options, r) {
      if (r.path.contains('/api/auth/mfa') && r.method == 'DELETE') {
        return ResponseBody.fromString('', 204);
      }
      return defaultAuthHandler(options, r);
    });
    await tester.pumpWidget(pane(
      client: clientWith(auth),
      user: const UserProfile(
        username: 'jane',
        mfaEnabled: true,
        permissions: <String, bool>{'settings.read': true},
      ),
      onMfaToggled: () => toggled++,
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('mfa-disable')));
    await tester.pumpAndSettle();
    expect(find.text('Disable MFA?'), findsOneWidget,
        reason: 'disabling is guarded by a confirmation');

    await tester.tap(find.byKey(const Key('mfa-disable-confirm')));
    await tester.pumpAndSettle();

    expect(
      auth.call('/api/auth/mfa')!.method,
      'DELETE',
      reason: 'the disable reached the server as a DELETE',
    );
    expect(toggled, 1);
  });
}
