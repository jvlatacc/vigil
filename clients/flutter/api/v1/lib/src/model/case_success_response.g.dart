// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_success_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseSuccessResponse extends CaseSuccessResponse {
  @override
  final bool success;

  factory _$CaseSuccessResponse(
          [void Function(CaseSuccessResponseBuilder)? updates]) =>
      (CaseSuccessResponseBuilder()..update(updates))._build();

  _$CaseSuccessResponse._({required this.success}) : super._();
  @override
  CaseSuccessResponse rebuild(
          void Function(CaseSuccessResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseSuccessResponseBuilder toBuilder() =>
      CaseSuccessResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseSuccessResponse && success == other.success;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, success.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseSuccessResponse')
          ..add('success', success))
        .toString();
  }
}

class CaseSuccessResponseBuilder
    implements Builder<CaseSuccessResponse, CaseSuccessResponseBuilder> {
  _$CaseSuccessResponse? _$v;

  bool? _success;
  bool? get success => _$this._success;
  set success(bool? success) => _$this._success = success;

  CaseSuccessResponseBuilder() {
    CaseSuccessResponse._defaults(this);
  }

  CaseSuccessResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _success = $v.success;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseSuccessResponse other) {
    _$v = other as _$CaseSuccessResponse;
  }

  @override
  void update(void Function(CaseSuccessResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseSuccessResponse build() => _build();

  _$CaseSuccessResponse _build() {
    final _$result = _$v ??
        _$CaseSuccessResponse._(
          success: BuiltValueNullFieldError.checkNotNull(
              success, r'CaseSuccessResponse', 'success'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
