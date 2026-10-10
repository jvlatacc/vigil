import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/onboarding/server_profile.dart';
import 'package:vigil_flutter/settings/server_section.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

/// Server profile management against a scripted probe: showing the connected
/// server, editing it (save re-probes — a server switch invalidates the
/// session), test-connection, and the honest failure states. No client is
/// wired here — [ServerSection] only talks to the probe seam the app root
/// supplies, mirroring onboarding's gate.
void main() {
  Widget pane({
    required ServerProfile profile,
    required ServerUrlProbe probeServer,
    required ValueChanged<ServerProfile> onServerChanged,
  }) =>
      MaterialApp(
        theme: buildVigilThemeData(Brightness.dark),
        home: Scaffold(
          body: SingleChildScrollView(
            child: ServerSection(
              profile: profile,
              probeServer: probeServer,
              onServerChanged: onServerChanged,
            ),
          ),
        ),
      );

  testWidgets('shows the connected server and opens an edit form',
      (tester) async {
    final changed = <ServerProfile>[];
    await tester.pumpWidget(pane(
      profile: const ServerProfile(baseUrl: 'https://soc.example.com'),
      probeServer: (url) async => {'version': '1'},
      onServerChanged: changed.add,
    ));

    expect(
      find.text('https://soc.example.com'),
      findsOneWidget,
      reason: 'the connected server is the first thing the section shows',
    );

    await tester.tap(find.byKey(const Key('server-edit')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('server-url-field')), findsOneWidget);
  });

  testWidgets('save probes the new URL and hands the profile up',
      (tester) async {
    final changed = <ServerProfile>[];
    final probed = <String>[];
    await tester.pumpWidget(pane(
      profile: const ServerProfile(baseUrl: 'https://soc.example.com'),
      probeServer: (url) async {
        probed.add(url);
        return {'version': '1'};
      },
      onServerChanged: changed.add,
    ));

    await tester.tap(find.byKey(const Key('server-edit')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('server-url-field')),
      'https://standby.example.com',
    );
    await tester.tap(find.byKey(const Key('server-save')));
    await tester.pumpAndSettle();

    expect(probed, ['https://standby.example.com'],
        reason: 'a server switch is gated on the probe passing');
    expect(changed.single.baseUrl, 'https://standby.example.com');
    expect(find.byKey(const Key('server-error')), findsNothing);
  });

  testWidgets('a failing probe keeps the old server and explains why',
      (tester) async {
    final changed = <ServerProfile>[];
    await tester.pumpWidget(pane(
      profile: const ServerProfile(baseUrl: 'https://soc.example.com'),
      probeServer: (url) async => throw const FormatException('unreachable'),
      onServerChanged: changed.add,
    ));

    await tester.tap(find.byKey(const Key('server-edit')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('server-url-field')),
      'https://dark.example.com',
    );
    await tester.tap(find.byKey(const Key('server-save')));
    await tester.pumpAndSettle();

    expect(changed, isEmpty,
        reason: 'no probe pass, no switch — the session belongs to the old server');
    expect(find.byKey(const Key('server-error')), findsOneWidget);
    expect(
      find.byKey(const Key('server-url-value')),
      findsNothing,
      reason: 'the form stays open for a retry — the failed URL is still in the field',
    );
  });

  testWidgets('test connection reports the server version on success',
      (tester) async {
    await tester.pumpWidget(pane(
      profile: const ServerProfile(baseUrl: 'https://soc.example.com'),
      probeServer: (url) async => {'version': '1'},
      onServerChanged: (_) {},
    ));

    await tester.tap(find.byKey(const Key('server-test')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('server-test-result')), findsOneWidget);
    expect(find.byKey(const Key('server-error')), findsNothing);
  });

  testWidgets('test connection surfaces the failure, not a fake success',
      (tester) async {
    await tester.pumpWidget(pane(
      profile: const ServerProfile(baseUrl: 'https://soc.example.com'),
      probeServer: (url) async => throw const FormatException('down'),
      onServerChanged: (_) {},
    ));

    await tester.tap(find.byKey(const Key('server-test')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('server-error')), findsOneWidget);
    expect(find.byKey(const Key('server-test-result')), findsNothing);
  });
}
