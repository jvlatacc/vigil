// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'entity_context.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$EntityContext extends EntityContext {
  @override
  final SourceEvidence? sourceEvidence;

  factory _$EntityContext([void Function(EntityContextBuilder)? updates]) =>
      (EntityContextBuilder()..update(updates))._build();

  _$EntityContext._({this.sourceEvidence}) : super._();
  @override
  EntityContext rebuild(void Function(EntityContextBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  EntityContextBuilder toBuilder() => EntityContextBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is EntityContext && sourceEvidence == other.sourceEvidence;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, sourceEvidence.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'EntityContext')
          ..add('sourceEvidence', sourceEvidence))
        .toString();
  }
}

class EntityContextBuilder
    implements Builder<EntityContext, EntityContextBuilder> {
  _$EntityContext? _$v;

  SourceEvidenceBuilder? _sourceEvidence;
  SourceEvidenceBuilder get sourceEvidence =>
      _$this._sourceEvidence ??= SourceEvidenceBuilder();
  set sourceEvidence(SourceEvidenceBuilder? sourceEvidence) =>
      _$this._sourceEvidence = sourceEvidence;

  EntityContextBuilder() {
    EntityContext._defaults(this);
  }

  EntityContextBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _sourceEvidence = $v.sourceEvidence?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(EntityContext other) {
    _$v = other as _$EntityContext;
  }

  @override
  void update(void Function(EntityContextBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  EntityContext build() => _build();

  _$EntityContext _build() {
    _$EntityContext _$result;
    try {
      _$result = _$v ??
          _$EntityContext._(
            sourceEvidence: _sourceEvidence?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'sourceEvidence';
        _sourceEvidence?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'EntityContext', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
