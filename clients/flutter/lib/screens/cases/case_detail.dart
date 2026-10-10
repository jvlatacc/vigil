import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';

import '../../api/vigil_client.dart';
import '../../data/polling_scheduler.dart';
import '../../theme/extensions.dart';
import '../../theme/vigil_typography.dart';
import '../shared/approval_fuse.dart';
import '../shared/hold_button.dart';
import '../shared/severity_chip.dart';
import '../shared/state_pill.dart';
import '../shared/vigil_time.dart';

/// The console's approvals cadence — the case page's approval strip rides
/// the same 20 s poll as Decisions (`useDecisions.ts:178`).
const _approvalsPollInterval = Duration(seconds: 20);

/// One case, read whole: header, linked findings, the evidence trail, and
/// the case-scoped approval cards (reversible → 8 s undo fuse; irreversible
/// → hold-to-confirm; reject always requires a reason). Console: `CasePage`
/// per SCREENS.md, with `shared/HoldButton` semantics.
class CaseDetailPane extends StatefulWidget {
  const CaseDetailPane({
    super.key,
    required this.client,
    required this.fuse,
    required this.caseId,
    required this.onChanged,
  });

  final VigilClient client;
  final FuseController fuse;
  final String caseId;

  /// Called when a decision here could change the queue behind the pane.
  final VoidCallback onChanged;

  @override
  State<CaseDetailPane> createState() => _CaseDetailPaneState();
}

class _CaseDetailPaneState extends State<CaseDetailPane> {
  late final PollingScheduler _scheduler = PollingScheduler(
    interval: _approvalsPollInterval,
    tick: (silent) => _poll(silent),
  );

  CaseDetailResponse? _case;
  List<CaseEvidenceSchema> _evidence = const [];
  List<NeedsYouItem> _needsYou = const [];
  bool _loaded = false;
  bool _failed = false;
  int _settledSeen = 0;

  @override
  void initState() {
    super.initState();
    _settledSeen = widget.fuse.settled;
    widget.fuse.addListener(_onFuse);
    _scheduler.start();
  }

  @override
  void dispose() {
    widget.fuse.removeListener(_onFuse);
    _scheduler.dispose();
    super.dispose();
  }

  /// A fused commit (maybe fired from another screen) landed — reload so
  /// the card reflects the server's truth.
  void _onFuse() {
    if (widget.fuse.settled == _settledSeen) return;
    _settledSeen = widget.fuse.settled;
    _reload();
    widget.onChanged();
  }

  Future<void> _poll(bool silent) async {
    try {
      final futures = await Future.wait([
        widget.client.v1.getCasesApi().getApiV1CasesCaseId(caseId: widget.caseId),
        widget.client.v1
            .getCasesApi()
            .getApiV1CasesCaseIdEvidence(caseId: widget.caseId),
        widget.client.v1.getApprovalsApi().getApiV1ApprovalsNeedsYou(),
      ]);
      final detail = futures[0] as Response<CaseDetailResponse>;
      final evidence = futures[1] as Response<CaseEvidenceListResponse>;
      final needsYou = futures[2] as Response<NeedsYouResponse>;
      if (!mounted) return;
      setState(() {
        _case = detail.data;
        _evidence = evidence.data?.evidence.toList() ?? const [];
        _needsYou = [
          for (final item in needsYou.data?.items ?? const <NeedsYouItem>[])
            if (item.caseId == widget.caseId) item,
        ];
        _loaded = true;
        _failed = false;
      });
    } on Exception {
      if (!mounted) return;
      setState(() {
        _failed = true;
        _loaded = true;
      });
    }
  }

  void _reload() => _scheduler.refresh();

  void _approve(NeedsYouItem item, {required bool viaHold}) {
    if (viaHold) {
      // Irreversible: the hold completed — commit now, no fuse, ever.
      _send(item, approve: true);
      return;
    }
    widget.fuse.start(FusedAction(
      key: item.sourceId,
      message: 'Approving · ${item.title}',
      commit: () => _send(item, approve: true),
      doneText: 'Approved · resuming run',
    ));
  }

  void _reject(NeedsYouItem item, String reason) {
    widget.fuse.start(FusedAction(
      key: item.sourceId,
      message: 'Rejecting · ${item.title}',
      commit: () => _send(item, approve: false, reason: reason),
      doneText: 'Rejected · recorded on the run',
    ));
  }

