import 'package:flutter/material.dart';
import 'package:one_of/any_of.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';

import '../approvals/approval_machine.dart';
import '../shared/hold_button.dart';
import '../shared/reject_reason_row.dart';
import '../shared/reversibility_chip.dart';
import '../shared/state_pill.dart';
import '../theme/extensions.dart';
import '../theme/vigil_colors.dart';
import '../theme/vigil_typography.dart';

/// The confidence meter's tone against the autonomy thresholds the backend
/// renders decision rules with: 0.90 is the auto-approve line, 0.85 the
/// quick-review line (core/response/config.py; console `confidenceLine`).
Color confidenceTone(double confidence, VigilColors colors) {
  if (confidence >= 0.90) return colors.good;
  if (confidence >= 0.85) return colors.fair;
  return colors.poor;
}

/// The block's sub-line: the decision rule the server recorded, else the
/// auto-approve note the console computes when no reason is attached
/// (HomeScreen.tsx `confidenceLine`).
String confidenceSubLine(String? reason, double confidence) {
  if (reason != null && reason.trim().isNotEmpty) return reason;
  return confidence >= 0.90
      ? 'Meets the 0.90 auto-approve line'
      : 'Confidence below the 0.90 auto-approve line';
}

/// The evidence excerpt: evidence arrives as a string, a list of entries,
/// or an object's values (AnyOf). Returns null when effectively empty —
/// the block then renders no evidence inset.
String? evidenceExcerpt(AnyOf? evidence) {
  if (evidence == null || evidence.isNull) return null;
  final value = evidence.values.values
      .cast<Object?>()
      .firstWhere((v) => v != null, orElse: () => null);
  if (value == null) return null;
  if (value is String) {
    final trimmed = value.trim();
    return trimmed.isEmpty ? null : trimmed;
  }
  if (value is List) {
    final joined = value.whereType<Object>().map(_entryText).join('\n');
    return joined.trim().isEmpty ? null : joined;
  }
  if (value is Map) {
    final joined = value.values.whereType<Object>().map(_entryText).join('\n');
    return joined.trim().isEmpty ? null : joined;
  }
  final text = _entryText(value);
  return text.trim().isEmpty ? null : text;
}

String _entryText(Object entry) {
  if (entry is Map) {
    final label = entry['title'] ?? entry['label'] ?? entry['kind'] ?? '';
    final detail = entry['detail'] ?? entry['summary'] ?? entry['value'] ?? '';
    final text = [label, detail]
        .whereType<Object>()
        .map((p) => p.toString().trim())
        .where((p) => p.isNotEmpty)
        .join(' — ');
    return text;
  }
  return entry.toString().trim();
}

/// The console's decision-block port (docs/design/console/components/
/// decision-block.md) for the Decisions queue: "Needs you" pill + waited
/// label, the action title, a confidence meter with reversibility chip and
/// rule sub-line, the evidence excerpt, and the three decisions — approve
/// (8 s undo fuse when reversible), hold-to-confirm (irreversible), reject
/// with a mandatory reason.
class DecisionBlock extends StatefulWidget {
  const DecisionBlock({
    super.key,
    required this.item,
    required this.onApprove,
    required this.onHoldConfirm,
    required this.onReject,
    this.now,
    this.busy = false,
  });

  final PendingActionResponse item;

  /// Reversible approve — the screen starts the undo fuse.
  final VoidCallback onApprove;

  /// Irreversible hold-to-confirm completed — commits immediately.
  final VoidCallback onHoldConfirm;

  /// Reject with the mandatory reason — the screen starts the fuse.
  final ValueChanged<String> onReject;

  final DateTime Function()? now;
  final bool busy;

  @override
  State<DecisionBlock> createState() => _DecisionBlockState();
}

class _DecisionBlockState extends State<DecisionBlock> {
  bool _rejecting = false;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final item = widget.item;
    final confidence = (item.confidence ?? 0).toDouble();
    final irreversible = item.reversibility == 'irreversible';

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colors.bg1,
        borderRadius: BorderRadius.circular(context.vigilMetrics.radiusCard),
        border: Border.all(color: colors.ln1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              const StatePill(
                  label: 'Needs you', tone: StatePillTone.poor, blink: true),
              Expanded(
                child: Text(
                  waitedLabel(item.createdAt, (widget.now ?? DateTime.now)()),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.right,
                  style: VigilTypography.meta.copyWith(color: colors.tx2),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            item.title ?? 'Proposed action',
            style: VigilTypography.blockTitle.copyWith(color: colors.tx0),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Text(
                confidence.toStringAsFixed(2),
                style: VigilTypography.countChip.copyWith(color: colors.tx1),
              ),
              const SizedBox(width: 8),
              ReversibilityChip(reversibility: item.reversibility),
              const SizedBox(width: 8),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(999),
                  child: SizedBox(
                    height: 4,
                    child: Stack(
                      children: [
                        Container(color: colors.bg4),
                        FractionallySizedBox(
                          widthFactor: confidence.clamp(0.0, 1.0),
                          child: Container(
                              color: confidenceTone(confidence, colors)),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            confidenceSubLine(item.reason, confidence),
            style: VigilTypography.meta.copyWith(color: colors.tx2),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          ...?_evidenceInset(context),
          const SizedBox(height: 10),
          if (_rejecting)
            RejectReasonRow(
              enabled: !widget.busy,
              onSubmit: (reason) {
                setState(() => _rejecting = false);
                widget.onReject(reason);
              },
            )
          else
            Row(
              children: [
                if (irreversible)
                  HoldButton(
                    key: const ValueKey('hold-approve'),
                    label: 'Approve',
                    enabled: !widget.busy,
                    onConfirm: widget.onHoldConfirm,
                  )
                else
                  FilledButton(
                    key: const ValueKey('approve-tap'),
                    onPressed: widget.busy ? null : () => widget.onApprove(),
                    style: FilledButton.styleFrom(
                      backgroundColor: colors.ac,
                      foregroundColor: colors.tx0,
                      textStyle: VigilTypography.label,
                      minimumSize: const Size(0, 36),
                    ),
                    child: const Text('Approve'),
                  ),
                const SizedBox(width: 8),
                OutlinedButton(
                  onPressed: widget.busy
                      ? null
                      : () => setState(() => _rejecting = true),
                  style: OutlinedButton.styleFrom(
                    side: BorderSide(color: colors.ln2),
                    foregroundColor: colors.tx1,
                    textStyle: VigilTypography.label,
                    minimumSize: const Size(0, 36),
                  ),
                  child: const Text('Reject'),
                ),
              ],
            ),
        ],
      ),
    );
  }

  List<Widget>? _evidenceInset(BuildContext context) {
    final colors = context.vigilColors;
    final excerpt = evidenceExcerpt(widget.item.evidence);
    if (excerpt == null) return null;
    return [
      Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: colors.bg2,
            borderRadius:
                BorderRadius.circular(context.vigilMetrics.radiusCardInner),
          ),
          child: Text(
            excerpt,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: VigilTypography.countChip.copyWith(color: colors.tx2),
          ),
        ),
      ),
    ];
  }
}
