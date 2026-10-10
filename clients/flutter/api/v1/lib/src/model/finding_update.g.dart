// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'finding_update.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$FindingUpdate extends FindingUpdate {
  @override
  final num? anomalyScore;
  @override
  final String? clusterId;
  @override
  final BuiltMap<String, JsonObject?>? entityContext;
  @override
  final BuiltList<String>? evidenceLinks;
  @override
  final BuiltMap<String, num>? mitrePredictions;
  @override
  final BuiltList<BuiltMap<String, JsonObject?>>? predictedTechniques;
  @override
  final String? severity;
  @override
  final String? status;

  factory _$FindingUpdate([void Function(FindingUpdateBuilder)? updates]) =>
      (FindingUpdateBuilder()..update(updates))._build();

  _$FindingUpdate._(
      {this.anomalyScore,
      this.clusterId,
      this.entityContext,
      this.evidenceLinks,
      this.mitrePredictions,
      this.predictedTechniques,
      this.severity,
      this.status})
      : super._();
  @override
  FindingUpdate rebuild(void Function(FindingUpdateBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  FindingUpdateBuilder toBuilder() => FindingUpdateBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is FindingUpdate &&
        anomalyScore == other.anomalyScore &&
        clusterId == other.clusterId &&
        entityContext == other.entityContext &&
        evidenceLinks == other.evidenceLinks &&
        mitrePredictions == other.mitrePredictions &&
        predictedTechniques == other.predictedTechniques &&
        severity == other.severity &&
        status == other.status;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, anomalyScore.hashCode);
    _$hash = $jc(_$hash, clusterId.hashCode);
    _$hash = $jc(_$hash, entityContext.hashCode);
    _$hash = $jc(_$hash, evidenceLinks.hashCode);
    _$hash = $jc(_$hash, mitrePredictions.hashCode);
    _$hash = $jc(_$hash, predictedTechniques.hashCode);
    _$hash = $jc(_$hash, severity.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'FindingUpdate')
          ..add('anomalyScore', anomalyScore)
          ..add('clusterId', clusterId)
          ..add('entityContext', entityContext)
          ..add('evidenceLinks', evidenceLinks)
          ..add('mitrePredictions', mitrePredictions)
          ..add('predictedTechniques', predictedTechniques)
          ..add('severity', severity)
          ..add('status', status))
        .toString();
  }
}

class FindingUpdateBuilder
    implements Builder<FindingUpdate, FindingUpdateBuilder> {
  _$FindingUpdate? _$v;

  num? _anomalyScore;
  num? get anomalyScore => _$this._anomalyScore;
  set anomalyScore(num? anomalyScore) => _$this._anomalyScore = anomalyScore;

  String? _clusterId;
  String? get clusterId => _$this._clusterId;
  set clusterId(String? clusterId) => _$this._clusterId = clusterId;

  MapBuilder<String, JsonObject?>? _entityContext;
  MapBuilder<String, JsonObject?> get entityContext =>
      _$this._entityContext ??= MapBuilder<String, JsonObject?>();
  set entityContext(MapBuilder<String, JsonObject?>? entityContext) =>
      _$this._entityContext = entityContext;

  ListBuilder<String>? _evidenceLinks;
  ListBuilder<String> get evidenceLinks =>
      _$this._evidenceLinks ??= ListBuilder<String>();
  set evidenceLinks(ListBuilder<String>? evidenceLinks) =>
      _$this._evidenceLinks = evidenceLinks;

  MapBuilder<String, num>? _mitrePredictions;
  MapBuilder<String, num> get mitrePredictions =>
      _$this._mitrePredictions ??= MapBuilder<String, num>();
  set mitrePredictions(MapBuilder<String, num>? mitrePredictions) =>
      _$this._mitrePredictions = mitrePredictions;

  ListBuilder<BuiltMap<String, JsonObject?>>? _predictedTechniques;
  ListBuilder<BuiltMap<String, JsonObject?>> get predictedTechniques =>
      _$this._predictedTechniques ??=
          ListBuilder<BuiltMap<String, JsonObject?>>();
  set predictedTechniques(
          ListBuilder<BuiltMap<String, JsonObject?>>? predictedTechniques) =>
      _$this._predictedTechniques = predictedTechniques;

  String? _severity;
  String? get severity => _$this._severity;
  set severity(String? severity) => _$this._severity = severity;

  String? _status;
  String? get status => _$this._status;
  set status(String? status) => _$this._status = status;

  FindingUpdateBuilder() {
    FindingUpdate._defaults(this);
  }

  FindingUpdateBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _anomalyScore = $v.anomalyScore;
      _clusterId = $v.clusterId;
      _entityContext = $v.entityContext?.toBuilder();
      _evidenceLinks = $v.evidenceLinks?.toBuilder();
      _mitrePredictions = $v.mitrePredictions?.toBuilder();
      _predictedTechniques = $v.predictedTechniques?.toBuilder();
      _severity = $v.severity;
      _status = $v.status;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(FindingUpdate other) {
    _$v = other as _$FindingUpdate;
  }

  @override
  void update(void Function(FindingUpdateBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  FindingUpdate build() => _build();

  _$FindingUpdate _build() {
    _$FindingUpdate _$result;
    try {
      _$result = _$v ??
          _$FindingUpdate._(
            anomalyScore: anomalyScore,
            clusterId: clusterId,
            entityContext: _entityContext?.build(),
            evidenceLinks: _evidenceLinks?.build(),
            mitrePredictions: _mitrePredictions?.build(),
            predictedTechniques: _predictedTechniques?.build(),
            severity: severity,
            status: status,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'entityContext';
        _entityContext?.build();
        _$failedField = 'evidenceLinks';
        _evidenceLinks?.build();
        _$failedField = 'mitrePredictions';
        _mitrePredictions?.build();
        _$failedField = 'predictedTechniques';
        _predictedTechniques?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'FindingUpdate', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
