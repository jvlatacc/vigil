import 'dart:async';

import 'package:flutter/material.dart';

import '../../theme/extensions.dart';
import '../../theme/vigil_typography.dart';

/// Hold-to-confirm (console `shared/HoldButton.tsx` + spec): for anything
/// Vigil cannot undo — isolate a host, quarantine a mailbox. 36px button,
/// 1px `poor` border, `poor` text; on pointer-down a `poor` fill grows
/// left→right over 1.6 s, the label becomes "Keep holding…" and the text
/// turns white; release early cancels. On completion [onConfirm] fires
/// once — the caller owns the committed state; there is no undo.
class HoldButton extends StatefulWidget {
  const HoldButton({
    super.key,
    required this.onConfirm,
    this.label = 'Hold to approve',
    this.busy = false,
    this.holdDuration = const Duration(milliseconds: 1600),
  });

  final VoidCallback onConfirm;
  final String label;
  final bool busy;
  final Duration holdDuration;

  @override
  State<HoldButton> createState() => _HoldButtonState();
}

class _HoldButtonState extends State<HoldButton> {
  bool _holding = false;

  /// Drives the fill while the pointer is down; the fraction done is
  /// `elapsed / holdDuration`.
  final Stopwatch _watch = Stopwatch();
  Timer? _tick;

  double get _progress => (_watch.elapsedMilliseconds /
          widget.holdDuration.inMilliseconds)
      .clamp(0.0, 1.0);

  void _start() {
    if (widget.busy || _holding) return;
    setState(() {
      _holding = true;
      _watch
        ..reset()
        ..start();
    });
    // ~30 fps is plenty for a linear fill and keeps tests deterministic.
    _tick = Timer.periodic(const Duration(milliseconds: 33), (_) {
      if (!_holding) return;
      if (_progress >= 1.0) {
        _complete();
      } else {
        setState(() {});
      }
    });
  }

  void _cancel() {
    _tick?.cancel();
    _tick = null;
    if (!_holding) return;
    setState(() => _holding = false);
  }

  void _complete() {
    _tick?.cancel();
    _tick = null;
    _watch.stop();
    setState(() => _holding = false);
    widget.onConfirm();
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final progress = _holding ? _progress : 0.0;
    final holding = _holding && progress < 1.0;
    final label = holding ? 'Keep holding…' : widget.label;
    return GestureDetector(
      onLongPressStart: (_) => _start(),
      onLongPressEnd: (_) => _cancel(),
      onLongPressCancel: _cancel,
      child: Container(
        key: const Key('hold-button'),
        height: 36,
        clipBehavior: Clip.antiAlias,
        decoration: BoxDecoration(
          color: colors.bg2,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: colors.poor),
        ),
        child: Stack(
          alignment: Alignment.center,
          children: [
            if (progress > 0)
              Positioned.fill(
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: FractionallySizedBox(
                    widthFactor: progress,
                    child: ColoredBox(color: colors.poor),
                  ),
                ),
              ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14),
              child: Text(
                label,
                style: VigilTypography.label.copyWith(
                  color: holding && progress > 0.35 ? colors.bg0 : colors.poor,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
