import 'package:flutter/material.dart';

import '../../theme/extensions.dart';
import '../../theme/vigil_colors.dart';
import '../../theme/vigil_typography.dart';

/// The console's `.sev` chip — a colored dot before a colored 12.5px label
/// (`styles.css` §.sev): critical → crit, high → high, medium → med,
/// low → ok(low), anything else → unrated (tx2 text, tx3 dot).
Color severityColor(String? severity, VigilColors colors) =>
    switch ((severity ?? '').trim().toLowerCase()) {
      'critical' || 'crit' => colors.sevCrit,
      'high' => colors.sevHigh,
      'medium' || 'med' => colors.sevMed,
      'low' => colors.sevLow,
      _ => colors.tx2,
    };

/// The dot color separately — unrated's dot is dimmer than its label.
Color severityDotColor(String? severity, VigilColors colors) =>
    switch ((severity ?? '').trim().toLowerCase()) {
      '' || 'unknown' || 'unrated' => colors.tx3,
      _ => severityColor(severity, colors),
    };

/// The chip's display label: Title Case for rated values, "Unrated"
/// otherwise — matching the console's severity column rendering.
String severityLabel(String? severity) {
  final s = (severity ?? '').trim();
  if (s.isEmpty || s.toLowerCase() == 'unknown') return 'Unrated';
  return s[0].toUpperCase() + s.substring(1).toLowerCase();
}

class SeverityChip extends StatelessWidget {
  const SeverityChip({super.key, required this.severity, this.dotOnly = false});

  /// The wire value — `critical`/`high`/`medium`/`low`, or anything the
  /// server sends when it rates nothing (rendered "unrated").
  final String? severity;

  /// Dot without the label (dense rows).
  final bool dotOnly;

  String get _label => severityLabel(severity);

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final color = severityColor(severity, colors);
    final dot = Container(
      width: 7,
      height: 7,
      decoration: BoxDecoration(
        color: severityDotColor(severity, colors),
        shape: BoxShape.circle,
      ),
    );
    if (dotOnly) return dot;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        dot,
        const SizedBox(width: 6),
        Text(
          _label,
          style: VigilTypography.label.copyWith(color: color, fontSize: 12.5),
        ),
      ],
    );
  }
}
