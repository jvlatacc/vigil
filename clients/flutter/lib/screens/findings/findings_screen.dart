import 'package:flutter/material.dart';
import 'package:vigil_api_v1/vigil_api_v1.dart';

import '../../api/attack_api.dart';
import '../../api/vigil_client.dart';
import '../../data/polling_scheduler.dart';
import '../../theme/extensions.dart';
import '../../theme/vigil_typography.dart';
import '../shared/severity_chip.dart';
import '../shared/vigil_time.dart';

/// The console's 10 s findings cadence (`useFindings.ts:44`).
const findingsPollInterval = Duration(seconds: 10);

/// Findings / Dashboard — the read queue with severity chips, the stats
/// summary from `GET /api/v1/findings/stats/summary`, and the ATT&CK
/// technique rollup. Console: `screens/dashboard/` (findings table +
/// ATT&CK panel); polling parity 10 s with silent background ticks.
class FindingsScreen extends StatefulWidget {
  const FindingsScreen({super.key, required this.client});

  final VigilClient client;

  @override
  State<FindingsScreen> createState() => _FindingsScreenState();
}

class _FindingsScreenState extends State<FindingsScreen> {
  late final PollingScheduler _scheduler = PollingScheduler(
    interval: findingsPollInterval,
    tick: _poll,
  );

  final TextEditingController _search = TextEditingController();
  String? _severity;

  List<FindingRecord> _findings = const [];
  FindingsSummaryResponse? _summary;
  AttackRollup? _rollup;
  int _total = 0;
  int _ticks = 0;
  bool _loaded = false;
  bool _failed = false;
  DateTime? _lastSync;

  @override
  void initState() {
    super.initState();
    _scheduler.start();
  }

  @override
  void dispose() {
    _scheduler.dispose();
    _search.dispose();
    super.dispose();
  }

  Future<void> _poll(bool silent) async {
    try {
      final search = _search.text.trim();
      final findings = await widget.client.v1.getFindingsApi().getApiV1Findings(
            severity: _severity,
            search: search.isEmpty ? null : search,
            limit: 200,
          );
      final summary =
          await widget.client.v1.getFindingsApi().getApiV1FindingsStatsSummary();
      // The rollup is the heaviest read of the three — refresh it on the
      // first load, on manual refresh, and roughly once a minute after.
      final slowTick = _ticks % 6 == 0;
      _ticks += 1;
      final rollup = slowTick ? await widget.client.attack.rollup() : null;
      if (!mounted) return;
      setState(() {
        _findings = findings.data?.findings?.toList() ?? const [];
        _total = findings.data?.total ?? _findings.length;
        _summary = summary.data;
        if (rollup != null) _rollup = rollup;
        _loaded = true;
        _failed = false;
        _lastSync = DateTime.now().toUtc();
      });
    } on Exception {
      if (!mounted) return;
      // The poll scheduler backs off; keep the last good data up with its
      // age label (the console's stale-data rule).
      setState(() {
        _failed = true;
        _loaded = true;
      });
      // Let the scheduler see the failure — it owns the backoff curve.
      rethrow;
    }
  }

  void _reload() => _scheduler.refresh();

