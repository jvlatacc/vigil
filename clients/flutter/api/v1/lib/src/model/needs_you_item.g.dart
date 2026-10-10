// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'needs_you_item.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$NeedsYouItem extends NeedsYouItem {
  @override
  final String? caseId;
  @override
  final String createdAt;
  @override
  final String kind;
  @override
  final String reason;
  @override
  final String reversibility;
  @override
  final String sourceId;
  @override
  final String title;

  factory _$NeedsYouItem([void Function(NeedsYouItemBuilder)? updates]) =>
      (NeedsYouItemBuilder()..update(updates))._build();

  _$NeedsYouItem._(
      {this.caseId,
      required this.createdAt,
      required this.kind,
      required this.reason,
      required this.reversibility,
      required this.sourceId,
      required this.title})
      : super._();
  @override
  NeedsYouItem rebuild(void Function(NeedsYouItemBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  NeedsYouItemBuilder toBuilder() => NeedsYouItemBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is NeedsYouItem &&
        caseId == other.caseId &&
        createdAt == other.createdAt &&
        kind == other.kind &&
        reason == other.reason &&
        reversibility == other.reversibility &&
        sourceId == other.sourceId &&
        title == other.title;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, caseId.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, kind.hashCode);
    _$hash = $jc(_$hash, reason.hashCode);
    _$hash = $jc(_$hash, reversibility.hashCode);
    _$hash = $jc(_$hash, sourceId.hashCode);
    _$hash = $jc(_$hash, title.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'NeedsYouItem')
          ..add('caseId', caseId)
          ..add('createdAt', createdAt)
          ..add('kind', kind)
          ..add('reason', reason)
          ..add('reversibility', reversibility)
          ..add('sourceId', sourceId)
          ..add('title', title))
        .toString();
  }
}

class NeedsYouItemBuilder
    implements Builder<NeedsYouItem, NeedsYouItemBuilder> {
  _$NeedsYouItem? _$v;

  String? _caseId;
  String? get caseId => _$this._caseId;
  set caseId(String? caseId) => _$this._caseId = caseId;

  String? _createdAt;
  String? get createdAt => _$this._createdAt;
  set createdAt(String? createdAt) => _$this._createdAt = createdAt;

  String? _kind;
  String? get kind => _$this._kind;
  set kind(String? kind) => _$this._kind = kind;

  String? _reason;
  String? get reason => _$this._reason;
  set reason(String? reason) => _$this._reason = reason;

  String? _reversibility;
  String? get reversibility => _$this._reversibility;
  set reversibility(String? reversibility) =>
      _$this._reversibility = reversibility;

  String? _sourceId;
  String? get sourceId => _$this._sourceId;
  set sourceId(String? sourceId) => _$this._sourceId = sourceId;

  String? _title;
  String? get title => _$this._title;
  set title(String? title) => _$this._title = title;

  NeedsYouItemBuilder() {
    NeedsYouItem._defaults(this);
  }

  NeedsYouItemBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _caseId = $v.caseId;
      _createdAt = $v.createdAt;
      _kind = $v.kind;
      _reason = $v.reason;
      _reversibility = $v.reversibility;
      _sourceId = $v.sourceId;
      _title = $v.title;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(NeedsYouItem other) {
    _$v = other as _$NeedsYouItem;
  }

  @override
  void update(void Function(NeedsYouItemBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  NeedsYouItem build() => _build();

  _$NeedsYouItem _build() {
    final _$result = _$v ??
        _$NeedsYouItem._(
          caseId: caseId,
          createdAt: BuiltValueNullFieldError.checkNotNull(
              createdAt, r'NeedsYouItem', 'createdAt'),
          kind: BuiltValueNullFieldError.checkNotNull(
              kind, r'NeedsYouItem', 'kind'),
          reason: BuiltValueNullFieldError.checkNotNull(
              reason, r'NeedsYouItem', 'reason'),
          reversibility: BuiltValueNullFieldError.checkNotNull(
              reversibility, r'NeedsYouItem', 'reversibility'),
          sourceId: BuiltValueNullFieldError.checkNotNull(
              sourceId, r'NeedsYouItem', 'sourceId'),
          title: BuiltValueNullFieldError.checkNotNull(
              title, r'NeedsYouItem', 'title'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
