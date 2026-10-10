import 'package:flutter/material.dart';

import '../theme/extensions.dart';
import '../theme/vigil_typography.dart';

/// Quick-pick reasons for rejecting a proposed action — filling the field
/// keeps the reason mandatory (the console's reject form) while one tap
/// covers the common calls.
const kRejectQuickPicks = [
  'Wrong target',
  'Too risky',
  'Duplicate',
  'Evidence is stale',
  'Handled manually',
];

/// The reject flow's inline reason entry — quick-pick chips that fill a
/// text field, and a submit that stays disabled until the field has a
/// non-blank reason. Reject always requires a reason (SCREENS.md).
class RejectReasonRow extends StatefulWidget {
  const RejectReasonRow({
    super.key,
    required this.onSubmit,
    this.enabled = true,
  });

  /// Called with the trimmed reason on submit.
  final ValueChanged<String> onSubmit;
  final bool enabled;

  @override
  State<RejectReasonRow> createState() => _RejectReasonRowState();
}

class _RejectReasonRowState extends State<RejectReasonRow> {
  final _controller = TextEditingController();

  bool get _hasReason => _controller.text.trim().isNotEmpty;

  @override
  void initState() {
    super.initState();
    _controller.addListener(() {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final reason = _controller.text.trim();
    if (reason.isEmpty) return;
    widget.onSubmit(reason);
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          'A reason is required.',
          style: VigilTypography.meta.copyWith(color: colors.tx2),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final pick in kRejectQuickPicks)
              ActionChip(
                label: Text(pick, style: VigilTypography.label),
                backgroundColor: colors.bg3,
                side: BorderSide(color: colors.ln2),
                onPressed: widget.enabled
                    ? () {
                        _controller.text = pick;
                        _controller.selection = TextSelection.fromPosition(
                          TextPosition(offset: pick.length),
                        );
                      }
                    : null,
              ),
          ],
        ),
        const SizedBox(height: 8),
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(
              child: TextField(
                controller: _controller,
                enabled: widget.enabled,
                style: VigilTypography.body.copyWith(color: colors.tx0),
                decoration: InputDecoration(
                  isDense: true,
                  hintText: 'Why are you rejecting this?',
                  hintStyle: VigilTypography.meta.copyWith(color: colors.tx3),
                  filled: true,
                  fillColor: colors.bg2,
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(
                        context.vigilMetrics.radiusButton),
                    borderSide: BorderSide(color: colors.ln2),
                  ),
                ),
                onSubmitted: widget.enabled ? (_) => _submit() : null,
              ),
            ),
            const SizedBox(width: 8),
            FilledButton(
              onPressed: widget.enabled && _hasReason ? _submit : null,
              style: FilledButton.styleFrom(
                backgroundColor: colors.poor,
                foregroundColor: colors.tx0,
                disabledBackgroundColor: colors.bg3,
                disabledForegroundColor: colors.tx3,
                textStyle: VigilTypography.label,
                minimumSize: const Size(0, 36),
              ),
              child: const Text('Reject'),
            ),
          ],
        ),
      ],
    );
  }
}
