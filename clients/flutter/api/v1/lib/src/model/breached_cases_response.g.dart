// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'breached_cases_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$BreachedCasesResponse extends BreachedCasesResponse {
  @override
  final BuiltList<BuiltMap<String, JsonObject?>>? breachedCases;

  factory _$BreachedCasesResponse(
          [void Function(BreachedCasesResponseBuilder)? updates]) =>
      (BreachedCasesResponseBuilder()..update(updates))._build();

  _$BreachedCasesResponse._({this.breachedCases}) : super._();
  @override
  BreachedCasesResponse rebuild(
          void Function(BreachedCasesResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  BreachedCasesResponseBuilder toBuilder() =>
      BreachedCasesResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is BreachedCasesResponse &&
        breachedCases == other.breachedCases;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, breachedCases.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'BreachedCasesResponse')
          ..add('breachedCases', breachedCases))
        .toString();
  }
}

class BreachedCasesResponseBuilder
    implements Builder<BreachedCasesResponse, BreachedCasesResponseBuilder> {
  _$BreachedCasesResponse? _$v;

  ListBuilder<BuiltMap<String, JsonObject?>>? _breachedCases;
  ListBuilder<BuiltMap<String, JsonObject?>> get breachedCases =>
      _$this._breachedCases ??= ListBuilder<BuiltMap<String, JsonObject?>>();
  set breachedCases(
          ListBuilder<BuiltMap<String, JsonObject?>>? breachedCases) =>
      _$this._breachedCases = breachedCases;

  BreachedCasesResponseBuilder() {
    BreachedCasesResponse._defaults(this);
  }

  BreachedCasesResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _breachedCases = $v.breachedCases?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(BreachedCasesResponse other) {
    _$v = other as _$BreachedCasesResponse;
  }

  @override
  void update(void Function(BreachedCasesResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  BreachedCasesResponse build() => _build();

  _$BreachedCasesResponse _build() {
    _$BreachedCasesResponse _$result;
    try {
      _$result = _$v ??
          _$BreachedCasesResponse._(
            breachedCases: _breachedCases?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'breachedCases';
        _breachedCases?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'BreachedCasesResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
