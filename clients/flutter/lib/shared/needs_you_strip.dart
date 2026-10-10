import 'package:flutter/material.dart';

import '../theme/extensions.dart';
import '../theme/vigil_typography.dart';

/// The console's needs-you-strip port (docs/design/console/components/
/// needs-you-strip.md): a compact "N need you" summary with a jump to the
/// Decisions queue. Poor tone — the strip exists to pull a person in.
class NeedsYouStrip extends StatelessWidget {
  const NeedsYouStrip({super.key, required this.count, this.onReview});

  /// How many items need a person right now.
  final int count;

  /// Jumps to the Decisions queue; null hides the affordance.
  final VoidCallback? onReview;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    return Container(
      key: const Key('needs-you-strip'),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: colors.poorBg,
        borderRadius: BorderRadius.circular(context.vigilMetrics.radiusPanel),
        border: Border.all(color: colors.poor.withValues(alpha: 0.5)),
      ),
      child: Row(
        children: [
          Icon(Icons.notifications_active,
              size: 14, color: colors.poor),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              count == 1 ? '1 need you' : '$count need you',
              style:
                  VigilTypography.label.copyWith(color: colors.tx0),
            ),
          ),
          if (onReview != null)
            TextButton(
              key: const Key('needs-you-review'),
              style: TextButton.styleFrom(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 0),
                minimumSize: const Size(0, 28),
              ),
              onPressed: onReview,
              child: const Text('Review', style: VigilTypography.label),
            ),
        ],
      ),
    );
  }
}
