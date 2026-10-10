import 'package:flutter/material.dart';

import '../../api/triage_api.dart';
import '../../api/vigil_client.dart';
import '../../data/polling_scheduler.dart';
import '../../theme/extensions.dart';
import '../../theme/vigil_typography.dart';
import '../shared/severity_chip.dart';
import '../shared/vigil_time.dart';

/// The console's triage cadence (`TriageScreen.tsx` `POLL_MS = 10_000`).
const triagePollInterval = Duration(seconds: 10);

/// Triage — "What intake did with what arrived": the queue with chip
/// filters, confidence/intake scores, and doors into cases. Console:
/// `screens/triage/TriageScreen.tsx`; polling parity 10 s.
class TriageScreen extends StatefulWidget {
  const TriageScreen({super.key, required this.client, this.onOpenCase});

  final VigilClient client;

  /// The case door: a row that opened (or merged into) a case links to it,
  /// the same cross-link the console's row gives.
  final void Function(String caseId)? onOpenCase;

  @override
  State<TriageScreen> createState() => _TriageScreenState();
}

class _TriageScreenState extends State<TriageScreen> {
  late final PollingScheduler _scheduler = PollingScheduler(
    interval: triagePollInterval,
    tick: _poll,
  );

  String? _kind;
  String? _state;
  String? _source;

