// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'closure_info.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ClosureInfo extends ClosureInfo {
  @override
  final ClosureCategory closureCategory;
  @override
  final String? closureNotes;
  @override
  final String? executiveSummary;
  @override
  final String? falsePositiveReason;
  @override
  final String? lessonsLearned;
  @override
  final String? recommendations;
  @override
  final String? rootCause;

  factory _$ClosureInfo([void Function(ClosureInfoBuilder)? updates]) =>
      (ClosureInfoBuilder()..update(updates))._build();

  _$ClosureInfo._(
      {required this.closureCategory,
      this.closureNotes,
      this.executiveSummary,
      this.falsePositiveReason,
      this.lessonsLearned,
      this.recommendations,
      this.rootCause})
      : super._();
  @override
  ClosureInfo rebuild(void Function(ClosureInfoBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ClosureInfoBuilder toBuilder() => ClosureInfoBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ClosureInfo &&
        closureCategory == other.closureCategory &&
        closureNotes == other.closureNotes &&
        executiveSummary == other.executiveSummary &&
        falsePositiveReason == other.falsePositiveReason &&
        lessonsLearned == other.lessonsLearned &&
        recommendations == other.recommendations &&
        rootCause == other.rootCause;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, closureCategory.hashCode);
    _$hash = $jc(_$hash, closureNotes.hashCode);
    _$hash = $jc(_$hash, executiveSummary.hashCode);
    _$hash = $jc(_$hash, falsePositiveReason.hashCode);
    _$hash = $jc(_$hash, lessonsLearned.hashCode);
    _$hash = $jc(_$hash, recommendations.hashCode);
    _$hash = $jc(_$hash, rootCause.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ClosureInfo')
          ..add('closureCategory', closureCategory)
          ..add('closureNotes', closureNotes)
          ..add('executiveSummary', executiveSummary)
          ..add('falsePositiveReason', falsePositiveReason)
          ..add('lessonsLearned', lessonsLearned)
          ..add('recommendations', recommendations)
          ..add('rootCause', rootCause))
        .toString();
  }
}

class ClosureInfoBuilder implements Builder<ClosureInfo, ClosureInfoBuilder> {
  _$ClosureInfo? _$v;

  ClosureCategory? _closureCategory;
  ClosureCategory? get closureCategory => _$this._closureCategory;
  set closureCategory(ClosureCategory? closureCategory) =>
      _$this._closureCategory = closureCategory;

  String? _closureNotes;
  String? get closureNotes => _$this._closureNotes;
  set closureNotes(String? closureNotes) => _$this._closureNotes = closureNotes;

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

  String? _rootCause;
  String? get rootCause => _$this._rootCause;
  set rootCause(String? rootCause) => _$this._rootCause = rootCause;

  ClosureInfoBuilder() {
    ClosureInfo._defaults(this);
  }

  ClosureInfoBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _closureCategory = $v.closureCategory;
      _closureNotes = $v.closureNotes;
      _executiveSummary = $v.executiveSummary;
      _falsePositiveReason = $v.falsePositiveReason;
      _lessonsLearned = $v.lessonsLearned;
      _recommendations = $v.recommendations;
      _rootCause = $v.rootCause;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ClosureInfo other) {
    _$v = other as _$ClosureInfo;
  }

  @override
  void update(void Function(ClosureInfoBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ClosureInfo build() => _build();

  _$ClosureInfo _build() {
    final _$result = _$v ??
        _$ClosureInfo._(
          closureCategory: BuiltValueNullFieldError.checkNotNull(
              closureCategory, r'ClosureInfo', 'closureCategory'),
          closureNotes: closureNotes,
          executiveSummary: executiveSummary,
          falsePositiveReason: falsePositiveReason,
          lessonsLearned: lessonsLearned,
          recommendations: recommendations,
          rootCause: rootCause,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
