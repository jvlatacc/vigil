// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_metrics_summary_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseMetricsSummaryResponse extends CaseMetricsSummaryResponse {
  @override
  final int criticalCases;
  @override
  final int openCases;
  @override
  final BuiltMap<String, int>? priorityBreakdown;
  @override
  final int resolvedCases;
  @override
  final BuiltMap<String, int>? statusBreakdown;
  @override
  final int totalCases;

  factory _$CaseMetricsSummaryResponse(
          [void Function(CaseMetricsSummaryResponseBuilder)? updates]) =>
      (CaseMetricsSummaryResponseBuilder()..update(updates))._build();

  _$CaseMetricsSummaryResponse._(
      {required this.criticalCases,
      required this.openCases,
      this.priorityBreakdown,
      required this.resolvedCases,
      this.statusBreakdown,
      required this.totalCases})
      : super._();
  @override
  CaseMetricsSummaryResponse rebuild(
          void Function(CaseMetricsSummaryResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseMetricsSummaryResponseBuilder toBuilder() =>
      CaseMetricsSummaryResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseMetricsSummaryResponse &&
        criticalCases == other.criticalCases &&
        openCases == other.openCases &&
        priorityBreakdown == other.priorityBreakdown &&
        resolvedCases == other.resolvedCases &&
        statusBreakdown == other.statusBreakdown &&
        totalCases == other.totalCases;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, criticalCases.hashCode);
    _$hash = $jc(_$hash, openCases.hashCode);
    _$hash = $jc(_$hash, priorityBreakdown.hashCode);
    _$hash = $jc(_$hash, resolvedCases.hashCode);
    _$hash = $jc(_$hash, statusBreakdown.hashCode);
    _$hash = $jc(_$hash, totalCases.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseMetricsSummaryResponse')
          ..add('criticalCases', criticalCases)
          ..add('openCases', openCases)
          ..add('priorityBreakdown', priorityBreakdown)
          ..add('resolvedCases', resolvedCases)
          ..add('statusBreakdown', statusBreakdown)
          ..add('totalCases', totalCases))
        .toString();
  }
}

class CaseMetricsSummaryResponseBuilder
    implements
        Builder<CaseMetricsSummaryResponse, CaseMetricsSummaryResponseBuilder> {
  _$CaseMetricsSummaryResponse? _$v;

  int? _criticalCases;
  int? get criticalCases => _$this._criticalCases;
  set criticalCases(int? criticalCases) =>
      _$this._criticalCases = criticalCases;

  int? _openCases;
  int? get openCases => _$this._openCases;
  set openCases(int? openCases) => _$this._openCases = openCases;

  MapBuilder<String, int>? _priorityBreakdown;
  MapBuilder<String, int> get priorityBreakdown =>
      _$this._priorityBreakdown ??= MapBuilder<String, int>();
  set priorityBreakdown(MapBuilder<String, int>? priorityBreakdown) =>
      _$this._priorityBreakdown = priorityBreakdown;

  int? _resolvedCases;
  int? get resolvedCases => _$this._resolvedCases;
  set resolvedCases(int? resolvedCases) =>
      _$this._resolvedCases = resolvedCases;

  MapBuilder<String, int>? _statusBreakdown;
  MapBuilder<String, int> get statusBreakdown =>
      _$this._statusBreakdown ??= MapBuilder<String, int>();
  set statusBreakdown(MapBuilder<String, int>? statusBreakdown) =>
      _$this._statusBreakdown = statusBreakdown;

  int? _totalCases;
  int? get totalCases => _$this._totalCases;
  set totalCases(int? totalCases) => _$this._totalCases = totalCases;

  CaseMetricsSummaryResponseBuilder() {
    CaseMetricsSummaryResponse._defaults(this);
  }

  CaseMetricsSummaryResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _criticalCases = $v.criticalCases;
      _openCases = $v.openCases;
      _priorityBreakdown = $v.priorityBreakdown?.toBuilder();
      _resolvedCases = $v.resolvedCases;
      _statusBreakdown = $v.statusBreakdown?.toBuilder();
      _totalCases = $v.totalCases;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseMetricsSummaryResponse other) {
    _$v = other as _$CaseMetricsSummaryResponse;
  }

  @override
  void update(void Function(CaseMetricsSummaryResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseMetricsSummaryResponse build() => _build();

  _$CaseMetricsSummaryResponse _build() {
    _$CaseMetricsSummaryResponse _$result;
    try {
      _$result = _$v ??
          _$CaseMetricsSummaryResponse._(
            criticalCases: BuiltValueNullFieldError.checkNotNull(
                criticalCases, r'CaseMetricsSummaryResponse', 'criticalCases'),
            openCases: BuiltValueNullFieldError.checkNotNull(
                openCases, r'CaseMetricsSummaryResponse', 'openCases'),
            priorityBreakdown: _priorityBreakdown?.build(),
            resolvedCases: BuiltValueNullFieldError.checkNotNull(
                resolvedCases, r'CaseMetricsSummaryResponse', 'resolvedCases'),
            statusBreakdown: _statusBreakdown?.build(),
            totalCases: BuiltValueNullFieldError.checkNotNull(
                totalCases, r'CaseMetricsSummaryResponse', 'totalCases'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'priorityBreakdown';
        _priorityBreakdown?.build();

        _$failedField = 'statusBreakdown';
        _statusBreakdown?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseMetricsSummaryResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
