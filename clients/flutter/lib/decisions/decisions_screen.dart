import 'package:flutter/material.dart';

import '../approvals/approval_machine.dart';
import '../approvals/approvals_controller.dart';
import '../shared/stale_banner.dart';
import '../theme/extensions.dart';
import '../theme/vigil_typography.dart';
import 'decision_block.dart';

/// The Decisions queue — "Review and provide feedback for AI decisions"
/// (the console's decisions/DecisionsScreen.tsx): one decision block per
/// pending action, with the confidence meter, reversibility chip, and
/// evidence excerpt. Reversible approvals arm the 8 s undo fuse;
/// irreversible ones demand the 1.6 s hold; reject demands a reason.
class DecisionsScreen extends StatelessWidget {
  const DecisionsScreen({super.key, required this.controller});

  final ApprovalsController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final colors = context.vigilColors;
        // Rows without an action id are un-actionable — the decision
        // controls key everything off the id.
        final queue = [
          for (final a in controller.pending)
            if (a.actionId != null && a.actionId!.isNotEmpty) a,
        ];
        final count = queue.length;

        return RefreshIndicator(
          onRefresh: () => controller.refresh(),
          child: ListView(
            key: const Key('decisions-queue'),
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
                count == 0
                    ? 'No decisions wait on you.'
                    : count == 1
                        ? '1 decision waits on you'
                        : '$count decisions wait on you',
                style: VigilTypography.pageTitle.copyWith(color: colors.tx0),
              ),
              const SizedBox(height: 16),
              if (controller.pendingPhase == FeedPhase.loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (controller.pendingPhase == FeedPhase.error &&
                  queue.isEmpty) ...[
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: colors.bg1,
                    borderRadius: BorderRadius.circular(
                        context.vigilMetrics.radiusCard),
                    border: Border.all(color: colors.poor),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.error_outline, color: colors.poor, size: 18),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          controller.pendingError ?? '',
                          style: VigilTypography.meta
                              .copyWith(color: colors.tx1),
                        ),
                      ),
                      TextButton(
                        onPressed: () => controller.refresh(),
                        child: const Text('Retry'),
                      ),
                    ],
                  ),
                ),
              ] else if (count == 0) ...[
                const SizedBox(height: 32),
                Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.check_circle_outline,
                          size: 32, color: colors.good),
                      const SizedBox(height: 12),
                      Text(
                        'Queue clear — nothing waits on a person.',
                        style: VigilTypography.bodyStrong
                            .copyWith(color: colors.tx0),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Pending approvals land here every 20 seconds at '
                        'the console cadence.',
                        textAlign: TextAlign.center,
                        style:
                            VigilTypography.meta.copyWith(color: colors.tx2),
                      ),
                    ],
                  ),
                ),
              ] else ...[
                for (final item in queue)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: DecisionBlock(
                      item: item,
                      busy: controller.isBusy(item.actionId!),
                      onApprove: () => controller.beginFused(
                        actionId: item.actionId!,
                        title: item.title ?? 'Proposed action',
                        verb: FuseVerb.approve,
                      ),
                      onHoldConfirm: () => controller.approveNow(
                        actionId: item.actionId!,
                        title: item.title ?? 'Proposed action',
                      ),
                      onReject: (reason) => controller.beginFused(
                        actionId: item.actionId!,
                        title: item.title ?? 'Proposed action',
                        verb: FuseVerb.reject,
                        reason: reason,
                      ),
                    ),
                  ),
              ],
            ],
          ),
        );
      },
    );
  }
}
