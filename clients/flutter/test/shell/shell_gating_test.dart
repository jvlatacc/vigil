import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/shell/screens.dart';
import 'package:vigil_flutter/shell/vigil_shell.dart';

import 'adaptive_shell_test.dart';

/// The console's SCREEN_PERMS contract, asserted one entry at a time:
/// every gated screen is invisible in navigation without its permission
/// key, appears with it, and a deep link lands on the explanatory denial
/// screen instead of the screen — the console hides gates, it does not
/// disable them (SocConsole.tsx SCREEN_PERMS).
void main() {
  group('gating table — every SCREEN_PERMS entry', () {
    testWidgets('cases.read gates Cases', (tester) async {
      await pumpShell(
        tester,
        const Size(700, 900),
        shell: shell(user: userWith({})),
      );
      expect(find.text('Cases'), findsNothing,
          reason: 'gated screens are hidden from navigation, not disabled');

      await pumpShell(
        tester,
        const Size(700, 900),
        shell: shell(user: userWith({'cases.read': true})),
      );
      expect(find.text('Cases'), findsOneWidget);
    });

    testWidgets('ai_decisions.approve gates AI Decisions', (tester) async {
      await pumpShell(
        tester,
        const Size(700, 900),
        shell: shell(user: userWith({})),
      );
      expect(find.text('AI Decisions'), findsNothing);

      await pumpShell(
        tester,
        const Size(700, 900),
        shell: shell(user: userWith({'ai_decisions.approve': true})),
      );
      expect(find.text('AI Decisions'), findsOneWidget);
    });

    testWidgets('ai_decisions.approve gates Home (the landing screen)',
        (tester) async {
      await pumpShell(
        tester,
        const Size(700, 900),
        shell: shell(user: userWith({})),
      );
      expect(find.text('Home'), findsNothing);

      await pumpShell(
        tester,
        const Size(700, 900),
        shell: shell(user: userWith({'ai_decisions.approve': true})),
      );
      expect(find.text('Home'), findsOneWidget);
    });

    testWidgets('settings.read gates Settings', (tester) async {
      await pumpShell(
        tester,
        const Size(700, 900),
        shell: shell(user: userWith({})),
      );
      expect(find.text('Settings'), findsNothing);

      await pumpShell(
        tester,
        const Size(700, 900),
        shell: shell(user: userWith({'settings.read': true})),
      );
      expect(find.text('Settings'), findsOneWidget);
    });

    testWidgets('Ask Vigil is ungated — visible without any permission',
        (tester) async {
      await pumpShell(
        tester,
        const Size(700, 900),
        shell: shell(user: userWith({})),
      );
      // At least one: the nav destination label and the open pane's app
      // bar can both read "Ask Vigil".
      expect(
        find.text('Ask Vigil'),
        findsWidgets,
        reason: 'ungated screens stay in navigation for everyone',
      );
    });

    testWidgets('unit table: canSeeScreen matches SCREEN_PERMS exactly',
        (tester) async {
      // Walk every entry of the ported map — a new console gate that is
      // added to screenPerms without a matching expectation fails here.
      expect(
          screenPerms.keys.toSet(),
          {
            VigilScreen.home,
            VigilScreen.decisions,
            VigilScreen.cases,
            VigilScreen.settings,
          },
          reason: 'the console gates exactly these four; ask stays ungated');

      for (final entry in screenPerms.entries) {
        final screen = entry.key;
        final perm = entry.value;
        expect(canSeeScreen(screen, {}), isFalse,
            reason: '$screen without $perm is hidden');
        expect(canSeeScreen(screen, {perm: true}), isTrue,
            reason: '$screen with $perm is visible');
        expect(canSeeScreen(screen, {perm: false}), isFalse,
            reason: 'an explicit false is as good as absent');
      }
      expect(canSeeScreen(VigilScreen.ask, {}), isTrue,
          reason: 'ungated screens stay visible for everyone');
    });

    // The deep-link denial is enforced at the app root (it resolves the
    // route before choosing shell vs denial) — every gated screen's
    // deep-link walk lives in ../app_root_test.dart, "every gated deep
    // link lands on the denial screen".

    testWidgets('ungated deep-link renders the screen', (tester) async {
      await pumpShell(
        tester,
        const Size(700, 900),
        shell: shell(user: userWith({}), initial: VigilScreen.ask),
      );

      expect(find.byType(PermissionDeniedScreen), findsNothing);
      expect(
        find.descendant(
          of: find.byType(AppBar),
          matching: find.text('Ask Vigil'),
        ),
        findsOneWidget,
      );
    });
  });
}
