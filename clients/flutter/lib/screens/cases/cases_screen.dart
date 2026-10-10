import 'package:flutter/material.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';

import '../../api/vigil_client.dart';
import '../../data/polling_scheduler.dart';
import '../../theme/extensions.dart';
import '../../theme/vigil_typography.dart';
import '../shared/approval_fuse.dart';
import '../shared/state_pill.dart';
import '../shared/vigil_time.dart';
import 'case_detail.dart';

/// The console's human-work cadence — approvals poll at 20 s
/// (`useDecisions.ts:178`); the case queue rides the same rhythm.
const casesPollInterval = Duration(seconds: 20);

/// Cases — "Manage investigation cases": master-detail on wide screens
/// (≥ 600 dp), list plus a pushed detail sheet on phones. Deep links carry
/// the console's `?case=<id>` semantics — the case opens selected. Console:
/// `screens/cases/CasesScreen.tsx`.
class CasesScreen extends StatefulWidget {
  const CasesScreen({
    super.key,
    required this.client,
    required this.fuse,
    this.initialCaseId,
  });

  final VigilClient client;

  /// The shell's undo fuse — approvals from the case detail commit through
  /// it so a fuse survives navigating away.
  final FuseController fuse;

  /// `?case=<id>` — the case to open on arrival.
  final String? initialCaseId;

  @override
  State<CasesScreen> createState() => _CasesScreenState();
}

class _CasesScreenState extends State<CasesScreen> {
  late final PollingScheduler _scheduler = PollingScheduler(
    interval: casesPollInterval,
    tick: _poll,
  );

  final TextEditingController _query = TextEditingController();
  String? _selectedCaseId;

  List<CaseQueueItem> _cases = const [];
  CaseQueueStrip? _strip;
  bool _loaded = false;
  bool _failed = false;
  DateTime? _lastSync;

