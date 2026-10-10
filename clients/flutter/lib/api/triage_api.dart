import 'package:dio/dio.dart';

/// One row of the triage queue (`triage_read._present`) — what intake did
/// with what arrived.
class TriageRow {
  const TriageRow({
    required this.id,
    required this.kind,
    required this.kindLabel,
    required this.state,
    required this.stateLabel,
    required this.source,
    required this.severityBand,
    required this.ageSeconds,
    required this.ttlSeconds,
    required this.lastQuarter,
    required this.workflowId,
    this.score,
    this.pickupSeconds,
    this.caseDoor,
    this.document,
    this.description,
    this.findingId,
    this.createdAt,
  });

  factory TriageRow.fromBody(Map<String, dynamic> body) => TriageRow(
        id: (body['id'] as num?)?.toInt() ?? 0,
        kind: body['kind'] as String? ?? '',
        kindLabel:
            body['kind_label'] as String? ?? body['kind'] as String? ?? '',
        state: body['state'] as String? ?? '',
        stateLabel: body['state_label'] as String? ?? '',
        source: body['source'] as String? ?? '',
        severityBand: body['severity_band'] as String? ?? 'unknown',
        ageSeconds: (body['age_seconds'] as num?)?.toInt() ?? 0,
        ttlSeconds: (body['ttl_seconds'] as num?)?.toInt() ?? 0,
        lastQuarter: body['last_quarter'] == true,
        workflowId: body['workflow_id'] as String? ?? '',
        // The server reports `score` as null today ("Not measured yet") —
        // the field is carried so a measured score lights up later.
        score: (body['score'] as num?)?.toDouble(),
        pickupSeconds: (body['pickup_seconds'] as num?)?.toDouble(),
        caseDoor: body['case_door'] as String?,
        document: body['document'] as String?,
        description: body['description'] as String?,
        findingId: body['finding_id'] as String?,
        createdAt: body['created_at'] as String?,
      );

  final int id;

  /// `detection` | `schedule` | `human_ask` (raw); [kindLabel] is the
  /// console's display word: Alert / Schedule / Ask.
  final String kind;
  final String kindLabel;

  /// `queued` | `launched` | `merged` | `expired` (raw); [stateLabel] is
  /// the display word ("Waiting for a slot", "Started a case", …).
  final String state;
  final String stateLabel;
  final String source;

  /// The ranked band: `critical` | `high` | `medium` | `low` | `unknown`.
  final String severityBand;
  final int ageSeconds;
  final int ttlSeconds;

  /// True inside the last quarter of the TTL — the console's promotion
  /// window; the row's age turns "due".
  final bool lastQuarter;

  /// The workflow (play) the row ran into, when intake launched one.
  final String workflowId;

  /// Intake score, when the server measures one. Null today.
  final double? score;
  final double? pickupSeconds;

  /// Case id the row opened/merged into, when that id is still a case —
  /// the door to the case page.
  final String? caseDoor;
  final String? document;
  final String? description;
  final String? findingId;
  final String? createdAt;
}

/// Chip-filter counts over every intake row, before filters and the cap.
class TriageCounts {
  const TriageCounts({
    required this.total,
    required this.kind,
    required this.source,
    required this.state,
  });

  factory TriageCounts.fromBody(Map<String, dynamic> body) => TriageCounts(
        total: (body['total'] as num?)?.toInt() ?? 0,
        kind: _stringCounts(body['kind']),
        source: _stringCounts(body['source']),
        state: _stringCounts(body['state']),
      );

  static Map<String, int> _stringCounts(Object? raw) => {
        if (raw is Map<String, dynamic>)
          for (final entry in raw.entries)
            if (entry.value is num) entry.key: (entry.value as num).toInt(),
      };

  final int total;
  final Map<String, int> kind;
  final Map<String, int> source;
  final Map<String, int> state;
}

/// Per-source arrival counts with collection lag.
class TriageSource {
  const TriageSource({
    required this.dataSource,
    required this.arrivals,
    this.lagSeconds,
    this.quiet,
  });

