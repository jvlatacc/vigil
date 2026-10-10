import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/auth/session.dart';
import 'package:vigil_flutter/shell/screens.dart';
import 'package:vigil_flutter/shell/vigil_shell.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

import '../helpers/chat_stub.dart';

/// A user every gated destination is visible to.
const approver = UserProfile(
  username: 'jane',
  email: 'jane@corp.example',
  permissions: {
    'ai_decisions.approve': true,
    'cases.read': true,
    'settings.read': true,
  },
);

UserProfile userWith(Map<String, bool> permissions) => UserProfile(
      username: 'jane',
      email: 'jane@corp.example',
      permissions: permissions,
    );

/// Pumps the shell at an exact dp width — both the rendered surface and the
/// MediaQuery the shell adapts to. The shell is pumped directly: the app
/// root adds async boot (secure storage, /auth/me) that has no place in a
/// form-factor test.
Future<void> pumpShell(
  WidgetTester tester,
  Size size, {
  required VigilShell shell,
}) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = size;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.binding.setSurfaceSize(size);
  addTearDown(() => tester.binding.setSurfaceSize(null));
  // The app's real host environment: MaterialApp supplies the Vigil theme
  // and MaterialLocalizations (NavigationRail reads them); Scaffold
  // supplies the Material surface.
  await tester.pumpWidget(MaterialApp(
    theme: buildVigilThemeData(Brightness.dark),
    home: Scaffold(body: shell),
  ));
  await tester.pumpAndSettle();
}

VigilShell shell({
  UserProfile user = approver,
  VigilScreen initial = VigilScreen.home,
  VoidCallback? onSignOut,
}) =>
    VigilShell(
      user: user,
      chatSession: stubChatSession(),
      initialScreen: initial,
      onSignOut: onSignOut ?? () {},
    );

bool hasNavigationBar(WidgetTester tester) =>
    tester.widgetList(find.byType(NavigationBar)).isNotEmpty;

bool hasNavigationRail(WidgetTester tester) =>
    tester.widgetList(find.byType(NavigationRail)).isNotEmpty;

void main() {
  group('adaptive shell form factors', () {
    testWidgets('400 dp phone renders bottom navigation, no rail',
        (tester) async {
      await pumpShell(tester, const Size(400, 800), shell: shell());

      expect(hasNavigationBar(tester), isTrue,
          reason: 'at or below 600 dp the console-style bar shows');
      expect(hasNavigationRail(tester), isFalse);
      // All five destinations visible for a full-permission user.
      expect(find.text('Home'), findsOneWidget);
      expect(find.text('AI Decisions'), findsOneWidget);
      expect(find.text('Cases'), findsOneWidget);
      expect(find.text('Ask Vigil'), findsOneWidget);
      expect(find.text('Settings'), findsOneWidget);
    });

    testWidgets('700 dp renders the navigation rail, no bottom bar',
        (tester) async {
      await pumpShell(tester, const Size(700, 900), shell: shell());

      expect(hasNavigationRail(tester), isTrue,
          reason: 'above 600 dp the rail replaces the bar');
      expect(hasNavigationBar(tester), isFalse);
    });

    testWidgets('1280 dp desktop renders the navigation rail', (tester) async {
      await pumpShell(tester, const Size(1280, 800), shell: shell());

      expect(hasNavigationRail(tester), isTrue);
      expect(hasNavigationBar(tester), isFalse);
    });

    testWidgets('rail tap switches the destination pane', (tester) async {
      await pumpShell(tester, const Size(700, 900), shell: shell());

      await tester.tap(find.text('Cases'));
      await tester.pumpAndSettle();

      expect(
        find.descendant(
          of: find.byType(AppBar),
          matching: find.text('Cases'),
        ),
        findsOneWidget,
      );
    });

    testWidgets('bar tap switches the destination pane', (tester) async {
      await pumpShell(tester, const Size(400, 800), shell: shell());

      await tester.tap(find.byKey(const Key('nav-decisions')));
      await tester.pumpAndSettle();

      expect(
        find.descendant(
          of: find.byType(AppBar),
          matching: find.text('AI Decisions'),
        ),
        findsOneWidget,
      );
    });

    testWidgets('Home is titled with the console vocabulary', (tester) async {
      await pumpShell(tester, const Size(700, 900), shell: shell());

      expect(
        find.descendant(
          of: find.byType(AppBar),
          matching: find.text('What needs a person'),
        ),
        findsOneWidget,
      );
    });
  });

  group('shell chrome', () {
    testWidgets('account menu signs out and names the user', (tester) async {
      var signOuts = 0;
      await pumpShell(
        tester,
        const Size(700, 900),
        shell: shell(onSignOut: () => signOuts++),
      );

      await tester.tap(find.byKey(const Key('account-menu')));
      await tester.pumpAndSettle();
      expect(find.text('jane'), findsOneWidget);
      expect(find.text('jane@corp.example'), findsOneWidget);

      await tester.tap(find.byKey(const Key('sign-out-item')));
      await tester.pumpAndSettle();

      expect(signOuts, 1);
    });
  });

  group('ask vigil placement', () {
    testWidgets('rail opens and closes the docked pane', (tester) async {
      await pumpShell(tester, const Size(1280, 800), shell: shell());

      await tester.tap(find.text('Ask Vigil'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('ask-dock-close')), findsOneWidget,
          reason: 'wide layouts dock the pane beside the content');

      await tester.tap(find.byKey(const Key('ask-dock-close')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('ask-dock-close')), findsNothing);
    });

    testWidgets('phone opens the ask surface as a modal sheet', (tester) async {
      await pumpShell(tester, const Size(400, 800), shell: shell());

      await tester.tap(find.text('Ask Vigil'));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ask-composer')), findsOneWidget);
      expect(find.byKey(const Key('ask-dock-close')), findsNothing,
          reason: 'phones present the pane as a sheet, not a dock');
    });
  });
}
