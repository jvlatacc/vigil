import 'package:flutter/material.dart';

import '../../theme/extensions.dart';
import '../../theme/vigil_typography.dart';

/// The console's state-pill tones (`shared/StatePill.tsx`, state-pill spec):
/// needs → poor, live → ac, closed → tx2 on bg3, idle → tx2/tx3.
enum PillTone { idle, live, needs, closed }

/// Colour pair and word for a case's combined state; any state shows
/// "Needs you" while a decision is pending. Mirrors the console's
/// `statePill(state, needs)` one to one.
({PillTone tone, String label}) casePillState(String? state, {bool needs = false}) {
  final s = (state ?? '').trim().toLowerCase();
  if (needs || s == 'waiting_approval') {
    return (tone: PillTone.needs, label: 'Needs you');
  }
  if (s == 'closed') return (tone: PillTone.closed, label: 'Closed');
  const live = {'assigned', 'executing', 'review_submitted'};
  final word = s.replaceAll('_', ' ');
  return (
    tone: live.contains(s) ? PillTone.live : PillTone.idle,
    label: word.isEmpty ? 'New' : word[0].toUpperCase() + word.substring(1),
  );
}

/// Height 22, padding 0 9, radius 999, 12/700, 7px dot before the text
/// (state-pill spec). The caller writes the reason after it.
class StatePill extends StatelessWidget {
  const StatePill({super.key, required this.state, this.needs = false});

  final String? state;
  final bool needs;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final (:tone, :label) = casePillState(state, needs: needs);
    final (dot, text, bg) = switch (tone) {
      PillTone.needs => (colors.poor, colors.poor, colors.poorBg),
      PillTone.live => (colors.ac, colors.ac, colors.acBg),
      PillTone.closed => (colors.tx2, colors.tx2, colors.bg3),
      PillTone.idle => (colors.tx3, colors.tx2, colors.bg3),
    };
    return Container(
      height: 22,
      padding: const EdgeInsets.symmetric(horizontal: 9),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 7,
            height: 7,
            decoration: BoxDecoration(color: dot, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: VigilTypography.label.copyWith(color: text, fontSize: 12),
          ),
        ],
      ),
    );
  }
}
