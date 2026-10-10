import 'package:flutter/material.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';

import '../approvals/approval_machine.dart';
import '../approvals/approvals_controller.dart';
import '../shared/hold_button.dart';
import '../shared/needs_you_strip.dart';
import '../shared/reject_reason_row.dart';
import '../shared/reversibility_chip.dart';
import '../shared/stale_banner.dart';
import '../theme/extensions.dart';
import '../theme/vigil_typography.dart';

/// Home — "What needs a person" (the console's home/HomeScreen.tsx): the
/// needs-you feed and pending-approvals count at the console cadence,
/// oldest first, top four shown until expanded. Approve commits through
/// the controller's undo fuse (reversible) or hold-to-confirm
/// (irreversible); reject always demands a reason.
class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    required this.controller,
    this.onOpenCase,
    this.onReview,
  });

  final ApprovalsController controller;

  /// Opens the case a needs-you item belongs to (Cases port pending).
  final VoidCallback? onOpenCase;

  /// Jumps to the Decisions queue (the strip's Review action).
  final VoidCallback? onReview;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  static const int _topN = 4;

  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final colors = context.vigilColors;
        final items = controller.needsYou;
        final shown = _expanded ? items : items.take(_topN).toList();
        final hidden = items.length - shown.length;

        return RefreshIndicator(
          onRefresh: () => controller.refresh(),
          child: ListView(
            key: const Key('home-feed'),
            padding: const EdgeInsets.all(16),
            children: [
              if (controller.stale)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: StaleBanner(
                    lastGoodAt: controller.lastGoodAt,
                    now: controller.now,
                  ),
                ),
              Text(
                _headline(controller.shownNeedsYouCount),
                style: VigilTypography.pageTitle.copyWith(color: colors.tx0),
              ),
              const SizedBox(height: 4),
              Text(
                'Oldest first, top $_topN shown.',
                style: VigilTypography.meta.copyWith(color: colors.tx2),
              ),
              const SizedBox(height: 16),
              if (items.isNotEmpty)
                NeedsYouStrip(
                  count: items.length,
                  onReview: widget.onReview,
                ),
              if (controller.needsYouPhase == FeedPhase.loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (controller.needsYouPhase == FeedPhase.error &&
                  items.isEmpty) ...[
                _ErrorPane(
                  message: controller.needsYouError ?? '',
                  onRetry: () => controller.refresh(),
                ),
              ] else if (items.isEmpty) ...[
                const SizedBox(height: 32),
                Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.check_circle_outline,
                          size: 32, color: colors.good),
                      const SizedBox(height: 12),
                      Text(
                        'Nothing needs a person right now',
                        style: VigilTypography.bodyStrong
                            .copyWith(color: colors.tx0),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Approvals and escalations land here at the '
                        'console cadence.',
                        textAlign: TextAlign.center,
                        style:
                            VigilTypography.meta.copyWith(color: colors.tx2),
                      ),
                    ],
                  ),
                ),
              ] else ...[
                for (final item in shown)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _NeedsYouCard(
                      item: item,
                      controller: controller,
                      onOpenCase: widget.onOpenCase,
                    ),
                  ),
                if (hidden > 0)
                  TextButton(
                    key: const Key('show-more'),
                    onPressed: () => setState(() => _expanded = true),
                    child: Text('Show $hidden more',
                        style: VigilTypography.label),
                  ),
              ],
            ],
          ),
        );
      },
    );
  }

  /// The headline the console renders for the needs-you count.
  static String _headline(int count) {
    if (count == 0) return 'Nothing needs a person right now.';
    if (count == 1) return '1 decision waits on you';
    return '$count decisions wait on you';
  }
}

/// One needs-you card — the console's DecisionCard: waited + reversibility
/// row, title, case/reason meta, and the three decisions.
class _NeedsYouCard extends StatefulWidget {
  const _NeedsYouCard({
    required this.item,
    required this.controller,
    this.onOpenCase,
  });

  final NeedsYouItem item;
  final ApprovalsController controller;
  final VoidCallback? onOpenCase;

  @override
  State<_NeedsYouCard> createState() => _NeedsYouCardState();
}

class _NeedsYouCardState extends State<_NeedsYouCard> {
  bool _rejecting = false;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    final item = widget.item;
    final controller = widget.controller;
    final irreversible = item.reversibility == 'irreversible';
    final busy = controller.isBusy(item.sourceId);

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
              Expanded(
                child: Text(
                  waitedLabel(item.createdAt, controller.now()),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: VigilTypography.meta.copyWith(color: colors.tx2),
                ),
              ),
              ReversibilityChip(reversibility: item.reversibility),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            item.title,
            style: VigilTypography.caseTitle.copyWith(color: colors.tx0),
          ),
          const SizedBox(height: 4),
          Text(
            [
              if (item.caseId != null && item.caseId!.isNotEmpty)
                'Case ${item.caseId}',
              if (item.reason.trim().isNotEmpty) item.reason,
            ].join(' · '),
            style: VigilTypography.meta.copyWith(color: colors.tx2),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 12),
          if (_rejecting)
            RejectReasonRow(
              enabled: !busy,
              onSubmit: (reason) {
                setState(() => _rejecting = false);
                controller.beginFused(
                  actionId: item.sourceId,
                  title: item.title,
                  verb: FuseVerb.reject,
                  reason: reason,
                );
              },
            )
          else
            Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                if (irreversible)
                  HoldButton(
                    label: 'Approve',
                    enabled: !busy,
                    onConfirm: () => controller.approveNow(
                      actionId: item.sourceId,
                      title: item.title,
                    ),
                  )
                else
                  FilledButton(
                    key: Key('approve-${item.sourceId}'),
                    onPressed: busy
                        ? null
                        : () => controller.beginFused(
                              actionId: item.sourceId,
                              title: item.title,
                              verb: FuseVerb.approve,
                            ),
                    style: FilledButton.styleFrom(
                      backgroundColor: colors.ac,
                      foregroundColor: colors.tx0,
                      textStyle: VigilTypography.label,
                      minimumSize: const Size(0, 36),
                    ),
                    child: const Text('Approve'),
                  ),
                OutlinedButton(
                  onPressed: busy
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
                if (item.caseId != null && item.caseId!.isNotEmpty)
                  TextButton(
                    onPressed: widget.onOpenCase,
                    child: const Text('Open case'),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}

class _ErrorPane extends StatelessWidget {
  const _ErrorPane({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final colors = context.vigilColors;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colors.bg1,
        borderRadius: BorderRadius.circular(context.vigilMetrics.radiusCard),
        border: Border.all(color: colors.poor),
      ),
      child: Row(
        children: [
          Icon(Icons.error_outline, color: colors.poor, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: VigilTypography.meta.copyWith(color: colors.tx1),
            ),
          ),
          TextButton(onPressed: onRetry, child: const Text('Retry')),
        ],
      ),
    );
  }
}
