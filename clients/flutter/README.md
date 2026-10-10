# Vigil — Flutter client

First-party Vigil client for iOS, Android, macOS, Windows, and Linux, built from
one Dart codebase. Package `vigil_flutter`, display name **Vigil**, bundle family
`ai.deeptempo.vigil.*`. A native SwiftUI watchOS companion is embedded in the iOS
target by a later workstream; this package owns the Flutter app itself.

No Flutter-web target: the React console (`clients/web/`) keeps the browser.

## Design system — ported, not reinterpreted

The canonical tokens live outside this package in `docs/design/console/`:

- `tokens/tokens.json` — colors (dark/light), type scale, radius, control sizes
- `assets/icons/icons.json` — the 82-icon line set (24 viewBox, 1.8 stroke)

`tool/codegen.py` reads both and generates, into `lib/theme/`:

- `vigil_colors.dart` — `VigilColors` `ThemeExtension` (every color token, both
  schemes, exact hex/rgba values: Good/Fair/Poor levels, severity scale,
  DeepTempo brand tokens)
- `vigil_theme.dart` — `VigilTheme` `ThemeExtension` (radius/control/space) plus
  the `ThemeData` builders that wire fonts and color roles
- `vigil_typography.dart` — the token type ramp as `TextStyle`s
- `vigil_icons.dart` — typed `VigilIcons` class; one `VigilIconData` per manifest
  entry, rendered by `VigilIcon` (CustomPaint stroke painter)

Regenerate after editing the token sources:

```bash
python3 tool/codegen.py   # from clients/flutter/
```

Generated files are committed; `test/design_tokens_test.dart` re-parses the
token sources and fails on any drift between them and the generated Dart, so
regenerating is always safe and never silent.

### Fonts

The console self-hosts Plus Jakarta Sans and Roboto Mono as woff2, which Flutter
cannot use. This package bundles the same two families as static TTFs
(`assets/fonts/`, latin subset, sourced from the Fontsource builds of the
Google Fonts releases): Plus Jakarta Sans 400/500/600/700 and Roboto Mono
400/500. The token scale's `650` weight maps to `w700`, matching how browsers
with static fonts resolve 650.

## Development gates

```bash
flutter pub get
flutter analyze
flutter test                     # unit + golden tests
flutter build apk --debug        # Android
flutter build linux              # Linux
```

iOS, macOS, and Windows archives require macOS/Windows runners and are verified
by the build-matrix workstream; the watchOS target is added to the iOS build
when the companion lands.
