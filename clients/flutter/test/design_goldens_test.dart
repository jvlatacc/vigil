import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vigil_flutter/design/galleries.dart';
import 'package:vigil_flutter/main.dart';
import 'package:vigil_flutter/theme/vigil_colors.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

/// Golden captures of the design-system galleries — every color token in
/// both schemes, the whole 82-icon set, the full type ramp — plus the Home
/// empty state. Regenerate with:
///   flutter test --update-goldens test/design_goldens_test.dart
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    // The bundled static TTFs must actually load in the test environment;
    // without these loaders goldens silently fall back to the Ahem font.
    Future<void> load(String family, List<String> files) async {
      final loader = FontLoader(family);
      for (final file in files) {
        loader.addFont(rootBundle.load('assets/fonts/$file'));
      }
      await loader.load();
    }

    await load('Plus Jakarta Sans', [
      'plus-jakarta-sans-400.ttf',
      'plus-jakarta-sans-500.ttf',
      'plus-jakarta-sans-600.ttf',
      'plus-jakarta-sans-700.ttf',
    ]);
    await load('Roboto Mono', [
      'roboto-mono-400.ttf',
      'roboto-mono-500.ttf',
    ]);
  });

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

  /// Sizes BOTH the render surface (what the golden captures) and the view
  /// metrics (what MediaQuery reports) — setSurfaceSize alone leaves the
  /// view at the 800x600 test default, so adaptive shells never switch.
  Future<void> pumpApp(WidgetTester tester, Size size) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = size;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.binding.setSurfaceSize(size);
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const VigilApp());
    await tester.pumpAndSettle();
  }

  testWidgets('color swatches render every token, dark scheme', (tester) async {
    await tester.binding.setSurfaceSize(const Size(720, 760));
    await tester.pumpWidget(surface(const SwatchGallery(colors: VigilColors.dark)));
    await expectLater(
      find.byType(SwatchGallery),
      matchesGoldenFile('goldens/swatches-dark.png'),
    );
  });

  testWidgets('color swatches render every token, light scheme', (tester) async {
    await tester.binding.setSurfaceSize(const Size(720, 760));
    await tester.pumpWidget(
      surface(const SwatchGallery(colors: VigilColors.light), brightness: Brightness.light),
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
    await pumpApp(tester, const Size(390, 844));
    await expectLater(
      find.byType(NeedsYouHome),
      matchesGoldenFile('goldens/home-empty.png'),
    );
  });

  testWidgets('Home empty state, desktop form factor with the nav rail',
      (tester) async {
    await pumpApp(tester, const Size(1100, 844));
    await expectLater(
      find.byType(NeedsYouHome),
      matchesGoldenFile('goldens/home-empty-desktop.png'),
    );
  });
}
