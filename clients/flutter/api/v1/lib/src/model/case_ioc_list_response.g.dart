// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_ioc_list_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseIOCListResponse extends CaseIOCListResponse {
  @override
  final BuiltList<CaseIOCSchema> iocs;

  factory _$CaseIOCListResponse(
          [void Function(CaseIOCListResponseBuilder)? updates]) =>
      (CaseIOCListResponseBuilder()..update(updates))._build();

  _$CaseIOCListResponse._({required this.iocs}) : super._();
  @override
  CaseIOCListResponse rebuild(
          void Function(CaseIOCListResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseIOCListResponseBuilder toBuilder() =>
      CaseIOCListResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseIOCListResponse && iocs == other.iocs;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, iocs.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseIOCListResponse')
          ..add('iocs', iocs))
        .toString();
  }
}

class CaseIOCListResponseBuilder
    implements Builder<CaseIOCListResponse, CaseIOCListResponseBuilder> {
  _$CaseIOCListResponse? _$v;

  ListBuilder<CaseIOCSchema>? _iocs;
  ListBuilder<CaseIOCSchema> get iocs =>
      _$this._iocs ??= ListBuilder<CaseIOCSchema>();
  set iocs(ListBuilder<CaseIOCSchema>? iocs) => _$this._iocs = iocs;

  CaseIOCListResponseBuilder() {
    CaseIOCListResponse._defaults(this);
  }

  CaseIOCListResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _iocs = $v.iocs.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseIOCListResponse other) {
    _$v = other as _$CaseIOCListResponse;
  }

  @override
  void update(void Function(CaseIOCListResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseIOCListResponse build() => _build();

  _$CaseIOCListResponse _build() {
    _$CaseIOCListResponse _$result;
    try {
      _$result = _$v ??
          _$CaseIOCListResponse._(
            iocs: iocs.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'iocs';
        iocs.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseIOCListResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
