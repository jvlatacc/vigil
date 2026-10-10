// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'finding_record.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$FindingRecord extends FindingRecord {
  @override
  final AnyOf? aiEnrichment;
  @override
  final num? anomalyScore;
  @override
  final String? clusterId;
  @override
  final String? createdAt;
  @override
  final String? dataSource;
  @override
  final String? description;
  @override
  final EntityContext? entityContext;
  @override
  final AnyOf? evidenceLinks;
  @override
  final BuiltList<String>? excludedIps;
  @override
  final String? externalId;
  @override
  final String? findingId;
  @override
  final AnyOf? mitrePredictions;
  @override
  final String? severity;
  @override
  final String? status;
  @override
  final String? timestamp;
  @override
  final String? title;
  @override
  final String? updatedAt;

  factory _$FindingRecord([void Function(FindingRecordBuilder)? updates]) =>
      (FindingRecordBuilder()..update(updates))._build();

  _$FindingRecord._(
      {this.aiEnrichment,
      this.anomalyScore,
      this.clusterId,
      this.createdAt,
      this.dataSource,
      this.description,
      this.entityContext,
      this.evidenceLinks,
      this.excludedIps,
      this.externalId,
      this.findingId,
      this.mitrePredictions,
      this.severity,
      this.status,
      this.timestamp,
      this.title,
      this.updatedAt})
      : super._();
  @override
  FindingRecord rebuild(void Function(FindingRecordBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  FindingRecordBuilder toBuilder() => FindingRecordBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is FindingRecord &&
        aiEnrichment == other.aiEnrichment &&
        anomalyScore == other.anomalyScore &&
        clusterId == other.clusterId &&
        createdAt == other.createdAt &&
        dataSource == other.dataSource &&
        description == other.description &&
        entityContext == other.entityContext &&
        evidenceLinks == other.evidenceLinks &&
        excludedIps == other.excludedIps &&
        externalId == other.externalId &&
        findingId == other.findingId &&
        mitrePredictions == other.mitrePredictions &&
        severity == other.severity &&
        status == other.status &&
        timestamp == other.timestamp &&
        title == other.title &&
        updatedAt == other.updatedAt;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, aiEnrichment.hashCode);
    _$hash = $jc(_$hash, anomalyScore.hashCode);
    _$hash = $jc(_$hash, clusterId.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, dataSource.hashCode);
    _$hash = $jc(_$hash, description.hashCode);
    _$hash = $jc(_$hash, entityContext.hashCode);
    _$hash = $jc(_$hash, evidenceLinks.hashCode);
    _$hash = $jc(_$hash, excludedIps.hashCode);
    _$hash = $jc(_$hash, externalId.hashCode);
    _$hash = $jc(_$hash, findingId.hashCode);
    _$hash = $jc(_$hash, mitrePredictions.hashCode);
    _$hash = $jc(_$hash, severity.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, timestamp.hashCode);
    _$hash = $jc(_$hash, title.hashCode);
    _$hash = $jc(_$hash, updatedAt.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'FindingRecord')
          ..add('aiEnrichment', aiEnrichment)
          ..add('anomalyScore', anomalyScore)
          ..add('clusterId', clusterId)
          ..add('createdAt', createdAt)
          ..add('dataSource', dataSource)
          ..add('description', description)
          ..add('entityContext', entityContext)
          ..add('evidenceLinks', evidenceLinks)
          ..add('excludedIps', excludedIps)
          ..add('externalId', externalId)
          ..add('findingId', findingId)
          ..add('mitrePredictions', mitrePredictions)
          ..add('severity', severity)
          ..add('status', status)
          ..add('timestamp', timestamp)
          ..add('title', title)
          ..add('updatedAt', updatedAt))
        .toString();
  }
}

