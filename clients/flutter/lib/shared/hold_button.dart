import 'package:flutter/material.dart';

import '../approvals/approval_machine.dart';
import '../theme/extensions.dart';
import '../theme/vigil_typography.dart';

/// The console's hold-to-confirm button
/// (docs/design/console/components/hold-to-confirm.md): for anything Vigil
/// cannot undo. 36px button, 1px poor border, poor text; on pointer-down a
/// poor fill grows left→right over 1.6 s, the label becomes "Keep
/// holding…" and the text turns white; release early cancels. On
/// completion [onConfirm] fires once — no undo, ever. Never used for
/// reversible actions.
class HoldButton extends StatefulWidget {
  const HoldButton({
    super.key,
    required this.label,
    required this.onConfirm,
    this.enabled = true,
    this.doneLabel,
  });

  final String label;

  /// Fires when the 1.6 s hold completes.
  final VoidCallback onConfirm;
  final bool enabled;

  /// Label after completion (e.g. "Approved · isolating FIN-WS-0231").
  final String? doneLabel;

  @override
  State<HoldButton> createState() => _HoldButtonState();
}

class _HoldButtonState extends State<HoldButton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _fill = AnimationController(
    vsync: this,
    duration: holdConfirmLength,
  );

  bool _completed = false;

  @override
  void initState() {
    super.initState();
    _fill.addStatusListener((status) {
      if (status == AnimationStatus.completed && !_completed) {
        _completed = true;
        widget.onConfirm();
        if (mounted) setState(() {});
      }
    });
  }

  @override
  void dispose() {
    _fill.dispose();
    super.dispose();
  }

  void _press() {
    if (widget.enabled && !_completed) _fill.forward();
  }

  /// Release early cancels — the console snaps the fill back (the base
  /// .home-hold has no width transition).
  void _release() {
    if (_completed) return;
    _fill.stop();
    _fill.value = 0;
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      enabled: widget.enabled,
      label: '${widget.label} — press and hold to confirm; '
          'this cannot be undone.',
      child: AnimatedBuilder(
        animation: _fill,
        // holding/done/label/textColor are computed INSIDE the builder on
        // purpose: the builder re-runs on every animation notification,
        // while locals captured from build() go stale — the label would
        // never flip to "Keep holding…" or to its done state.
        builder: (context, _) {
          final colors = context.vigilColors;
          final done = _completed;
          final holding = _fill.isAnimating || (_fill.value > 0 && !done);
          final label = done
              ? (widget.doneLabel ?? widget.label)
              : (holding ? 'Keep holding…' : widget.label);
          final textColor = !widget.enabled
              ? colors.tx3
              : done
                  ? colors.good
                  : holding
                      ? colors.tx0
                      : colors.poor;
          return Listener(
            onPointerDown: (_) => _press(),
            onPointerUp: (_) => _release(),
            onPointerCancel: (_) => _release(),
            child: Container(
              height: 36,
              padding: const EdgeInsets.symmetric(horizontal: 14),
              decoration: BoxDecoration(
                color: colors.bg2,
                borderRadius: BorderRadius.circular(
                    context.vigilMetrics.radiusButton),
                border: Border.all(
                    color: widget.enabled ? colors.poor : colors.ln2),
              ),
              child: Stack(
                alignment: Alignment.centerLeft,
                children: [
                  // The poor fill, left→right (hold-approve.css).
                  // Positioned.fill binds the fill to the stack's resolved
                  // size — a plain Align child multiplies the zero-ish
                  // width factor by the Row's unbounded main axis, which
                  // yields NaN constraints.
                  if (!done)
                    Positioned.fill(
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: FractionallySizedBox(
                          widthFactor: _fill.value,
                          child: Container(
                              color: colors.poor.withValues(alpha: 0.35)),
                        ),
                      ),
                    ),
                  Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: VigilTypography.label.copyWith(color: textColor),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
