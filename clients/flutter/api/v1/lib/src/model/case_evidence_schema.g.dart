// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_evidence_schema.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseEvidenceSchema extends CaseEvidenceSchema {
  @override
  final AnyOf? analysisResults;
  @override
  final String? caseId;
  @override
  final BuiltList<JsonObject?>? chainOfCustody;
  @override
  final String? collectedAt;
  @override
  final String? collectedBy;
  @override
  final String? createdAt;
  @override
  final String? description;
  @override
  final int? evidenceId;
  @override
  final String? evidenceType;
  @override
  final String? fileHashMd5;
  @override
  final String? fileHashSha256;
  @override
  final String? filePath;
  @override
  final int? fileSize;
  @override
  final String? name;
  @override
  final String? source_;
  @override
  final BuiltList<String>? tags;
  @override
  final String? updatedAt;

  factory _$CaseEvidenceSchema(
          [void Function(CaseEvidenceSchemaBuilder)? updates]) =>
      (CaseEvidenceSchemaBuilder()..update(updates))._build();

  _$CaseEvidenceSchema._(
      {this.analysisResults,
      this.caseId,
      this.chainOfCustody,
      this.collectedAt,
      this.collectedBy,
      this.createdAt,
      this.description,
      this.evidenceId,
      this.evidenceType,
      this.fileHashMd5,
      this.fileHashSha256,
      this.filePath,
      this.fileSize,
      this.name,
      this.source_,
      this.tags,
      this.updatedAt})
      : super._();
  @override
  CaseEvidenceSchema rebuild(
          void Function(CaseEvidenceSchemaBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseEvidenceSchemaBuilder toBuilder() =>
      CaseEvidenceSchemaBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseEvidenceSchema &&
        analysisResults == other.analysisResults &&
        caseId == other.caseId &&
        chainOfCustody == other.chainOfCustody &&
        collectedAt == other.collectedAt &&
        collectedBy == other.collectedBy &&
        createdAt == other.createdAt &&
        description == other.description &&
        evidenceId == other.evidenceId &&
        evidenceType == other.evidenceType &&
        fileHashMd5 == other.fileHashMd5 &&
        fileHashSha256 == other.fileHashSha256 &&
        filePath == other.filePath &&
        fileSize == other.fileSize &&
        name == other.name &&
        source_ == other.source_ &&
        tags == other.tags &&
        updatedAt == other.updatedAt;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, analysisResults.hashCode);
    _$hash = $jc(_$hash, caseId.hashCode);
    _$hash = $jc(_$hash, chainOfCustody.hashCode);
    _$hash = $jc(_$hash, collectedAt.hashCode);
    _$hash = $jc(_$hash, collectedBy.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, description.hashCode);
    _$hash = $jc(_$hash, evidenceId.hashCode);
    _$hash = $jc(_$hash, evidenceType.hashCode);
    _$hash = $jc(_$hash, fileHashMd5.hashCode);
    _$hash = $jc(_$hash, fileHashSha256.hashCode);
    _$hash = $jc(_$hash, filePath.hashCode);
    _$hash = $jc(_$hash, fileSize.hashCode);
    _$hash = $jc(_$hash, name.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jc(_$hash, tags.hashCode);
    _$hash = $jc(_$hash, updatedAt.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseEvidenceSchema')
          ..add('analysisResults', analysisResults)
          ..add('caseId', caseId)
          ..add('chainOfCustody', chainOfCustody)
          ..add('collectedAt', collectedAt)
          ..add('collectedBy', collectedBy)
          ..add('createdAt', createdAt)
          ..add('description', description)
          ..add('evidenceId', evidenceId)
          ..add('evidenceType', evidenceType)
          ..add('fileHashMd5', fileHashMd5)
          ..add('fileHashSha256', fileHashSha256)
          ..add('filePath', filePath)
          ..add('fileSize', fileSize)
          ..add('name', name)
          ..add('source_', source_)
          ..add('tags', tags)
          ..add('updatedAt', updatedAt))
        .toString();
  }
}

