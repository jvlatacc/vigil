// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_ioc_schema.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseIOCSchema extends CaseIOCSchema {
  @override
  final String? caseId;
  @override
  final num? confidence;
  @override
  final String? context;
  @override
  final String? createdAt;
  @override
  final AnyOf? enrichmentData;
  @override
  final String? firstSeen;
  @override
  final int? iocId;
  @override
  final String? iocType;
  @override
  final bool? isActive;
  @override
  final bool? isFalsePositive;
  @override
  final String? lastSeen;
  @override
  final num? reputationScore;
  @override
  final String? source_;
  @override
  final BuiltList<String>? tags;
  @override
  final String? threatLevel;
  @override
  final String? updatedAt;
  @override
  final String? value;

  factory _$CaseIOCSchema([void Function(CaseIOCSchemaBuilder)? updates]) =>
      (CaseIOCSchemaBuilder()..update(updates))._build();

  _$CaseIOCSchema._(
      {this.caseId,
      this.confidence,
      this.context,
      this.createdAt,
      this.enrichmentData,
      this.firstSeen,
      this.iocId,
      this.iocType,
      this.isActive,
      this.isFalsePositive,
      this.lastSeen,
      this.reputationScore,
      this.source_,
      this.tags,
      this.threatLevel,
      this.updatedAt,
      this.value})
      : super._();
  @override
  CaseIOCSchema rebuild(void Function(CaseIOCSchemaBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseIOCSchemaBuilder toBuilder() => CaseIOCSchemaBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseIOCSchema &&
        caseId == other.caseId &&
        confidence == other.confidence &&
        context == other.context &&
        createdAt == other.createdAt &&
        enrichmentData == other.enrichmentData &&
        firstSeen == other.firstSeen &&
        iocId == other.iocId &&
        iocType == other.iocType &&
        isActive == other.isActive &&
        isFalsePositive == other.isFalsePositive &&
        lastSeen == other.lastSeen &&
        reputationScore == other.reputationScore &&
        source_ == other.source_ &&
        tags == other.tags &&
        threatLevel == other.threatLevel &&
        updatedAt == other.updatedAt &&
        value == other.value;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, caseId.hashCode);
    _$hash = $jc(_$hash, confidence.hashCode);
    _$hash = $jc(_$hash, context.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, enrichmentData.hashCode);
    _$hash = $jc(_$hash, firstSeen.hashCode);
    _$hash = $jc(_$hash, iocId.hashCode);
    _$hash = $jc(_$hash, iocType.hashCode);
    _$hash = $jc(_$hash, isActive.hashCode);
    _$hash = $jc(_$hash, isFalsePositive.hashCode);
    _$hash = $jc(_$hash, lastSeen.hashCode);
    _$hash = $jc(_$hash, reputationScore.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jc(_$hash, tags.hashCode);
    _$hash = $jc(_$hash, threatLevel.hashCode);
    _$hash = $jc(_$hash, updatedAt.hashCode);
    _$hash = $jc(_$hash, value.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseIOCSchema')
          ..add('caseId', caseId)
          ..add('confidence', confidence)
          ..add('context', context)
          ..add('createdAt', createdAt)
          ..add('enrichmentData', enrichmentData)
          ..add('firstSeen', firstSeen)
          ..add('iocId', iocId)
          ..add('iocType', iocType)
          ..add('isActive', isActive)
          ..add('isFalsePositive', isFalsePositive)
          ..add('lastSeen', lastSeen)
          ..add('reputationScore', reputationScore)
          ..add('source_', source_)
          ..add('tags', tags)
          ..add('threatLevel', threatLevel)
          ..add('updatedAt', updatedAt)
          ..add('value', value))
        .toString();
  }
}

