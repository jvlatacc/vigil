import 'package:flutter/material.dart';

import '../approvals/approval_machine.dart';
import '../theme/extensions.dart';
import '../theme/vigil_typography.dart';

/// The stale-data banner (State model, "Stale / offline"): after two
/// consecutive poll failures the last good data stays visible with its
/// age — "Checked 4 min ago — reconnecting" — while backoff continues.
/// [now] is injectable for tests; it defaults to the real clock.
class StaleBanner extends StatelessWidget {
  const StaleBanner({super.key, required this.lastGoodAt, this.now});

  final DateTime? lastGoodAt;
  final DateTime Function()? now;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final label = dataAgeLabel(lastGoodAt, (now ?? DateTime.now)());
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: colors.bg2,
        borderRadius: BorderRadius.circular(context.vigilMetrics.radiusPanel),
        border: Border.all(color: colors.fair),
      ),
      child: Row(
        children: [
          Icon(Icons.wifi_off, size: 14, color: colors.fair),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              '$label — reconnecting',
              style: VigilTypography.meta.copyWith(color: colors.tx1),
            ),
          ),
        ],
      ),
    );
  }
}
