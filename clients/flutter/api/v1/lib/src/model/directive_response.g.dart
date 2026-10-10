// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'directive_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$DirectiveResponse extends DirectiveResponse {
  @override
  final String createdAt;
  @override
  final String directiveId;
  @override
  final String kind;

  factory _$DirectiveResponse(
          [void Function(DirectiveResponseBuilder)? updates]) =>
      (DirectiveResponseBuilder()..update(updates))._build();

  _$DirectiveResponse._(
      {required this.createdAt, required this.directiveId, required this.kind})
      : super._();
  @override
  DirectiveResponse rebuild(void Function(DirectiveResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  DirectiveResponseBuilder toBuilder() =>
      DirectiveResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is DirectiveResponse &&
        createdAt == other.createdAt &&
        directiveId == other.directiveId &&
        kind == other.kind;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, directiveId.hashCode);
    _$hash = $jc(_$hash, kind.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'DirectiveResponse')
          ..add('createdAt', createdAt)
          ..add('directiveId', directiveId)
          ..add('kind', kind))
        .toString();
  }
}

class DirectiveResponseBuilder
    implements Builder<DirectiveResponse, DirectiveResponseBuilder> {
  _$DirectiveResponse? _$v;

  String? _createdAt;
  String? get createdAt => _$this._createdAt;
  set createdAt(String? createdAt) => _$this._createdAt = createdAt;

  String? _directiveId;
  String? get directiveId => _$this._directiveId;
  set directiveId(String? directiveId) => _$this._directiveId = directiveId;

  String? _kind;
  String? get kind => _$this._kind;
  set kind(String? kind) => _$this._kind = kind;

  DirectiveResponseBuilder() {
    DirectiveResponse._defaults(this);
  }

  DirectiveResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _createdAt = $v.createdAt;
      _directiveId = $v.directiveId;
      _kind = $v.kind;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(DirectiveResponse other) {
    _$v = other as _$DirectiveResponse;
  }

  @override
  void update(void Function(DirectiveResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  DirectiveResponse build() => _build();

  _$DirectiveResponse _build() {
    final _$result = _$v ??
        _$DirectiveResponse._(
          createdAt: BuiltValueNullFieldError.checkNotNull(
              createdAt, r'DirectiveResponse', 'createdAt'),
          directiveId: BuiltValueNullFieldError.checkNotNull(
              directiveId, r'DirectiveResponse', 'directiveId'),
          kind: BuiltValueNullFieldError.checkNotNull(
              kind, r'DirectiveResponse', 'kind'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
