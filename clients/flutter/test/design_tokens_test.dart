import 'dart:convert';
import 'dart:io';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vigil_flutter/theme/vigil_colors.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';
import 'package:vigil_flutter/theme/vigil_typography.dart';

/// Re-parses the canonical token sources and holds them beside the ported
/// values, so every parity check fails with a readable diff, and any drift
/// in tokens.json / tokens.css vs the generated Dart is caught in CI.
class TokenSources {
  TokenSources._(this.json_, this.css)
      : darkBlock = RegExp(r'\.vg-dark\s*\{([^}]*)\}').firstMatch(css)?.group(1) ?? '',
        lightBlock = RegExp(r'\.vg-light\s*\{([^}]*)\}').firstMatch(css)?.group(1) ?? '',
        rootBlock = RegExp(r':root\s*\{([^}]*)\}').firstMatch(css)?.group(1) ?? '';

  final Map<String, dynamic> json_;
  final String css;
  final String darkBlock;
  final String lightBlock;
  final String rootBlock;

  static TokenSources load() {
    final tokens = jsonDecode(
      File('../../docs/design/console/tokens/tokens.json').readAsStringSync(),
    ) as Map<String, dynamic>;
    final css = File('../../docs/design/console/tokens/tokens.css').readAsStringSync();
    return TokenSources._(tokens, css);
  }

  Map<String, dynamic> get colors => json_['color']! as Map<String, dynamic>;
  Map<String, dynamic> get radius => json_['radius']! as Map<String, dynamic>;
  Map<String, dynamic> get control => json_['control']! as Map<String, dynamic>;
  List<dynamic> get space => json_['space']! as List<dynamic>;
  Map<String, dynamic> get type => json_['type']! as Map<String, dynamic>;
  Map<String, dynamic> get scale => type['scale']! as Map<String, dynamic>;
}

Color parseColor(String value) {
  final v = value.trim();
  if (v.startsWith('#')) {
    final hex = v.substring(1);
    if (hex.length == 6) return Color(int.parse('FF$hex', radix: 16));
    return Color(int.parse(hex, radix: 16));
  }
  final m = RegExp(r'rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9.]+)\s*\)')
      .firstMatch(v)!;
  return Color.fromRGBO(
    int.parse(m.group(1)!),
    int.parse(m.group(2)!),
    int.parse(m.group(3)!),
    double.parse(m.group(4)!),
  );
}

double parsePx(Object value) =>
    double.parse(value.toString().replaceAll(RegExp(r'px$'), ''));

late TokenSources sources;

