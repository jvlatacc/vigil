import 'package:flutter/material.dart';

import '../approvals/approval_machine.dart';
import '../approvals/approvals_controller.dart';
import '../theme/extensions.dart';
import '../theme/vigil_typography.dart';

/// The undo-fuse toast host (docs/design/console/components/undo-fuse.md):
/// one card per decision mid-fuse — "{Approving|Rejecting}: {title}" with
/// an outlined Undo button whose 2px accent bar shrinks over the fuse's
/// remaining time; the decision is final when the bar is gone. Undo inside
/// the fuse cancels outright; there is no undo after it.
class FusedDecisionToast extends StatelessWidget {
  const FusedDecisionToast({super.key, required this.controller});

  final ApprovalsController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final fuses = controller.fuses.values.toList();
        if (fuses.isEmpty) return const SizedBox.shrink();
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final fuse in fuses)
              _FuseCard(
                key: ValueKey('fuse-${fuse.actionId}'),
                fuse: fuse,
                remainingAtMount: fuse.remainingAt(controller.now()),
                onUndo: () => controller.undo(fuse.actionId),
              ),
          ],
        );
      },
    );
  }
}

class _FuseCard extends StatelessWidget {
  const _FuseCard({
    super.key,
    required this.fuse,
    required this.remainingAtMount,
    required this.onUndo,
  });

  final ApprovalFuse fuse;

  /// Fuse time left when the card mounted — drives the shrinking bar (the
  /// controller's Timer owns the actual commit).
  final Duration remainingAtMount;
  final VoidCallback onUndo;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: colors.bg1,
        borderRadius: BorderRadius.circular(context.vigilMetrics.radiusPanel),
        border: Border.all(color: colors.ln1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${fuse.verb.presentTense}: ${fuse.title}',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: VigilTypography.body.copyWith(color: colors.tx0),
                ),
              ),
              const SizedBox(width: 12),
              _UndoFuseButton(
                remaining: remainingAtMount,
                onPressed: onUndo,
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            fuse.verb == FuseVerb.reject
                ? 'Rejecting with reason · nothing sent yet'
                : 'Reversible · nothing sent yet',
            style: VigilTypography.meta.copyWith(color: colors.tx2),
          ),
        ],
      ),
    );
  }
}

/// Outlined 28px Undo button with a 2px accent bar along its bottom edge
/// shrinking to zero over [remaining] — the console's vg-fuse.
class _UndoFuseButton extends StatefulWidget {
  const _UndoFuseButton({required this.remaining, required this.onPressed});

  final Duration remaining;
  final VoidCallback onPressed;

  @override
  State<_UndoFuseButton> createState() => _UndoFuseButtonState();
}

class _UndoFuseButtonState extends State<_UndoFuseButton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _bar;

  @override
  void initState() {
    super.initState();
    _bar = AnimationController(
      vsync: this,
      duration: widget.remaining,
      value: 1,
    );
    // Shrink from full immediately — the fuse started when the controller
    // queued the decision, a frame or two before this card mounted.
    _bar.reverse(from: 1);
  }

  @override
  void dispose() {
    _bar.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    return AnimatedBuilder(
      animation: _bar,
      builder: (context, _) {
        // IntrinsicWidth bounds the stretch to the button's own width — a
        // Row child gets an unbounded main-axis max, and a stretching
        // Column would force the bar to infinite width.
        return IntrinsicWidth(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              OutlinedButton(
                onPressed: widget.onPressed,
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size(64, 28),
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  side: BorderSide(color: colors.ln2),
                  foregroundColor: colors.tx0,
                  textStyle: VigilTypography.label,
                ),
                child: const Text('Undo'),
              ),
              // vg-fuse: 2px accent bar, scaleX 1 → 0, linear.
              ClipRect(
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: FractionallySizedBox(
                    widthFactor: _bar.value,
                    child: Container(
                      height: 2,
                      color: colors.ac,
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
