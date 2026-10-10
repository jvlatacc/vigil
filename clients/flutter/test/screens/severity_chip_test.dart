import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vigil_flutter/screens/shared/severity_chip.dart';
import 'package:vigil_flutter/theme/vigil_colors.dart';
import 'package:vigil_flutter/theme/vigil_theme.dart';

/// The console's severity scale mapped into the design tokens —
/// `styles.css` §.sev: critical → crit, high → high, medium → med,
/// low → low, anything unrated → the muted pair. The table walks every
/// input the server sends (plus its sloppy variants) so a token reshuffle
/// cannot silently swap bands.
void main() {
  final darkTheme = buildVigilThemeData(Brightness.dark);

  test('mapping table — every wire value lands on its own band', () {
    final colors = darkTheme.extension<VigilColors>()!;
    final cases = <String, Color>{
      'critical': colors.sevCrit,
      'crit': colors.sevCrit, // backend shorthand
      'Critical': colors.sevCrit, // case-insensitive
      'CRITICAL': colors.sevCrit,
      'high': colors.sevHigh,
      'HIGH': colors.sevHigh,
      'medium': colors.sevMed,
      'med': colors.sevMed,
      'low': colors.sevLow,
      'LOW': colors.sevLow,
    };
    cases.forEach((severity, expected) {
      expect(severityColor(severity, colors), expected,
          reason: 'severity "$severity" must map to its band color');
      expect(severityDotColor(severity, colors), expected,
          reason: 'severity "$severity" dot must match its band color');
    });
  });

  test('unrated inputs render the muted pair, not a severity band', () {
    final colors = darkTheme.extension<VigilColors>()!;
    for (final unrated in <String?>[null, '', 'unknown', 'unrated', ' ']) {
      expect(severityColor(unrated, colors), colors.tx2,
          reason: 'unrated "$unrated" label color');
      expect(severityDotColor(unrated, colors), colors.tx3,
          reason: 'unrated "$unrated" dot is dimmer than its label');
    }
  });

  test('the four bands are distinct colors', () {
    final colors = darkTheme.extension<VigilColors>()!;
    final bands = {
      colors.sevCrit,
      colors.sevHigh,
      colors.sevMed,
      colors.sevLow,
    };
    expect(bands.length, 4, reason: 'collapsed bands would hide severity');
  });

  test('labels — Title Case for rated, Unrated for the rest', () {
    expect(severityLabel('critical'), 'Critical');
    expect(severityLabel('HIGH'), 'High');
    expect(severityLabel('med'), 'Med');
    expect(severityLabel('low'), 'Low');
    expect(severityLabel(null), 'Unrated');
    expect(severityLabel(''), 'Unrated');
    expect(severityLabel('unknown'), 'Unrated');
    expect(severityLabel(' unrated '), 'Unrated');
  });

  testWidgets('chip renders its dot before a colored label', (tester) async {
    final colors = darkTheme.extension<VigilColors>()!;
    await tester.pumpWidget(MaterialApp(
      theme: darkTheme,
      home: const Scaffold(
        body: Center(child: SeverityChip(severity: 'high')),
      ),
    ));

    final text = tester.widget<Text>(
      find.descendant(
        of: find.byType(SeverityChip),
        matching: find.byType(Text),
      ),
    );
    expect(text.data, 'High');
    expect(text.style?.color, colors.sevHigh);
  });

  testWidgets('dotOnly renders just the dot (dense rows)', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: darkTheme,
      home: const Scaffold(
        body: Center(child: SeverityChip(severity: 'low', dotOnly: true)),
      ),
    ));

    expect(
      find.descendant(
        of: find.byType(SeverityChip),
        matching: find.byType(Text),
      ),
      findsNothing,
    );
  });
}