  @override
  Widget build(BuildContext context) {
    if (!_loaded) return _loading(context);
    if (_failed && _findings.isEmpty) return _errorPane(context);
    return RefreshIndicator(
      onRefresh: () async => _reload(),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_failed) _staleBanner(context),
          _statsStrip(context),
          const SizedBox(height: 12),
          _attackPanel(context),
          const SizedBox(height: 12),
          _filters(context),
          const SizedBox(height: 8),
          if (_findings.isEmpty)
            _empty(context)
          else
            ..._findings.take(100).map(_row),
          if (_total > 100)
            Padding(
              padding: const EdgeInsets.only(top: 8, bottom: 24),
              child: Text(
                'Showing 100 of $_total — refine the filters to narrow the '
                'queue.',
                style: VigilTypography.meta.copyWith(
                  color: context.vigilColors.tx2,
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _staleBanner(BuildContext context) {
    final colors = context.vigilColors;
    return Container(
      key: const Key('findings-stale'),
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
            Text('Loading findings…',
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
              'Findings could not be loaded',
              style: VigilTypography.bodyStrong
                  .copyWith(color: context.vigilColors.tx0),
            ),
            const SizedBox(height: 6),
            Text(
              'The server did not answer. Retrying with backoff.',
              style:
                  VigilTypography.meta.copyWith(color: context.vigilColors.tx2),
            ),
            const SizedBox(height: 16),
            FilledButton.tonal(
              key: const Key('findings-retry'),
              onPressed: _reload,
              child: const Text('Retry'),
            ),
          ],
        ),
      );

  Widget _statsStrip(BuildContext context) {
    final colors = context.vigilColors;
    final bySeverity = _summary?.bySeverity;
    final tiles = <(String, String, Color)>[
      ('Total', '${_summary?.total ?? _total}', colors.tx0),
      ('Critical', '${bySeverity?['critical'] ?? 0}', colors.sevCrit),
      ('High', '${bySeverity?['high'] ?? 0}', colors.sevHigh),
      ('Medium', '${bySeverity?['medium'] ?? 0}', colors.sevMed),
      ('Low', '${bySeverity?['low'] ?? 0}', colors.sevLow),
    ];
    return Row(
      key: const Key('findings-stats'),
      children: [
        for (final (label, value, color) in tiles)
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
                        color: color,
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

  Widget _attackPanel(BuildContext context) {
    final colors = context.vigilColors;
    final rollup = _rollup;
    return Container(
      key: const Key('findings-attack'),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colors.bg1,
        borderRadius:
            BorderRadius.circular(context.vigilMetrics.radiusCard),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('ATT&CK techniques in the queue',
              style: VigilTypography.label.copyWith(color: colors.tx0)),
          const SizedBox(height: 8),
          if (rollup == null)
            Text('Loading rollup…',
                style: VigilTypography.meta.copyWith(color: colors.tx2))
          else if (rollup.techniques.isEmpty)
            Text('No techniques predicted on the current queue.',
                style: VigilTypography.meta.copyWith(color: colors.tx2))
          else
            for (final technique in rollup.techniques.take(8))
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        '${technique.techniqueId} — ${technique.displayName}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style:
                            VigilTypography.body.copyWith(color: colors.tx1),
                      ),
                    ),
                    for (final severity
                        in const ['critical', 'high', 'medium', 'low'])
                      if ((technique.severities[severity] ?? 0) > 0)
                        Padding(
                          padding: const EdgeInsets.only(left: 4),
                          child: SeverityChip(
                              severity: severity, dotOnly: true),
                        ),
                    const SizedBox(width: 8),
                    Text('${technique.count}',
                        style: VigilTypography.label
                            .copyWith(color: colors.tx0)),
                  ],
                ),
              ),
        ],
      ),
    );
  }

  Widget _filters(BuildContext context) {
    final colors = context.vigilColors;
    return Wrap(
      spacing: 4,
      runSpacing: 4,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 220,
          child: TextField(
            key: const Key('findings-search'),
            controller: _search,
            style: VigilTypography.body.copyWith(color: colors.tx0),
            decoration: InputDecoration(
              isDense: true,
              hintText: 'Search findings',
              hintStyle: VigilTypography.meta.copyWith(color: colors.tx3),
              prefixIcon: const Icon(Icons.search, size: 18),
              border: OutlineInputBorder(
                borderRadius:
                    BorderRadius.circular(context.vigilMetrics.radiusButton),
              ),
            ),
            onSubmitted: (_) => _reload(),
          ),
        ),
        for (final severity
            in const [null, 'critical', 'high', 'medium', 'low'])
          _severityFilter(context, severity),
      ],
    );
  }

  Widget _severityFilter(BuildContext context, String? severity) {
    final colors = context.vigilColors;
    final selected = _severity == severity;
    return FilterChip(
      key: Key('findings-sev-${severity ?? 'all'}'),
      label: Text(switch (severity) {
        null => 'All',
        final s => s[0].toUpperCase() + s.substring(1),
      }),
      selected: selected,
      onSelected: (_) {
        setState(() => _severity = selected ? null : severity);
        _reload();
      },
      labelStyle: VigilTypography.meta.copyWith(
        color: selected ? colors.acTx : colors.tx1,
      ),
      checkmarkColor: colors.acTx,
      selectedColor: colors.acBg,
      showCheckmark: false,
      visualDensity: VisualDensity.compact,
    );
  }

  Widget _empty(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 40),
        child: Column(
          children: [
            Text(
              'No findings match',
              style: VigilTypography.bodyStrong
                  .copyWith(color: context.vigilColors.tx0),
            ),
            const SizedBox(height: 6),
            Text(
              'Widen the filters, or wait for the next 10 s poll.',
              style: VigilTypography.meta
                  .copyWith(color: context.vigilColors.tx2),
            ),
          ],
        ),
      );

  Widget _row(FindingRecord finding) {
    final colors = context.vigilColors;
    final ts = parseUtc(finding.timestamp);
    return Container(
      key: Key('finding-${finding.findingId ?? ''}'),
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: colors.bg1,
        borderRadius:
            BorderRadius.circular(context.vigilMetrics.radiusCardInner),
      ),
      child: Row(
        children: [
          SeverityChip(severity: finding.severity),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  finding.title ?? 'Untitled finding',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style:
                      VigilTypography.bodyStrong.copyWith(color: colors.tx0),
                ),
                const SizedBox(height: 2),
                Text(
                  [
                    if (finding.dataSource != null &&
                        finding.dataSource!.isNotEmpty)
                      finding.dataSource!,
                    if (finding.status != null && finding.status!.isNotEmpty)
                      finding.status!,
                    if (ts != null) fmtUtc(ts),
                  ].join(' · '),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: VigilTypography.meta.copyWith(color: colors.tx2),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
