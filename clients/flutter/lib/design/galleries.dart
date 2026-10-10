import 'package:flutter/material.dart';

import '../theme/extensions.dart';
import '../theme/vigil_colors.dart';
import '../theme/vigil_icon.dart';
import '../theme/vigil_icons.dart';
import '../theme/vigil_typography.dart';

/// Full-catalog galleries for the design system: every color token, every
/// icon, the whole type ramp — one scheme per gallery. The goldens wrap
/// these directly, so a token or icon missing from the port shows up as a
/// missing tile in a test failure, not just in review.

class SwatchGallery extends StatelessWidget {
  const SwatchGallery({super.key, required this.colors});

  final VigilColors colors;

  @override
  Widget build(BuildContext context) {
    final metrics = context.vigilMetrics;
    return Wrap(
      spacing: metrics.space[2],
      runSpacing: metrics.space[2],
      children: [
        for (final name in VigilColors.tokenNames)
          SizedBox(
            width: 164,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  height: 44,
                  decoration: BoxDecoration(
                    color: colors.byName(name),
                    borderRadius:
                        BorderRadius.circular(metrics.radiusCardInner),
                    border: Border.all(color: colors.ln1),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  name,
                  overflow: TextOverflow.ellipsis,
                  style: VigilTypography.micro.copyWith(color: colors.tx2),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class IconGallery extends StatelessWidget {
  const IconGallery({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final metrics = context.vigilMetrics;
    return Wrap(
      spacing: metrics.space[2],
      runSpacing: metrics.space[2],
      children: [
        for (final icon in VigilIcons.all)
          SizedBox(
            width: 84,
            child: Column(
              children: [
                VigilIcon(icon, color: colors.tx0),
                const SizedBox(height: 4),
                Text(
                  icon.name,
                  overflow: TextOverflow.ellipsis,
                  style: VigilTypography.micro.copyWith(color: colors.tx2),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class TypeRampGallery extends StatelessWidget {
  const TypeRampGallery({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final entry in VigilTypography.byName.entries) ...[
          const SizedBox(height: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Isolate host web-prod-3 · 0.88 reversible',
                style: entry.value.copyWith(color: colors.tx0),
              ),
              Text(
                '${entry.key} · ${entry.value.fontSize}',
                style: VigilTypography.micro.copyWith(color: colors.tx2),
              ),
            ],
          ),
        ],
      ],
    );
  }
}
