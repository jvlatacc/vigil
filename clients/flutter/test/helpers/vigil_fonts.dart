import 'package:flutter/services.dart';

/// Loads the bundled Plus Jakarta Sans / Roboto Mono TTFs so widget tests
/// and goldens render real typography instead of the Ahem fallback.
Future<void> loadVigilFonts() async {
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
}
