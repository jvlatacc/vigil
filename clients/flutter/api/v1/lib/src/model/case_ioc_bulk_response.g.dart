// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_ioc_bulk_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseIOCBulkResponse extends CaseIOCBulkResponse {
  @override
  final int added;

  factory _$CaseIOCBulkResponse(
          [void Function(CaseIOCBulkResponseBuilder)? updates]) =>
      (CaseIOCBulkResponseBuilder()..update(updates))._build();

  _$CaseIOCBulkResponse._({required this.added}) : super._();
  @override
  CaseIOCBulkResponse rebuild(
          void Function(CaseIOCBulkResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseIOCBulkResponseBuilder toBuilder() =>
      CaseIOCBulkResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseIOCBulkResponse && added == other.added;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, added.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseIOCBulkResponse')
          ..add('added', added))
        .toString();
  }
}

class CaseIOCBulkResponseBuilder
    implements Builder<CaseIOCBulkResponse, CaseIOCBulkResponseBuilder> {
  _$CaseIOCBulkResponse? _$v;

  int? _added;
  int? get added => _$this._added;
  set added(int? added) => _$this._added = added;

  CaseIOCBulkResponseBuilder() {
    CaseIOCBulkResponse._defaults(this);
  }

  CaseIOCBulkResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _added = $v.added;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseIOCBulkResponse other) {
    _$v = other as _$CaseIOCBulkResponse;
  }

  @override
  void update(void Function(CaseIOCBulkResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseIOCBulkResponse build() => _build();

  _$CaseIOCBulkResponse _build() {
    final _$result = _$v ??
        _$CaseIOCBulkResponse._(
          added: BuiltValueNullFieldError.checkNotNull(
              added, r'CaseIOCBulkResponse', 'added'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
