import 'package:dio/dio.dart';

/// One row of the ATT&CK technique rollup (`occurrence_rollup`).
class AttackTechniqueRow {
  const AttackTechniqueRow({
    required this.techniqueId,
    required this.count,
    required this.severities,
    this.techniqueName,
    this.tactic,
  });

  factory AttackTechniqueRow.fromBody(Map<String, dynamic> body) =>
      AttackTechniqueRow(
        techniqueId: body['technique_id'] as String? ?? '',
        techniqueName: body['technique_name'] as String?,
        tactic: body['tactic'] as String?,
        count: (body['count'] as num?)?.toInt() ?? 0,
        severities: {
          for (final entry
              in (body['severities'] as Map<String, dynamic>? ?? {}).entries)
            entry.key: (entry.value as num?)?.toInt() ?? 0,
        },
      );

  /// MITRE technique id, e.g. `T1486` (resolved names beat raw ids
  /// server-side — `resolve_mitre_id`).
  final String techniqueId;

  /// Optional display name; falls back to [techniqueId] in the UI.
  final String? techniqueName;
  final String? tactic;
  final int count;

  /// Occurrences by severity: `critical`/`high`/`medium`/`low` (and
  /// `unknown` when a finding carried no severity).
  final Map<String, int> severities;

  String get displayName =>
      (techniqueName == null || techniqueName!.isEmpty)
          ? techniqueId
          : techniqueName!;
}

/// GET `/api/attack/techniques/rollup` — occurrences per ATT&CK technique
/// across the (analyst-excluded-hidden) findings queue.
///
/// Hand-written against `core/threat_intel/attack_router.py`: the rollup
/// sits on the console surface (bare `/api`), outside the frozen `/api/v1`
/// snapshot, so it is typed by hand and covered by unit tests instead of
/// codegen — the same accepted exception as [ConfigApi]. The Dio passed in
/// is the app's *authenticated* instance; bearer injection, the byte-stable
/// User-Agent, and one-shot refresh-then-replay ride on the shared
/// [VigilAuthenticator].
class AttackApi {
  AttackApi({required Dio dio}) : _dio = dio;

  final Dio _dio;

  /// [timeRange] — `24h` | `7d` | `30d` | `all` (the console's dashboard
  /// default). [minConfidence] filters predictions below a confidence
  /// floor; [runId] switches the endpoint into per-run coverage mode,
  /// which this client does not use.
  Future<AttackRollup> rollup({
    String timeRange = 'all',
    double minConfidence = 0.0,
    String? runId,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/api/attack/techniques/rollup',
      queryParameters: {
        'min_confidence': minConfidence,
        'time_range': timeRange,
        if (runId != null) 'run_id': runId,
      },
    );
    return AttackRollup.fromBody(res.data ?? const {});
  }
}

class AttackRollup {
  const AttackRollup({required this.totalTechniques, required this.techniques});

  factory AttackRollup.fromBody(Map<String, dynamic> body) {
    final rows = body['techniques'];
    return AttackRollup(
      totalTechniques: (body['total_techniques'] as num?)?.toInt() ?? 0,
      techniques: [
        if (rows is List)
          for (final row in rows)
            if (row is Map<String, dynamic>) AttackTechniqueRow.fromBody(row),
      ],
    );
  }

  final int totalTechniques;

  /// Sorted by count descending (the server sorts; the client keeps order).
  final List<AttackTechniqueRow> techniques;
}
