import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vigil_flutter/api/vigil_client.dart';
import 'package:vigil_flutter/auth/session.dart';
import 'package:vigil_flutter/auth/token_store.dart';
import 'package:vigil_flutter/design/galleries.dart';
import 'package:vigil_flutter/shell/screens.dart';
import 'package:vigil_flutter/shell/vigil_shell.dart';
import 'package:vigil_flutter/theme/vigil_colors.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

import 'helpers/vigil_fonts.dart';

/// Golden captures of the design-system galleries — every color token in
/// both schemes, the whole 82-icon set, the full type ramp — plus the shell
/// chrome with the Home empty state. Regenerate with:
///   flutter test --update-goldens test/design_goldens_test.dart
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(loadVigilFonts);

  Widget surface(Widget child, {Brightness brightness = Brightness.dark}) {
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Theme(
        data: buildVigilThemeData(brightness),
        child: Scaffold(
          body: Padding(padding: const EdgeInsets.all(12), child: child),
        ),
      ),
    );
  }

  /// A user the shell renders with — every gated screen visible, so the
  /// chrome goldens show the full destination set.
  const approver = UserProfile(
    username: 'jane',
    email: 'jane@corp.example',
    permissions: {
      'ai_decisions.approve': true,
      'cases.read': true,
      'settings.read': true,
    },
  );

  /// Sizes BOTH the render surface (what the golden captures) and the view
  /// metrics (what MediaQuery reports) — setSurfaceSize alone leaves the
  /// view at the 800x600 test default, so adaptive shells never switch.
  /// The shell is pumped directly: the app root adds async boot (secure
  /// storage, /auth/me) that has no place in a design golden.
  Future<void> pumpShell(
    WidgetTester tester,
    Size size, {
    Brightness brightness = Brightness.dark,
  }) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = size;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.binding.setSurfaceSize(size);
    addTearDown(() => tester.binding.setSurfaceSize(null));
    // MaterialApp supplies MaterialLocalizations and the default text
    // environment the shell's material widgets read.
    await tester.pumpWidget(
      MaterialApp(
        theme: buildVigilThemeData(brightness),
        home: Scaffold(
          body: VigilShell(
            user: approver,
            client: VigilClient(
              // The shell's Home pane never polls; the URL is inert.
              baseUrl: 'http://localhost:6987',
              tokenStore: InMemoryTokenStore(),
              userAgent: 'VigilTest/1.0',
            ),
            initialScreen: VigilScreen.home,
            onSignOut: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('color swatches render every token, dark scheme', (tester) async {
    await tester.binding.setSurfaceSize(const Size(720, 760));
    await tester
        .pumpWidget(surface(const SwatchGallery(colors: VigilColors.dark)));
    await expectLater(
      find.byType(SwatchGallery),
      matchesGoldenFile('goldens/swatches-dark.png'),
    );
  });

  testWidgets('color swatches render every token, light scheme',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(720, 760));
    await tester.pumpWidget(
      surface(const SwatchGallery(colors: VigilColors.light),
          brightness: Brightness.light),
    );
    await expectLater(
      find.byType(SwatchGallery),
      matchesGoldenFile('goldens/swatches-light.png'),
    );
  });

  testWidgets('the 82-icon line set renders', (tester) async {
    await tester.binding.setSurfaceSize(const Size(720, 720));
    await tester.pumpWidget(surface(const IconGallery()));
    await expectLater(
      find.byType(IconGallery),
      matchesGoldenFile('goldens/icons.png'),
    );
  });

  testWidgets('the token type ramp renders', (tester) async {
    await tester.binding.setSurfaceSize(const Size(480, 560));
    await tester.pumpWidget(surface(
      const TypeRampGallery(),
      brightness: Brightness.light,
    ));
    await expectLater(
      find.byType(TypeRampGallery),
      matchesGoldenFile('goldens/type-ramp.png'),
    );
  });

  testWidgets('Home empty state with the shell chrome', (tester) async {
    await pumpShell(tester, const Size(390, 844));
    await expectLater(
      find.byType(VigilShell),
      matchesGoldenFile('goldens/home-empty.png'),
    );
  });

  testWidgets('Home empty state, desktop form factor with the nav rail',
      (tester) async {
    await pumpShell(tester, const Size(1100, 844));
    await expectLater(
      find.byType(VigilShell),
      matchesGoldenFile('goldens/home-empty-desktop.png'),
    );
  });
}