class CaseIOCSchemaBuilder
    implements Builder<CaseIOCSchema, CaseIOCSchemaBuilder> {
  _$CaseIOCSchema? _$v;

  String? _caseId;
  String? get caseId => _$this._caseId;
  set caseId(String? caseId) => _$this._caseId = caseId;

  num? _confidence;
  num? get confidence => _$this._confidence;
  set confidence(num? confidence) => _$this._confidence = confidence;

  String? _context;
  String? get context => _$this._context;
  set context(String? context) => _$this._context = context;

  String? _createdAt;
  String? get createdAt => _$this._createdAt;
  set createdAt(String? createdAt) => _$this._createdAt = createdAt;

  AnyOf? _enrichmentData;
  AnyOf? get enrichmentData => _$this._enrichmentData;
  set enrichmentData(AnyOf? enrichmentData) =>
      _$this._enrichmentData = enrichmentData;

  String? _firstSeen;
  String? get firstSeen => _$this._firstSeen;
  set firstSeen(String? firstSeen) => _$this._firstSeen = firstSeen;

  int? _iocId;
  int? get iocId => _$this._iocId;
  set iocId(int? iocId) => _$this._iocId = iocId;

  String? _iocType;
  String? get iocType => _$this._iocType;
  set iocType(String? iocType) => _$this._iocType = iocType;

  bool? _isActive;
  bool? get isActive => _$this._isActive;
  set isActive(bool? isActive) => _$this._isActive = isActive;

  bool? _isFalsePositive;
  bool? get isFalsePositive => _$this._isFalsePositive;
  set isFalsePositive(bool? isFalsePositive) =>
      _$this._isFalsePositive = isFalsePositive;

  String? _lastSeen;
  String? get lastSeen => _$this._lastSeen;
  set lastSeen(String? lastSeen) => _$this._lastSeen = lastSeen;

  num? _reputationScore;
  num? get reputationScore => _$this._reputationScore;
  set reputationScore(num? reputationScore) =>
      _$this._reputationScore = reputationScore;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  ListBuilder<String>? _tags;
  ListBuilder<String> get tags => _$this._tags ??= ListBuilder<String>();
  set tags(ListBuilder<String>? tags) => _$this._tags = tags;

  String? _threatLevel;
  String? get threatLevel => _$this._threatLevel;
  set threatLevel(String? threatLevel) => _$this._threatLevel = threatLevel;

  String? _updatedAt;
  String? get updatedAt => _$this._updatedAt;
  set updatedAt(String? updatedAt) => _$this._updatedAt = updatedAt;

  String? _value;
  String? get value => _$this._value;
  set value(String? value) => _$this._value = value;

  CaseIOCSchemaBuilder() {
    CaseIOCSchema._defaults(this);
  }

  CaseIOCSchemaBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _caseId = $v.caseId;
      _confidence = $v.confidence;
      _context = $v.context;
      _createdAt = $v.createdAt;
      _enrichmentData = $v.enrichmentData;
      _firstSeen = $v.firstSeen;
      _iocId = $v.iocId;
      _iocType = $v.iocType;
      _isActive = $v.isActive;
      _isFalsePositive = $v.isFalsePositive;
      _lastSeen = $v.lastSeen;
      _reputationScore = $v.reputationScore;
      _source_ = $v.source_;
      _tags = $v.tags?.toBuilder();
      _threatLevel = $v.threatLevel;
      _updatedAt = $v.updatedAt;
      _value = $v.value;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseIOCSchema other) {
    _$v = other as _$CaseIOCSchema;
  }

  @override
  void update(void Function(CaseIOCSchemaBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseIOCSchema build() => _build();

  _$CaseIOCSchema _build() {
    _$CaseIOCSchema _$result;
    try {
      _$result = _$v ??
          _$CaseIOCSchema._(
            caseId: caseId,
            confidence: confidence,
            context: context,
            createdAt: createdAt,
            enrichmentData: enrichmentData,
            firstSeen: firstSeen,
            iocId: iocId,
            iocType: iocType,
            isActive: isActive,
            isFalsePositive: isFalsePositive,
            lastSeen: lastSeen,
            reputationScore: reputationScore,
            source_: source_,
            tags: _tags?.build(),
            threatLevel: threatLevel,
            updatedAt: updatedAt,
            value: value,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'tags';
        _tags?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseIOCSchema', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
