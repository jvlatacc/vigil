import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:vigil_flutter/app.dart';
import 'package:vigil_flutter/auth/token_store.dart';
import 'package:vigil_flutter/onboarding/server_profile.dart';

/// A REAL Linux desktop capture of the Ask Vigil streaming state, driven
/// against a local mock Vigil server (tools/mock server started separately
/// on 127.0.0.1:6931). Native windows are not browser-drivable, so this
/// driver + an X11 root-window grab is how the desktop screenshot is taken.
///
///   xvfb-run -a -s "-screen 0 1440x900x24" \
///     flutter test -d linux integration_test/ask_streaming_desktop_test.dart
Future<void> _waitFor(
  WidgetTester tester,
  Finder finder, {
  int seconds = 20,
}) async {
  for (var i = 0; i < seconds * 10; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    if (finder.evaluate().isNotEmpty) return;
  }
  fail('never found ${finder}');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'Ask Vigil streams an answer in the docked pane',
    (tester) async {
      await tester.pumpWidget(VigilApp(
        profileStore: InMemoryServerProfileStore(
          profile: const ServerProfile(baseUrl: 'http://127.0.0.1:6931'),
        ),
        tokenStore: InMemoryTokenStore()
          ..save(accessToken: 'qa-access', refreshToken: 'qa-refresh'),
      ));

      // Boot: /auth/me over the mock, then the shell with the rail.
      await _waitFor(tester, find.text('Ask Vigil'));

      // The dock opens beside the current pane on wide layouts.
      await tester.tap(find.text('Ask Vigil').first);
      await _waitFor(tester, find.byKey(const Key('ask-send')));

      await tester.enterText(find.byType(TextField).last,
          'what does isolating web-prod-3 touch?');
      await tester.pump(const Duration(milliseconds: 100));
      await tester.tap(find.byKey(const Key('ask-send')));

      // The mock streams frames over ~3 s, then holds — capture mid-stream.
      await tester.pump(const Duration(seconds: 5));

      final capture = Process.run(
        'import',
        ['-window', 'root',
         '/home/user/work/evidence/ask-vigil-streaming-desktop.png'],
      );
      final result = await capture.timeout(const Duration(seconds: 30));
      if (result.exitCode != 0) {
        fail('screenshot failed: ${result.stderr}');
      }
    },
    timeout: const Timeout(Duration(minutes: 10)),
  );
}