  List<TriageRow> _rows = const [];
  TriageCounts? _counts;
  TriageStrip? _strip;
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
    super.dispose();
  }

  Future<void> _poll(bool silent) async {
    try {
      final payload = await widget.client.triage.get(
        kind: _kind,
        state: _state,
        source: _source,
      );
      if (!mounted) return;
      setState(() {
        _rows = payload.rows;
        _counts = payload.counts;
        _strip = payload.strip;
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

  @override
  Widget build(BuildContext context) {
    if (!_loaded) return _loading(context);
    if (_failed && _rows.isEmpty) return _errorPane(context);
    return RefreshIndicator(
      onRefresh: () async => _reload(),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_failed) _staleBanner(context),
          _stripRow(context),
          const SizedBox(height: 12),
          _filters(context),
          const SizedBox(height: 8),
          if (_rows.isEmpty) _empty(context) else ..._rows.map(_row),
        ],
      ),
    );
  }

  Widget _staleBanner(BuildContext context) {
    final colors = context.vigilColors;
    return Container(
      key: const Key('triage-stale'),
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
            Text('Loading triage queue…',
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
              'Triage could not be loaded',
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
              key: const Key('triage-retry'),
              onPressed: _reload,
              child: const Text('Retry'),
            ),
          ],
        ),
      );

  Widget _stripRow(BuildContext context) {
    final colors = context.vigilColors;
    final strip = _stripOf();
    final tiles = <(String, String)>[
      (
        'Picked up today',
        strip == null
            ? '—'
            : strip.pickedUpShare == null
                ? '${strip.pickedUpToday} of ${strip.createdToday}'
                : '${(strip.pickedUpShare! * 100).toStringAsFixed(0)}% — '
                    '${strip.pickedUpToday} of ${strip.createdToday}',
      ),
      ('Waiting', '${strip?.waiting ?? 0}'),
      ('Cases created today', '${strip?.casesCreatedToday ?? 0}'),
      ('Trust floor', strip == null || strip.trustFloor.isEmpty
          ? 'Not measured yet'
          : strip.trustFloor),
    ];
    return Row(
      key: const Key('triage-strip'),
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
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: VigilTypography.sectionTitle.copyWith(
                        color: colors.tx0,
                        fontSize: 13,
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

  TriageStrip? _stripOf() => _strip;

  Widget _filters(BuildContext context) {
    final colors = context.vigilColors;
    final counts = _counts;
    return Wrap(
      spacing: 4,
      runSpacing: 4,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        Text('Kind', style: VigilTypography.meta.copyWith(color: colors.tx3)),
        for (final kind in _sortedKinds()) _kindChip(context, kind),
        const SizedBox(width: 8),
        Text('State', style: VigilTypography.meta.copyWith(color: colors.tx3)),
        for (final state in _sortedStates()) _stateChip(context, state),
        if ((_source != null)) ...[
          const SizedBox(width: 8),
          ActionChip(
            key: const Key('triage-source-clear'),
            label: Text('Source: $_source ×'),
            onPressed: () {
              setState(() => _source = null);
              _reload();
            },
            labelStyle: VigilTypography.meta.copyWith(color: colors.tx1),
            visualDensity: VisualDensity.compact,
          ),
        ],
        if (counts == null) const SizedBox.shrink(),
      ],
    );
  }

  List<String> _sortedKinds() {
    final kind = _counts?.kind ?? const {};
    final keys = kind.keys.toList()..sort();
    return keys;
  }

  List<String> _sortedStates() {
    final state = _counts?.state ?? const {};
    final keys = state.keys.toList()..sort();
    return keys;
  }

  Widget _kindChip(BuildContext context, String kind) {
    final colors = context.vigilColors;
    final selected = _kind == kind;
    final count = _counts?.kind[kind] ?? 0;
    return FilterChip(
      key: Key('triage-kind-$kind'),
      label: Text('$kind ($count)'),
      selected: selected,
      onSelected: (_) {
        setState(() => _kind = selected ? null : kind);
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

  Widget _stateChip(BuildContext context, String state) {
    final colors = context.vigilColors;
    final selected = _state == state;
    final count = _counts?.state[state] ?? 0;
    return FilterChip(
      key: Key('triage-state-$state'),
      label: Text('$state ($count)'),
      selected: selected,
      onSelected: (_) {
        setState(() => _state = selected ? null : state);
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
              'Nothing in the triage queue',
              style: VigilTypography.bodyStrong
                  .copyWith(color: context.vigilColors.tx0),
            ),
            const SizedBox(height: 6),
            Text(
              'What intake did with what arrived shows up here at the '
              '10 s cadence.',
              style: VigilTypography.meta
                  .copyWith(color: context.vigilColors.tx2),
            ),
          ],
        ),
      );

  Widget _row(TriageRow row) {
    final colors = context.vigilColors;
    final door = row.caseDoor;
    final hasDoor = door != null && door.isNotEmpty;
    return Container(
      key: Key('triage-row-${row.id}'),
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: colors.bg1,
        borderRadius:
            BorderRadius.circular(context.vigilMetrics.radiusCardInner),
      ),
      child: Row(
        children: [
          SeverityChip(severity: row.severityBand),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  [
                    row.kindLabel,
                    if (row.document != null && row.document!.isNotEmpty)
                      row.document!,
                  ].join(' — '),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style:
                      VigilTypography.bodyStrong.copyWith(color: colors.tx0),
                ),
                const SizedBox(height: 2),
                Text(
                  [
                    row.stateLabel,
                    if (row.source.isNotEmpty) row.source,
                    // The console's intake score renders "Not measured yet"
                    // until the server keeps one — never a made-up number.
                    row.score == null
                        ? 'Not measured yet'
                        : 'intake ${(row.score! * 100).toStringAsFixed(0)}%',
                    row.lastQuarter ? 'due' : fmtAge(Duration(seconds: row.ageSeconds)),
                  ].join(' · '),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: VigilTypography.meta.copyWith(
                    color: row.lastQuarter ? colors.fair : colors.tx2,
                  ),
                ),
              ],
            ),
          ),
          if (hasDoor)
            IconButton(
              key: Key('triage-door-${row.id}'),
              tooltip: 'Open case',
              icon: const Icon(Icons.open_in_new, size: 18),
              color: colors.tx2,
              onPressed: () => widget.onOpenCase?.call(door),
            ),
        ],
      ),
    );
  }
}
