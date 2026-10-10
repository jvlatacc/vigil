import 'package:flutter/material.dart';

import '../theme/extensions.dart';
import '../theme/vigil_typography.dart';

/// Colour pairs for the console's state pill
/// (docs/design/console/components/state-pill.md): Acting good, Running ·
/// asks first accent, Needs you poor, Closed muted, Idle dim.
enum StatePillTone { good, accent, poor, muted, dim }

/// The console's state pill: height 22, padding 0 9, radius 999, font
/// 12/700, a 7px dot before the text. [blink] reproduces the 1.6 s blink
/// on the Needs-you dot (and yields to reduced-motion).
class StatePill extends StatelessWidget {
  const StatePill({
    super.key,
    required this.label,
    this.tone = StatePillTone.muted,
    this.blink = false,
  });

  final String label;
  final StatePillTone tone;
  final bool blink;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final (fg, bg) = switch (tone) {
      StatePillTone.good => (colors.good, colors.goodBg),
      StatePillTone.accent => (colors.ac, colors.acBg),
      StatePillTone.poor => (colors.poor, colors.poorBg),
      StatePillTone.muted => (colors.tx2, colors.bg3),
      StatePillTone.dim => (colors.tx3, colors.bg2),
    };
    return Container(
      height: 22,
      padding: const EdgeInsets.symmetric(horizontal: 9),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: fg.withValues(alpha: 0.38)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _Dot(color: fg, blink: blink),
          const SizedBox(width: 6),
          Text(
            label,
            style: VigilTypography.label.copyWith(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: fg,
            ),
          ),
        ],
      ),
    );
  }
}

class _Dot extends StatelessWidget {
  const _Dot({required this.color, required this.blink});

  final Color color;
  final bool blink;

  @override
  Widget build(BuildContext context) {
    final dot = Container(
      width: 7,
      height: 7,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
    final reducedMotion = MediaQuery.of(context).disableAnimations;
    if (!blink || reducedMotion) return dot;
    // vg-blink: opacity 1 → .25 → 1 over the 1.6 s cycle.
    return _BlinkingDot(color: color);
  }
}

class _BlinkingDot extends StatefulWidget {
  const _BlinkingDot({required this.color});

  final Color color;

  @override
  State<_BlinkingDot> createState() => _BlinkingDotState();
}

class _BlinkingDotState extends State<_BlinkingDot>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1600),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        // 0%,100% → 1; 50% → .25 (triangle wave).
        final t = _controller.value;
        final opacity = 1.0 - 0.75 * (1.0 - (2.0 * t - 1.0).abs());
        return Opacity(opacity: opacity, child: _dot());
      },
      child: _dot(),
    );
  }

  Widget _dot() => Container(
        width: 7,
        height: 7,
        decoration:
            BoxDecoration(color: widget.color, shape: BoxShape.circle),
      );
}