class FindingRecordBuilder
    implements Builder<FindingRecord, FindingRecordBuilder> {
  _$FindingRecord? _$v;

  AnyOf? _aiEnrichment;
  AnyOf? get aiEnrichment => _$this._aiEnrichment;
  set aiEnrichment(AnyOf? aiEnrichment) => _$this._aiEnrichment = aiEnrichment;

  num? _anomalyScore;
  num? get anomalyScore => _$this._anomalyScore;
  set anomalyScore(num? anomalyScore) => _$this._anomalyScore = anomalyScore;

  String? _clusterId;
  String? get clusterId => _$this._clusterId;
  set clusterId(String? clusterId) => _$this._clusterId = clusterId;

  String? _createdAt;
  String? get createdAt => _$this._createdAt;
  set createdAt(String? createdAt) => _$this._createdAt = createdAt;

  String? _dataSource;
  String? get dataSource => _$this._dataSource;
  set dataSource(String? dataSource) => _$this._dataSource = dataSource;

  String? _description;
  String? get description => _$this._description;
  set description(String? description) => _$this._description = description;

  EntityContextBuilder? _entityContext;
  EntityContextBuilder get entityContext =>
      _$this._entityContext ??= EntityContextBuilder();
  set entityContext(EntityContextBuilder? entityContext) =>
      _$this._entityContext = entityContext;

  AnyOf? _evidenceLinks;
  AnyOf? get evidenceLinks => _$this._evidenceLinks;
  set evidenceLinks(AnyOf? evidenceLinks) =>
      _$this._evidenceLinks = evidenceLinks;

  ListBuilder<String>? _excludedIps;
  ListBuilder<String> get excludedIps =>
      _$this._excludedIps ??= ListBuilder<String>();
  set excludedIps(ListBuilder<String>? excludedIps) =>
      _$this._excludedIps = excludedIps;

  String? _externalId;
  String? get externalId => _$this._externalId;
  set externalId(String? externalId) => _$this._externalId = externalId;

  String? _findingId;
  String? get findingId => _$this._findingId;
  set findingId(String? findingId) => _$this._findingId = findingId;

  AnyOf? _mitrePredictions;
  AnyOf? get mitrePredictions => _$this._mitrePredictions;
  set mitrePredictions(AnyOf? mitrePredictions) =>
      _$this._mitrePredictions = mitrePredictions;

  String? _severity;
  String? get severity => _$this._severity;
  set severity(String? severity) => _$this._severity = severity;

  String? _status;
  String? get status => _$this._status;
  set status(String? status) => _$this._status = status;

  String? _timestamp;
  String? get timestamp => _$this._timestamp;
  set timestamp(String? timestamp) => _$this._timestamp = timestamp;

  String? _title;
  String? get title => _$this._title;
  set title(String? title) => _$this._title = title;

  String? _updatedAt;
  String? get updatedAt => _$this._updatedAt;
  set updatedAt(String? updatedAt) => _$this._updatedAt = updatedAt;

  FindingRecordBuilder() {
    FindingRecord._defaults(this);
  }

  FindingRecordBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _aiEnrichment = $v.aiEnrichment;
      _anomalyScore = $v.anomalyScore;
      _clusterId = $v.clusterId;
      _createdAt = $v.createdAt;
      _dataSource = $v.dataSource;
      _description = $v.description;
      _entityContext = $v.entityContext?.toBuilder();
      _evidenceLinks = $v.evidenceLinks;
      _excludedIps = $v.excludedIps?.toBuilder();
      _externalId = $v.externalId;
      _findingId = $v.findingId;
      _mitrePredictions = $v.mitrePredictions;
      _severity = $v.severity;
      _status = $v.status;
      _timestamp = $v.timestamp;
      _title = $v.title;
      _updatedAt = $v.updatedAt;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(FindingRecord other) {
    _$v = other as _$FindingRecord;
  }

  @override
  void update(void Function(FindingRecordBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  FindingRecord build() => _build();

  _$FindingRecord _build() {
    _$FindingRecord _$result;
    try {
      _$result = _$v ??
          _$FindingRecord._(
            aiEnrichment: aiEnrichment,
            anomalyScore: anomalyScore,
            clusterId: clusterId,
            createdAt: createdAt,
            dataSource: dataSource,
            description: description,
            entityContext: _entityContext?.build(),
            evidenceLinks: evidenceLinks,
            excludedIps: _excludedIps?.build(),
            externalId: externalId,
            findingId: findingId,
            mitrePredictions: mitrePredictions,
            severity: severity,
            status: status,
            timestamp: timestamp,
            title: title,
            updatedAt: updatedAt,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'entityContext';
        _entityContext?.build();

        _$failedField = 'excludedIps';
        _excludedIps?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'FindingRecord', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
