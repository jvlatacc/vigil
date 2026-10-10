import 'package:flutter/material.dart';

import '../theme/extensions.dart';
import '../theme/vigil_icon.dart';
import '../theme/vigil_icons.dart';
import '../theme/vigil_typography.dart';

/// The Apple Watch section of Settings — the entry point for pairing the
/// watchOS companion. The companion approves from the wrist against its own
/// token pair, handed over from this phone at pairing time over
/// WatchConnectivity (the watch never sees the password and never shares the
/// phone's live tokens).
///
/// The handoff implementation lands with the watch companion task; until
/// then [onPairWatch] is null and the section says so plainly rather than
/// pretending a pairing flow exists.
class WatchPairingCard extends StatelessWidget {
  const WatchPairingCard({super.key, this.onPairWatch});

  /// Invoked when the user asks to pair. Null while the watch companion's
  /// token-handoff is not merged — the entry renders its honest
  /// not-yet-available state.
  final VoidCallback? onPairWatch;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final available = onPairWatch != null;
    return Card(
      key: const Key('watch-card'),
      color: colors.bg1,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(context.vigilMetrics.radiusCard),
        side: BorderSide(color: colors.ln0),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                VigilIcon(VigilIcons.clock, size: 18, color: colors.tx1),
                const SizedBox(width: 8),
                Text(
                  'Apple Watch',
                  style:
                      VigilTypography.sectionTitle.copyWith(color: colors.tx0),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              'Approve or reject from the wrist. The watch signs in with its '
              'own session, handed over from this device — approvals still '
              'land when the phone is out of reach.',
              style: VigilTypography.meta.copyWith(color: colors.tx2),
            ),
            const SizedBox(height: 12),
            if (available)
              FilledButton(
                key: const Key('watch-pair'),
                onPressed: onPairWatch,
                child: const Text('Pair Apple Watch'),
              )
            else
              Text(
                'Pairing arrives with the watch companion. This entry stays '
                'so the handoff has a home.',
                style: VigilTypography.meta.copyWith(color: colors.tx3),
              ),
          ],
        ),
      ),
    );
  }
}
