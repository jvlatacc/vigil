import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:vigil_flutter/theme/vigil_icon.dart';
import 'package:vigil_flutter/theme/vigil_icons.dart';

/// The generated VigilIcons class is verified against the manifest it was
/// generated from: same count, same names, same path data, and every path
/// must parse through the SVG path parser the painter uses.
void main() {
  late Map<String, dynamic> manifest;

  setUpAll(() {
    manifest = jsonDecode(
      File('../../docs/design/console/assets/icons/icons.json')
          .readAsStringSync(),
    ) as Map<String, dynamic>;
  });

  test('icon count matches the manifest (82-icon line set)', () {
    expect(manifest.length, 82,
        reason: 'manifest size changed? re-audit the set');
    expect(VigilIcons.all.length, manifest.length,
        reason: 'VigilIcons drifted from icons.json');
    expect(VigilIcons.byName.length, manifest.length);
  });

  test('every manifest icon exists with identical path data', () {
    for (final entry in manifest.entries) {
      final icon = VigilIcons.byName[entry.key];
      expect(icon, isNotNull, reason: 'missing icon: ${entry.key}');
      expect(icon!.path.trim(), entry.value,
          reason: 'path drift: ${entry.key}');
      expect(icon.name, entry.key);
    }
  });

  test('no extra icons outside the manifest', () {
    final manifestNames = manifest.keys.toSet();
    final portedNames = VigilIcons.byName.keys.toSet();
    expect(portedNames.difference(manifestNames), isEmpty,
        reason: 'icons in VigilIcons but not in icons.json');
  });

  test('every icon path parses through the SVG path parser', () {
    for (final icon in VigilIcons.all) {
      final path = vigilIconPath(icon.path);
      // Dot icons like "more" (three h0.1 segments) are legitimately
      // degenerate for bounds — the round-cap stroke renders them. Assert
      // drawable extent, not bounds.
      final metrics = path.computeMetrics().toList();
      expect(metrics, isNotEmpty,
          reason: 'icon ${icon.name} parsed to an empty path');
      expect(
        metrics.any((m) => m.length > 0),
        isTrue,
        reason: 'icon ${icon.name} has no drawable extent',
      );
    }
  });
}