  factory TriageSource.fromBody(Map<String, dynamic> body) => TriageSource(
        dataSource: body['data_source'] as String? ?? '',
        arrivals: (body['arrivals'] as num?)?.toInt() ?? 0,
        lagSeconds: (body['lag_seconds'] as num?)?.toDouble(),
        quiet: body['quiet'] as bool?,
      );

  final String dataSource;
  final int arrivals;
  final double? lagSeconds;
  final bool? quiet;
}

/// The strip figures above the queue (`_strip`).
class TriageStrip {
  const TriageStrip({
    required this.pickedUpShare,
    required this.pickedUpToday,
    required this.createdToday,
    required this.waiting,
    required this.casesCreatedToday,
    required this.trustFloor,
  });

  factory TriageStrip.fromBody(Map<String, dynamic> body) {
    final pickedUp = body['picked_up'];
    final picked = pickedUp is Map<String, dynamic> ? pickedUp : const {};
    return TriageStrip(
      pickedUpToday: (picked['launched_or_merged'] as num?)?.toInt() ?? 0,
      createdToday: (picked['created_today'] as num?)?.toInt() ?? 0,
      pickedUpShare: (picked['share'] as num?)?.toDouble(),
      waiting: (body['waiting'] as num?)?.toInt() ?? 0,
      casesCreatedToday: (body['cases_created_today'] as num?)?.toInt() ?? 0,
      trustFloor: body['trust_floor'] as String? ?? '',
    );
  }

  final int pickedUpToday;
  final int createdToday;

  /// `picked_up_today / created_today`, null when nothing arrived today.
  final double? pickedUpShare;
  final int waiting;
  final int casesCreatedToday;

  /// "Not measured yet" until the server keeps a trust score — rendered
  /// as-is, never as a number.
  final String trustFloor;
}

/// GET `/api/triage` — the intake queue read (`services/api/triage_read.py`).
///
/// Hand-written against the backend: triage is console-surface (bare
/// `/api`), outside the frozen `/api/v1` snapshot — the same accepted
/// exception as [ConfigApi]. The Dio passed in is the app's *authenticated*
/// instance; bearer injection, the byte-stable User-Agent, and one-shot
/// refresh-then-replay ride on the shared [VigilAuthenticator].
class TriageApi {
  TriageApi({required Dio dio}) : _dio = dio;

  final Dio _dio;

  /// [kind]/[state]/[source] narrow the returned rows server-side; the
  /// strip and [TriageCounts] always describe the whole table.
  Future<TriagePayload> get({
    String? kind,
    String? source,
    String? state,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/api/triage',
      queryParameters: {
        if (kind != null && kind.isNotEmpty) 'kind': kind,
        if (source != null && source.isNotEmpty) 'source': source,
        if (state != null && state.isNotEmpty) 'state': state,
      },
    );
    return TriagePayload.fromBody(res.data ?? const {});
  }
}

class TriagePayload {
  const TriagePayload({
    required this.rows,
    required this.matched,
    required this.strip,
    required this.counts,
    required this.sources,
  });

  factory TriagePayload.fromBody(Map<String, dynamic> body) {
    final rows = body['rows'];
    final sources = body['sources'];
    return TriagePayload(
      rows: [
        if (rows is List)
          for (final row in rows)
            if (row is Map<String, dynamic>) TriageRow.fromBody(row),
      ],
      matched: (body['matched'] as num?)?.toInt() ?? 0,
      strip: TriageStrip.fromBody(
        body['strip'] is Map<String, dynamic>
            ? body['strip'] as Map<String, dynamic>
            : const {},
      ),
      counts: TriageCounts.fromBody(
        body['counts'] is Map<String, dynamic>
            ? body['counts'] as Map<String, dynamic>
            : const {},
      ),
      sources: [
        if (sources is List)
          for (final source in sources)
            if (source is Map<String, dynamic>) TriageSource.fromBody(source),
      ],
    );
  }

  /// Rows that pass the filters (queued by rank first, then decided
  /// newest first), capped at the server's 200-row cap.
  final List<TriageRow> rows;

  /// How many rows pass the filters before the cap.
  final int matched;
  final TriageStrip strip;
  final TriageCounts counts;
  final List<TriageSource> sources;
}
