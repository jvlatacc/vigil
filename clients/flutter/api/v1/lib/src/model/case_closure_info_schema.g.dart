// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_closure_info_schema.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseClosureInfoSchema extends CaseClosureInfoSchema {
  @override
  final String? caseId;
  @override
  final String? closedAt;
  @override
  final String? closedBy;
  @override
  final String? closureCategory;
  @override
  final String? closureNotes;
  @override
  final BuiltList<String>? contributingFactors;
  @override
  final String? executiveSummary;
  @override
  final String? falsePositiveReason;
  @override
  final String? lessonsLearned;
  @override
  final String? recommendations;
  @override
  final String? recurrencePrevention;
  @override
  final String? rootCause;

  factory _$CaseClosureInfoSchema(
          [void Function(CaseClosureInfoSchemaBuilder)? updates]) =>
      (CaseClosureInfoSchemaBuilder()..update(updates))._build();

  _$CaseClosureInfoSchema._(
      {this.caseId,
      this.closedAt,
      this.closedBy,
      this.closureCategory,
      this.closureNotes,
      this.contributingFactors,
      this.executiveSummary,
      this.falsePositiveReason,
      this.lessonsLearned,
      this.recommendations,
      this.recurrencePrevention,
      this.rootCause})
      : super._();
  @override
  CaseClosureInfoSchema rebuild(
          void Function(CaseClosureInfoSchemaBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseClosureInfoSchemaBuilder toBuilder() =>
      CaseClosureInfoSchemaBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseClosureInfoSchema &&
        caseId == other.caseId &&
        closedAt == other.closedAt &&
        closedBy == other.closedBy &&
        closureCategory == other.closureCategory &&
        closureNotes == other.closureNotes &&
        contributingFactors == other.contributingFactors &&
        executiveSummary == other.executiveSummary &&
        falsePositiveReason == other.falsePositiveReason &&
        lessonsLearned == other.lessonsLearned &&
        recommendations == other.recommendations &&
        recurrencePrevention == other.recurrencePrevention &&
        rootCause == other.rootCause;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, caseId.hashCode);
    _$hash = $jc(_$hash, closedAt.hashCode);
    _$hash = $jc(_$hash, closedBy.hashCode);
    _$hash = $jc(_$hash, closureCategory.hashCode);
    _$hash = $jc(_$hash, closureNotes.hashCode);
    _$hash = $jc(_$hash, contributingFactors.hashCode);
    _$hash = $jc(_$hash, executiveSummary.hashCode);
    _$hash = $jc(_$hash, falsePositiveReason.hashCode);
    _$hash = $jc(_$hash, lessonsLearned.hashCode);
    _$hash = $jc(_$hash, recommendations.hashCode);
    _$hash = $jc(_$hash, recurrencePrevention.hashCode);
    _$hash = $jc(_$hash, rootCause.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseClosureInfoSchema')
          ..add('caseId', caseId)
          ..add('closedAt', closedAt)
          ..add('closedBy', closedBy)
          ..add('closureCategory', closureCategory)
          ..add('closureNotes', closureNotes)
          ..add('contributingFactors', contributingFactors)
          ..add('executiveSummary', executiveSummary)
          ..add('falsePositiveReason', falsePositiveReason)
          ..add('lessonsLearned', lessonsLearned)
          ..add('recommendations', recommendations)
          ..add('recurrencePrevention', recurrencePrevention)
          ..add('rootCause', rootCause))
        .toString();
  }
}

class CaseClosureInfoSchemaBuilder
    implements Builder<CaseClosureInfoSchema, CaseClosureInfoSchemaBuilder> {
  _$CaseClosureInfoSchema? _$v;

  String? _caseId;
  String? get caseId => _$this._caseId;
  set caseId(String? caseId) => _$this._caseId = caseId;

  String? _closedAt;
  String? get closedAt => _$this._closedAt;
  set closedAt(String? closedAt) => _$this._closedAt = closedAt;

  String? _closedBy;
  String? get closedBy => _$this._closedBy;
  set closedBy(String? closedBy) => _$this._closedBy = closedBy;

  String? _closureCategory;
  String? get closureCategory => _$this._closureCategory;
  set closureCategory(String? closureCategory) =>
      _$this._closureCategory = closureCategory;

  String? _closureNotes;
  String? get closureNotes => _$this._closureNotes;
  set closureNotes(String? closureNotes) => _$this._closureNotes = closureNotes;

  ListBuilder<String>? _contributingFactors;
  ListBuilder<String> get contributingFactors =>
      _$this._contributingFactors ??= ListBuilder<String>();
  set contributingFactors(ListBuilder<String>? contributingFactors) =>
      _$this._contributingFactors = contributingFactors;

  String? _executiveSummary;
  String? get executiveSummary => _$this._executiveSummary;
  set executiveSummary(String? executiveSummary) =>
      _$this._executiveSummary = executiveSummary;

  String? _falsePositiveReason;
  String? get falsePositiveReason => _$this._falsePositiveReason;
  set falsePositiveReason(String? falsePositiveReason) =>
      _$this._falsePositiveReason = falsePositiveReason;

  String? _lessonsLearned;
  String? get lessonsLearned => _$this._lessonsLearned;
  set lessonsLearned(String? lessonsLearned) =>
      _$this._lessonsLearned = lessonsLearned;

  String? _recommendations;
  String? get recommendations => _$this._recommendations;
  set recommendations(String? recommendations) =>
      _$this._recommendations = recommendations;

  String? _recurrencePrevention;
  String? get recurrencePrevention => _$this._recurrencePrevention;
  set recurrencePrevention(String? recurrencePrevention) =>
      _$this._recurrencePrevention = recurrencePrevention;

  String? _rootCause;
  String? get rootCause => _$this._rootCause;
  set rootCause(String? rootCause) => _$this._rootCause = rootCause;

  CaseClosureInfoSchemaBuilder() {
    CaseClosureInfoSchema._defaults(this);
  }

  CaseClosureInfoSchemaBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _caseId = $v.caseId;
      _closedAt = $v.closedAt;
      _closedBy = $v.closedBy;
      _closureCategory = $v.closureCategory;
      _closureNotes = $v.closureNotes;
      _contributingFactors = $v.contributingFactors?.toBuilder();
      _executiveSummary = $v.executiveSummary;
      _falsePositiveReason = $v.falsePositiveReason;
      _lessonsLearned = $v.lessonsLearned;
      _recommendations = $v.recommendations;
      _recurrencePrevention = $v.recurrencePrevention;
      _rootCause = $v.rootCause;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseClosureInfoSchema other) {
    _$v = other as _$CaseClosureInfoSchema;
  }

  @override
  void update(void Function(CaseClosureInfoSchemaBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseClosureInfoSchema build() => _build();

  _$CaseClosureInfoSchema _build() {
    _$CaseClosureInfoSchema _$result;
    try {
      _$result = _$v ??
          _$CaseClosureInfoSchema._(
            caseId: caseId,
            closedAt: closedAt,
            closedBy: closedBy,
            closureCategory: closureCategory,
            closureNotes: closureNotes,
            contributingFactors: _contributingFactors?.build(),
            executiveSummary: executiveSummary,
            falsePositiveReason: falsePositiveReason,
            lessonsLearned: lessonsLearned,
            recommendations: recommendations,
            recurrencePrevention: recurrencePrevention,
            rootCause: rootCause,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'contributingFactors';
        _contributingFactors?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseClosureInfoSchema', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
