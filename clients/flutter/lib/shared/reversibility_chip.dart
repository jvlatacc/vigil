import 'package:flutter/material.dart';

import '../theme/extensions.dart';
import '../theme/vigil_typography.dart';

/// Tone pill for an action's reversibility — reversible actions carry the
/// accent tone, irreversible ones the poor tone (trust language).
class ReversibilityChip extends StatelessWidget {
  const ReversibilityChip({super.key, required this.reversibility});

  /// `reversible` | `irreversible` (the frozen contract's vocabulary).
  final String? reversibility;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final irreversible = reversibility == 'irreversible';
    final fg = irreversible ? colors.poor : colors.ac;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: irreversible ? colors.poorBg : colors.acBg,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: fg.withValues(alpha: 0.4)),
      ),
      child: Text(
        reversibility ?? 'unknown',
        style: VigilTypography.label.copyWith(
          fontSize: 11,
          color: fg,
        ),
      ),
    );
  }
}
