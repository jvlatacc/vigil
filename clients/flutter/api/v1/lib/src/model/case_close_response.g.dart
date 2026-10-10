// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_close_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseCloseResponse extends CaseCloseResponse {
  @override
  final CaseClosureInfoSchema closure;
  @override
  final bool success;

  factory _$CaseCloseResponse(
          [void Function(CaseCloseResponseBuilder)? updates]) =>
      (CaseCloseResponseBuilder()..update(updates))._build();

  _$CaseCloseResponse._({required this.closure, required this.success})
      : super._();
  @override
  CaseCloseResponse rebuild(void Function(CaseCloseResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseCloseResponseBuilder toBuilder() =>
      CaseCloseResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseCloseResponse &&
        closure == other.closure &&
        success == other.success;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, closure.hashCode);
    _$hash = $jc(_$hash, success.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseCloseResponse')
          ..add('closure', closure)
          ..add('success', success))
        .toString();
  }
}

class CaseCloseResponseBuilder
    implements Builder<CaseCloseResponse, CaseCloseResponseBuilder> {
  _$CaseCloseResponse? _$v;

  CaseClosureInfoSchemaBuilder? _closure;
  CaseClosureInfoSchemaBuilder get closure =>
      _$this._closure ??= CaseClosureInfoSchemaBuilder();
  set closure(CaseClosureInfoSchemaBuilder? closure) =>
      _$this._closure = closure;

  bool? _success;
  bool? get success => _$this._success;
  set success(bool? success) => _$this._success = success;

  CaseCloseResponseBuilder() {
    CaseCloseResponse._defaults(this);
  }

  CaseCloseResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _closure = $v.closure.toBuilder();
      _success = $v.success;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseCloseResponse other) {
    _$v = other as _$CaseCloseResponse;
  }

  @override
  void update(void Function(CaseCloseResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseCloseResponse build() => _build();

  _$CaseCloseResponse _build() {
    _$CaseCloseResponse _$result;
    try {
      _$result = _$v ??
          _$CaseCloseResponse._(
            closure: closure.build(),
            success: BuiltValueNullFieldError.checkNotNull(
                success, r'CaseCloseResponse', 'success'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'closure';
        closure.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseCloseResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
