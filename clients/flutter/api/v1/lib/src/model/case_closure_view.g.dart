// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_closure_view.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseClosureView extends CaseClosureView {
  @override
  final String? closedAt;
  @override
  final String closedBy;
  @override
  final String closedByKind;
  @override
  final String closureCategory;
  @override
  final String? verdict;

  factory _$CaseClosureView([void Function(CaseClosureViewBuilder)? updates]) =>
      (CaseClosureViewBuilder()..update(updates))._build();

  _$CaseClosureView._(
      {this.closedAt,
      required this.closedBy,
      required this.closedByKind,
      required this.closureCategory,
      this.verdict})
      : super._();
  @override
  CaseClosureView rebuild(void Function(CaseClosureViewBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseClosureViewBuilder toBuilder() => CaseClosureViewBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseClosureView &&
        closedAt == other.closedAt &&
        closedBy == other.closedBy &&
        closedByKind == other.closedByKind &&
        closureCategory == other.closureCategory &&
        verdict == other.verdict;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, closedAt.hashCode);
    _$hash = $jc(_$hash, closedBy.hashCode);
    _$hash = $jc(_$hash, closedByKind.hashCode);
    _$hash = $jc(_$hash, closureCategory.hashCode);
    _$hash = $jc(_$hash, verdict.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseClosureView')
          ..add('closedAt', closedAt)
          ..add('closedBy', closedBy)
          ..add('closedByKind', closedByKind)
          ..add('closureCategory', closureCategory)
          ..add('verdict', verdict))
        .toString();
  }
}

class CaseClosureViewBuilder
    implements Builder<CaseClosureView, CaseClosureViewBuilder> {
  _$CaseClosureView? _$v;

  String? _closedAt;
  String? get closedAt => _$this._closedAt;
  set closedAt(String? closedAt) => _$this._closedAt = closedAt;

  String? _closedBy;
  String? get closedBy => _$this._closedBy;
  set closedBy(String? closedBy) => _$this._closedBy = closedBy;

  String? _closedByKind;
  String? get closedByKind => _$this._closedByKind;
  set closedByKind(String? closedByKind) => _$this._closedByKind = closedByKind;

  String? _closureCategory;
  String? get closureCategory => _$this._closureCategory;
  set closureCategory(String? closureCategory) =>
      _$this._closureCategory = closureCategory;

  String? _verdict;
  String? get verdict => _$this._verdict;
  set verdict(String? verdict) => _$this._verdict = verdict;

  CaseClosureViewBuilder() {
    CaseClosureView._defaults(this);
  }

  CaseClosureViewBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _closedAt = $v.closedAt;
      _closedBy = $v.closedBy;
      _closedByKind = $v.closedByKind;
      _closureCategory = $v.closureCategory;
      _verdict = $v.verdict;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseClosureView other) {
    _$v = other as _$CaseClosureView;
  }

  @override
  void update(void Function(CaseClosureViewBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseClosureView build() => _build();

  _$CaseClosureView _build() {
    final _$result = _$v ??
        _$CaseClosureView._(
          closedAt: closedAt,
          closedBy: BuiltValueNullFieldError.checkNotNull(
              closedBy, r'CaseClosureView', 'closedBy'),
          closedByKind: BuiltValueNullFieldError.checkNotNull(
              closedByKind, r'CaseClosureView', 'closedByKind'),
          closureCategory: BuiltValueNullFieldError.checkNotNull(
              closureCategory, r'CaseClosureView', 'closureCategory'),
          verdict: verdict,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