void main() {
  setUpAll(() {
    sources = TokenSources.load();
  });

  test('every tokens.json color token exists in VigilColors in both schemes', () {
    for (final entry in sources.colors.entries) {
      final name = entry.key;
      final spec = entry.value as Map<String, dynamic>;
      for (final which in ['dark', 'light']) {
        expect(
          VigilColors.tokenNames.contains(name),
          isTrue,
          reason: 'token $name missing from VigilColors',
        );
        final expected = parseColor(spec[which] as String);
        final actual = which == 'dark'
            ? VigilColors.dark.byName(name)
            : VigilColors.light.byName(name);
        expect(actual, expected,
            reason: '$name.$which drifted: ported $actual vs canonical $expected');
      }
    }
  });

  test('tokens.json and tokens.css agree on every color token (sources cross-check)',
      () {
    // Compare each declaration inside the scheme's own block — both theme
    // blocks define --bg0, so a document-wide regex matches the wrong one.
    for (final entry in sources.colors.entries) {
      final name = entry.key;
      final spec = entry.value as Map<String, dynamic>;
      for (final which in ['dark', 'light']) {
        final expected = parseColor(spec[which] as String);
        final themeBlock = which == 'dark' ? sources.darkBlock : sources.lightBlock;
        final decl = RegExp('--${RegExp.escape(name)}\\s*:\\s*([^;]+);');
        final matches = decl.allMatches(themeBlock).toList();
        if (matches.isEmpty && themeBlock.isEmpty) {
          matches.addAll(decl.allMatches(sources.rootBlock));
        }
        // The CSS value may reference a shared var or carry the literal;
        // when it is a literal, it must equal tokens.json.
        for (final m in matches) {
          final cssValue = m.group(1)!.trim();
          if (cssValue.startsWith('#') || cssValue.startsWith('rgba(')) {
            expect(parseColor(cssValue), expected,
                reason: 'tokens.css --$name ($cssValue) != tokens.json');
          }
        }
      }
    }
  });

  test('level, severity, and DeepTempo brand tokens keep their canonical values',
      () {
    // Spot anchors straight from tokens.json — full coverage is the loop above.
    final colors = sources.colors;
    Color dark(String n) => VigilColors.dark.byName(n);
    Color light(String n) => VigilColors.light.byName(n);
    expect(dark('good'), parseColor((colors['good'] as Map)['dark'] as String));
    expect(dark('fair'), parseColor((colors['fair'] as Map)['dark'] as String));
    expect(dark('poor'), parseColor((colors['poor'] as Map)['dark'] as String));
    expect(dark('sev-crit'), parseColor((colors['sev-crit'] as Map)['dark'] as String));
    expect(dark('sev-high'), parseColor((colors['sev-high'] as Map)['dark'] as String));
    expect(dark('sev-med'), parseColor((colors['sev-med'] as Map)['dark'] as String));
    expect(dark('sev-low'), parseColor((colors['sev-low'] as Map)['dark'] as String));
    expect(dark('dt-red'), parseColor((colors['dt-red'] as Map)['dark'] as String));
    expect(light('dt-red'), parseColor((colors['dt-red'] as Map)['light'] as String));
    expect(dark('ac'), const Color(0xFF3AA8FF));
    expect(light('ac'), const Color(0xFF0A6FD6));
  });

  test('radius, control, and space metrics match tokens.json', () {
    for (final entry in sources.radius.entries) {
      expect(
        VigilTheme.radiusTokens[entry.key],
        parsePx(entry.value),
        reason: 'radius ${entry.key} drifted',
      );
    }
    for (final entry in sources.control.entries) {
      expect(
        VigilTheme.controlTokens[entry.key],
        parsePx(entry.value),
        reason: 'control ${entry.key} drifted',
      );
    }
    final portedSpace = VigilTheme.metrics.space;
    expect(portedSpace.length, sources.space.length, reason: 'space ramp size');
    for (var i = 0; i < portedSpace.length; i++) {
      expect(portedSpace[i], parsePx(sources.space[i]), reason: 'space[$i]');
    }
  });

  test('type ramp matches tokens.json sizes and (hundred-rounded) weights', () {
    for (final entry in sources.scale.entries) {
      final name = entry.key;
      final spec = (entry.value as String)
          .replaceAll('/', ' ')
          .split(RegExp(r'\s+'))
        ..removeWhere((t) => t.isEmpty);
      final expectedSize = parsePx(spec.first);
      int? expectedWeight;
      for (final tok in spec.skip(1)) {
        if (RegExp(r'^\d+$').hasMatch(tok)) expectedWeight = int.parse(tok);
      }
      final style = VigilTypography.byName[name];
      expect(style, isNotNull, reason: 'type style $name missing from VigilTypography');
      expect(style!.fontSize, expectedSize, reason: 'size of $name');
      if (expectedWeight != null) {
        // tokens.json carries variable-font weights (650); static TTFs ship
        // hundreds and CSS matching rounds 650 up to 700.
        final rounded = expectedWeight % 100 != 0 ? 700 : expectedWeight;
        final expectedFontWeight = FontWeight.values[(rounded ~/ 100) - 1];
        expect(style.fontWeight, expectedFontWeight,
            reason: 'weight of $name (token $expectedWeight, static rounding $rounded)');
      }
    }
  });
}