  Future<void> _send(NeedsYouItem item,
      {required bool approve, String? reason}) async {
    final api = widget.client.v1.getApprovalsApi();
    if (approve) {
      await api.postApiV1ApprovalsActionIdApprove(
        actionId: item.sourceId,
        approveRequest: ApproveRequest(),
      );
    } else {
      await api.postApiV1ApprovalsActionIdReject(
        actionId: item.sourceId,
        rejectRequest: RejectRequest((b) => b..reason = reason ?? ''),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_loaded) return _detailLoading(context);
    final c = _case;
    if (c == null) return _detailError(context);
    final colors = context.vigilColors;
    return RefreshIndicator(
      onRefresh: () async => _reload(),
      child: ListView(
        key: const Key('case-detail'),
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              StatePill(state: c.combinedState),
              const SizedBox(width: 8),
              if (c.priority != null && c.priority!.isNotEmpty)
                SeverityChip(severity: c.priority),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            c.title ?? 'Untitled case',
            style: VigilTypography.sectionTitle.copyWith(color: colors.tx0),
          ),
          if (c.createdAt != null) ...[
            const SizedBox(height: 4),
            Text(
              [
                'Case ${c.caseId}',
                if (c.assignee != null && c.assignee!.isNotEmpty)
                  'assigned to ${c.assignee!}',
                'opened ${fmtUtc(parseUtc(c.createdAt!) ?? DateTime.now().toUtc())}',
              ].join(' · '),
              style: VigilTypography.meta.copyWith(color: colors.tx2),
            ),
          ],
          if (c.description != null && c.description!.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(c.description!,
                style: VigilTypography.body.copyWith(color: colors.tx1)),
          ],
          if ((c.mitreTechniques ?? const <String>[]).isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 4,
              runSpacing: 4,
              children: [
                for (final t in c.mitreTechniques ?? const <String>[])
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: colors.bg3,
                      borderRadius: BorderRadius.circular(
                          context.vigilMetrics.radiusPillSm),
                    ),
                    child: Text(t,
                        style: VigilTypography.meta
                            .copyWith(color: colors.tx1)),
                  ),
              ],
            ),
          ],
          _approvalsSection(context),
          _sectionTitle(context, 'Linked findings'),
          if ((c.linkedFindings ?? const <CaseLinkedFinding>[]).isEmpty)
            _muted(context, 'No findings linked to this case.')
          else
            for (final f in c.linkedFindings ?? const <CaseLinkedFinding>[])
              _linkedFinding(context, f),
          _sectionTitle(context, 'Evidence trail'),
          if (_evidence.isEmpty)
            _muted(context, 'No evidence collected for this case.')
          else
            for (final e in _evidence) _evidenceRow(context, e),
          if (_failed) ...[
            const SizedBox(height: 12),
            Text(
              'Some reads failed — the page retries with backoff.',
              style: VigilTypography.meta.copyWith(color: colors.poor),
            ),
          ],
          const SizedBox(height: 24),
        ],
      ),
    );
  }

  Widget _detailLoading(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 12),
            Text('Loading case…',
                style: VigilTypography.meta
                    .copyWith(color: context.vigilColors.tx2)),
          ],
        ),
      );

  Widget _detailError(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Case could not be loaded',
              style: VigilTypography.bodyStrong
                  .copyWith(color: context.vigilColors.tx0),
            ),
            const SizedBox(height: 16),
            FilledButton.tonal(
              key: const Key('case-detail-retry'),
              onPressed: _reload,
              child: const Text('Retry'),
            ),
          ],
        ),
      );

  Widget _sectionTitle(BuildContext context, String title) => Padding(
        padding: const EdgeInsets.only(top: 20, bottom: 8),
        child: Text(title,
            style: VigilTypography.label
                .copyWith(color: context.vigilColors.tx2)),
      );

  Widget _muted(BuildContext context, String text) => Text(text,
      style: VigilTypography.meta.copyWith(color: context.vigilColors.tx2));

  Widget _approvalsSection(BuildContext context) {
    final colors = context.vigilColors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _sectionTitle(context, 'Needs you'),
        if (_needsYou.isEmpty)
          _muted(context, 'Nothing on this case waits for a person.')
        else
          for (final item in _needsYou)
            if (!widget.fuse.isPending(item.sourceId))
              _approvalCard(context, item),
        if (widget.fuse.pendingKeys.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Text(
              'Decision pending — the undo fuse is still running.',
              style: VigilTypography.meta.copyWith(color: colors.fair),
            ),
          ),
      ],
    );
  }

  Widget _approvalCard(BuildContext context, NeedsYouItem item) {
    final colors = context.vigilColors;
    final irreversible = item.reversibility == 'irreversible';
    return Container(
      key: Key('case-approval-${item.sourceId}'),
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colors.bg1,
        borderRadius:
            BorderRadius.circular(context.vigilMetrics.radiusCardInner),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: irreversible ? colors.poorBg : colors.acBg,
                  borderRadius: BorderRadius.circular(
                      context.vigilMetrics.radiusPillSm),
                ),
                child: Text(
                  irreversible ? 'irreversible' : 'reversible',
                  style: VigilTypography.meta.copyWith(
                    color: irreversible ? colors.poor : colors.acTx,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  fmtAge(parseUtc(item.createdAt)?.difference(
                          DateTime.now().toUtc()) ??
                      Duration.zero),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: VigilTypography.meta.copyWith(color: colors.tx2),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(item.title,
              style:
                  VigilTypography.bodyStrong.copyWith(color: colors.tx0)),
          if (item.reason.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(item.reason,
                style: VigilTypography.meta.copyWith(color: colors.tx2)),
          ],
          const SizedBox(height: 10),
          // Wrap, not Row: the hold-to-confirm label plus Reject cannot
          // always share one line on a phone — floating controls cover
          // nothing (DESIGN.md §7).
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (irreversible)
                HoldButton(
                  label: 'Hold to approve — cannot be undone',
                  busy: false,
                  onConfirm: () => _approve(item, viaHold: true),
                )
              else
                FilledButton(
                  key: Key('case-approve-${item.sourceId}'),
                  onPressed: () => _approve(item, viaHold: false),
                  child: const Text('Approve'),
                ),
              OutlinedButton(
                key: Key('case-reject-${item.sourceId}'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: colors.poor,
                  side: BorderSide(color: colors.poor),
                ),
                onPressed: () => _rejectSheet(context, item),
                child: const Text('Reject'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _rejectSheet(BuildContext context, NeedsYouItem item) {
    final colors = context.vigilColors;
    final controller = TextEditingController();
    const quickPicks = ['Too risky', 'Wrong target', 'Already handled'];
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: colors.bg1,
      isScrollControlled: true,
      builder: (sheetContext) => StatefulBuilder(
        builder: (sheetContext, setSheetState) => Padding(
          padding: EdgeInsets.fromLTRB(
              16, 16, 16,
              16 + MediaQuery.of(sheetContext).viewInsets.bottom),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Reject',
                  style: VigilTypography.sectionTitle
                      .copyWith(color: colors.tx0)),
              const SizedBox(height: 4),
              Text(
                'Required. Recorded on the workflow run\'s audit trail.',
                style: VigilTypography.meta.copyWith(color: colors.tx2),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 4,
                runSpacing: 4,
                children: [
                  for (final pick in quickPicks)
                    ActionChip(
                      label: Text(pick),
                      onPressed: () =>
                          setSheetState(() => controller.text = pick),
                      labelStyle:
                          VigilTypography.meta.copyWith(color: colors.tx1),
                      visualDensity: VisualDensity.compact,
                    ),
                ],
              ),
              const SizedBox(height: 10),
              TextField(
                key: const Key('reject-reason'),
                controller: controller,
                autofocus: true,
                maxLines: 3,
                style: VigilTypography.body.copyWith(color: colors.tx0),
                decoration: InputDecoration(
                  hintText: 'Why is this being rejected?',
                  hintStyle:
                      VigilTypography.meta.copyWith(color: colors.tx3),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(
                        context.vigilMetrics.radiusButton),
                  ),
                ),
                onChanged: (_) => setSheetState(() {}),
              ),
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.of(sheetContext).pop(),
                    child: const Text('Cancel'),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    key: const Key('reject-submit'),
                    style: FilledButton.styleFrom(
                      backgroundColor: colors.poor,
                      foregroundColor: colors.bg0,
                    ),
                    onPressed: controller.text.trim().isEmpty
                        ? null
                        : () {
                            Navigator.of(sheetContext).pop();
                            _reject(item, controller.text.trim());
                          },
                    child: const Text('Reject'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _linkedFinding(BuildContext context, CaseLinkedFinding f) {
    final colors = context.vigilColors;
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: colors.bg1,
        borderRadius:
            BorderRadius.circular(context.vigilMetrics.radiusCardInner),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(f.title ?? f.findingId,
              style: VigilTypography.bodyStrong.copyWith(color: colors.tx0)),
          if (f.description != null && f.description!.isNotEmpty)
            Text(f.description!,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: VigilTypography.meta.copyWith(color: colors.tx2)),
        ],
      ),
    );
  }

  Widget _evidenceRow(BuildContext context, CaseEvidenceSchema e) {
    final colors = context.vigilColors;
    final collected = parseUtc(e.collectedAt ?? e.createdAt);
    return Container(
      key: Key('evidence-${e.evidenceId ?? ''}'),
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: colors.bg1,
        borderRadius:
            BorderRadius.circular(context.vigilMetrics.radiusCardInner),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: colors.bg3,
                  borderRadius: BorderRadius.circular(
                      context.vigilMetrics.radiusPillSm),
                ),
                child: Text(e.evidenceType ?? 'evidence',
                    style:
                        VigilTypography.meta.copyWith(color: colors.tx1)),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  e.name ?? 'Evidence',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: VigilTypography.bodyStrong
                      .copyWith(color: colors.tx0),
                ),
              ),
            ],
          ),
          if (e.description != null && e.description!.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(e.description!,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: VigilTypography.meta.copyWith(color: colors.tx2)),
          ],
          const SizedBox(height: 4),
          Text(
            [
              if (e.collectedBy != null && e.collectedBy!.isNotEmpty)
                'collected by ${e.collectedBy!}',
              if (collected != null) fmtUtc(collected),
              if (e.filePath != null && e.filePath!.isNotEmpty) e.filePath!,
            ].join(' · '),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: VigilTypography.meta.copyWith(color: colors.tx3),
          ),
        ],
      ),
    );
  }
}