class CaseEvidenceSchemaBuilder
    implements Builder<CaseEvidenceSchema, CaseEvidenceSchemaBuilder> {
  _$CaseEvidenceSchema? _$v;

  AnyOf? _analysisResults;
  AnyOf? get analysisResults => _$this._analysisResults;
  set analysisResults(AnyOf? analysisResults) =>
      _$this._analysisResults = analysisResults;

  String? _caseId;
  String? get caseId => _$this._caseId;
  set caseId(String? caseId) => _$this._caseId = caseId;

  ListBuilder<JsonObject?>? _chainOfCustody;
  ListBuilder<JsonObject?> get chainOfCustody =>
      _$this._chainOfCustody ??= ListBuilder<JsonObject?>();
  set chainOfCustody(ListBuilder<JsonObject?>? chainOfCustody) =>
      _$this._chainOfCustody = chainOfCustody;

  String? _collectedAt;
  String? get collectedAt => _$this._collectedAt;
  set collectedAt(String? collectedAt) => _$this._collectedAt = collectedAt;

  String? _collectedBy;
  String? get collectedBy => _$this._collectedBy;
  set collectedBy(String? collectedBy) => _$this._collectedBy = collectedBy;

  String? _createdAt;
  String? get createdAt => _$this._createdAt;
  set createdAt(String? createdAt) => _$this._createdAt = createdAt;

  String? _description;
  String? get description => _$this._description;
  set description(String? description) => _$this._description = description;

  int? _evidenceId;
  int? get evidenceId => _$this._evidenceId;
  set evidenceId(int? evidenceId) => _$this._evidenceId = evidenceId;

  String? _evidenceType;
  String? get evidenceType => _$this._evidenceType;
  set evidenceType(String? evidenceType) => _$this._evidenceType = evidenceType;

  String? _fileHashMd5;
  String? get fileHashMd5 => _$this._fileHashMd5;
  set fileHashMd5(String? fileHashMd5) => _$this._fileHashMd5 = fileHashMd5;

  String? _fileHashSha256;
  String? get fileHashSha256 => _$this._fileHashSha256;
  set fileHashSha256(String? fileHashSha256) =>
      _$this._fileHashSha256 = fileHashSha256;

  String? _filePath;
  String? get filePath => _$this._filePath;
  set filePath(String? filePath) => _$this._filePath = filePath;

  int? _fileSize;
  int? get fileSize => _$this._fileSize;
  set fileSize(int? fileSize) => _$this._fileSize = fileSize;

  String? _name;
  String? get name => _$this._name;
  set name(String? name) => _$this._name = name;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  ListBuilder<String>? _tags;
  ListBuilder<String> get tags => _$this._tags ??= ListBuilder<String>();
  set tags(ListBuilder<String>? tags) => _$this._tags = tags;

  String? _updatedAt;
  String? get updatedAt => _$this._updatedAt;
  set updatedAt(String? updatedAt) => _$this._updatedAt = updatedAt;

  CaseEvidenceSchemaBuilder() {
    CaseEvidenceSchema._defaults(this);
  }

  CaseEvidenceSchemaBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _analysisResults = $v.analysisResults;
      _caseId = $v.caseId;
      _chainOfCustody = $v.chainOfCustody?.toBuilder();
      _collectedAt = $v.collectedAt;
      _collectedBy = $v.collectedBy;
      _createdAt = $v.createdAt;
      _description = $v.description;
      _evidenceId = $v.evidenceId;
      _evidenceType = $v.evidenceType;
      _fileHashMd5 = $v.fileHashMd5;
      _fileHashSha256 = $v.fileHashSha256;
      _filePath = $v.filePath;
      _fileSize = $v.fileSize;
      _name = $v.name;
      _source_ = $v.source_;
      _tags = $v.tags?.toBuilder();
      _updatedAt = $v.updatedAt;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseEvidenceSchema other) {
    _$v = other as _$CaseEvidenceSchema;
  }

  @override
  void update(void Function(CaseEvidenceSchemaBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseEvidenceSchema build() => _build();

  _$CaseEvidenceSchema _build() {
    _$CaseEvidenceSchema _$result;
    try {
      _$result = _$v ??
          _$CaseEvidenceSchema._(
            analysisResults: analysisResults,
            caseId: caseId,
            chainOfCustody: _chainOfCustody?.build(),
            collectedAt: collectedAt,
            collectedBy: collectedBy,
            createdAt: createdAt,
            description: description,
            evidenceId: evidenceId,
            evidenceType: evidenceType,
            fileHashMd5: fileHashMd5,
            fileHashSha256: fileHashSha256,
            filePath: filePath,
            fileSize: fileSize,
            name: name,
            source_: source_,
            tags: _tags?.build(),
            updatedAt: updatedAt,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'chainOfCustody';
        _chainOfCustody?.build();

        _$failedField = 'tags';
        _tags?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseEvidenceSchema', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