  @override
  void initState() {
    super.initState();
    _selectedCaseId = widget.initialCaseId;
    if (widget.initialCaseId != null) {
      // A deep-linked case opens on arrival: on a phone that means pushing
      // the detail sheet, not just selecting behind the list.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        if (MediaQuery.sizeOf(context).width < _detailBreakpoint) {
          _openCase(widget.initialCaseId!);
        }
      });
    }
    _scheduler.start();
  }

  @override
  void dispose() {
    _scheduler.dispose();
    _query.dispose();
    super.dispose();
  }

  Future<void> _poll(bool silent) async {
    try {
      final query = _query.text.trim();
      final res = await widget.client.v1.getCasesApi().getApiV1Cases(
            query: query.isEmpty ? null : query,
            limit: 200,
          );
      if (!mounted) return;
      setState(() {
        _cases = res.data?.cases.toList() ?? const [];
        _strip = res.data?.strip;
        _loaded = true;
        _failed = false;
        _lastSync = DateTime.now().toUtc();
      });
    } on Exception {
      if (!mounted) return;
      setState(() {
        _failed = true;
        _loaded = true;
      });
      // Let the scheduler see the failure — it owns the backoff curve.
      rethrow;
    }
  }

  void _reload() => _scheduler.refresh();

  void _openCase(String caseId) {
    setState(() => _selectedCaseId = caseId);
    final wide = MediaQuery.sizeOf(context).width >= _detailBreakpoint;
    if (!wide) {
      // Phones: the detail is its own sheet over the list.
      Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (context) => _DetailSheet(
          client: widget.client,
          fuse: widget.fuse,
          caseId: caseId,
          onChanged: _reload,
        ),
      ));
    }
  }

  static const _detailBreakpoint = 600;

  @override
  Widget build(BuildContext context) {
    if (!_loaded) return _loading(context);
    if (_failed && _cases.isEmpty) return _errorPane(context);
    final wide = MediaQuery.sizeOf(context).width >= _detailBreakpoint;
    final selected = _selectedCaseId;
    final list = RefreshIndicator(
      onRefresh: () async => _reload(),
      child: ListView(
        key: const Key('cases-list'),
        padding: const EdgeInsets.all(16),
        children: [
          if (_failed) _staleBanner(context),
          _stripRow(context),
          const SizedBox(height: 12),
          _searchField(context),
          const SizedBox(height: 8),
          if (_cases.isEmpty) _empty(context) else ..._cases.map(_row),
        ],
      ),
    );
    if (!wide) return list;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(width: 380, child: list),
        const VerticalDivider(width: 1, thickness: 1),
        Expanded(
          key: const Key('cases-detail-pane'),
          child: selected == null
              ? _noSelection(context)
              : CaseDetailPane(
                  key: ValueKey(selected),
                  client: widget.client,
                  fuse: widget.fuse,
                  caseId: selected,
                  onChanged: _reload,
                ),
        ),
      ],
    );
  }

  Widget _noSelection(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Select a case',
              style: VigilTypography.bodyStrong
                  .copyWith(color: context.vigilColors.tx0),
            ),
            const SizedBox(height: 6),
            Text(
              'Pick a case from the queue to read its evidence trail.',
              style:
                  VigilTypography.meta.copyWith(color: context.vigilColors.tx2),
            ),
          ],
        ),
      );

  Widget _staleBanner(BuildContext context) {
    final colors = context.vigilColors;
    return Container(
      key: const Key('cases-stale'),
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: colors.poorBg,
        borderRadius:
            BorderRadius.circular(context.vigilMetrics.radiusCardInner),
      ),
      child: Text(
        'Could not reach the server — showing data from '
        '${_lastSync == null ? 'an unknown time' : fmtAge(DateTime.now().toUtc().difference(_lastSync!))}.'
        ' Retrying with backoff.',
        style: VigilTypography.meta.copyWith(color: colors.poor),
      ),
    );
  }

  Widget _loading(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 12),
            Text('Loading cases…',
                style: VigilTypography.meta
                    .copyWith(color: context.vigilColors.tx2)),
          ],
        ),
      );

  Widget _errorPane(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Cases could not be loaded',
              style: VigilTypography.bodyStrong
                  .copyWith(color: context.vigilColors.tx0),
            ),
            const SizedBox(height: 6),
            Text(
              'The server did not answer. Retrying with backoff.',
              style: VigilTypography.meta
                  .copyWith(color: context.vigilColors.tx2),
            ),
            const SizedBox(height: 16),
            FilledButton.tonal(
              key: const Key('cases-retry'),
              onPressed: _reload,
              child: const Text('Retry'),
            ),
          ],
        ),
      );

  Widget _stripRow(BuildContext context) {
    final colors = context.vigilColors;
    final strip = _strip;
    final tiles = <(String, String)>[
      ('Needs you', '${strip?.needsYou ?? 0}'),
      ('Closed today', '${strip?.closedToday ?? 0}'),
      ('SLA at risk', '${strip?.slaAtRisk ?? 0}'),
    ];
    return Row(
      key: const Key('cases-strip'),
      children: [
        for (final (label, value) in tiles)
          Expanded(
            child: Container(
              margin: const EdgeInsets.only(right: 8),
              padding:
                  const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: colors.bg1,
                borderRadius: BorderRadius.circular(
                    context.vigilMetrics.radiusCardInner),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(value,
                      style: VigilTypography.sectionTitle.copyWith(
                        color: label == 'Needs you' && (strip?.needsYou ?? 0) > 0
                            ? colors.poor
                            : colors.tx0,
                        fontSize: 15,
                      )),
                  const SizedBox(height: 2),
                  Text(label,
                      style:
                          VigilTypography.meta.copyWith(color: colors.tx2)),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _searchField(BuildContext context) {
    final colors = context.vigilColors;
    return TextField(
      key: const Key('cases-search'),
      controller: _query,
      style: VigilTypography.body.copyWith(color: colors.tx0),
      decoration: InputDecoration(
        isDense: true,
        hintText: 'Search cases',
        hintStyle: VigilTypography.meta.copyWith(color: colors.tx3),
        prefixIcon: const Icon(Icons.search, size: 18),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(context.vigilMetrics.radiusButton),
        ),
      ),
      onSubmitted: (_) => _reload(),
    );
  }

  Widget _empty(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 40),
        child: Column(
          children: [
            Text(
              'No cases match',
              style: VigilTypography.bodyStrong
                  .copyWith(color: context.vigilColors.tx0),
            ),
            const SizedBox(height: 6),
            Text(
              'Clear the search, or wait for the next poll.',
              style: VigilTypography.meta
                  .copyWith(color: context.vigilColors.tx2),
            ),
          ],
        ),
      );

  Widget _row(CaseQueueItem item) {
    final colors = context.vigilColors;
    final selected = item.caseId == _selectedCaseId;
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Material(
        key: Key('case-row-${item.caseId}'),
        color: selected ? colors.bg3 : colors.bg1,
        borderRadius:
            BorderRadius.circular(context.vigilMetrics.radiusCardInner),
        child: InkWell(
          borderRadius:
              BorderRadius.circular(context.vigilMetrics.radiusCardInner),
          onTap: () => _openCase(item.caseId),
          child: Padding(
            padding:
                const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Row(
              children: [
                StatePill(state: item.combinedState, needs: item.needsYou ?? false),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: VigilTypography.bodyStrong
                            .copyWith(color: colors.tx0),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        [
                          if (item.priority != null &&
                              item.priority!.isNotEmpty)
                            item.priority!,
                          if (item.findingsCount != null)
                            '${item.findingsCount} finding${item.findingsCount == 1 ? '' : 's'}',
                          if (item.assignee != null &&
                              item.assignee!.isNotEmpty)
                            item.assignee!,
                          fmtAge(Duration(seconds: item.ageSeconds.toInt())),
                          if ((item.slaSecondsLeft ?? 0) > 0)
                            'SLA ${fmtDuration(Duration(seconds: item.slaSecondsLeft!.toInt()))}',
                        ].join(' · '),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: VigilTypography.meta
                            .copyWith(color: colors.tx2),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The phone-side detail sheet: a full-height page over the list with a
/// back button — the list stays mounted beneath it.
class _DetailSheet extends StatelessWidget {
  const _DetailSheet({
    required this.client,
    required this.fuse,
    required this.caseId,
    required this.onChanged,
  });

  final VigilClient client;
  final FuseController fuse;
  final String caseId;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: context.vigilColors.bg0,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: const Text('Case', style: VigilTypography.sectionTitle),
      ),
      body: CaseDetailPane(
        client: client,
        fuse: fuse,
        caseId: caseId,
        onChanged: onChanged,
      ),
    );
  }
}
