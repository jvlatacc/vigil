// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_summary_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseSummaryResponse extends CaseSummaryResponse {
  @override
  final BuiltMap<String, int> byPriority;
  @override
  final BuiltMap<String, int> byStatus;
  @override
  final int total;

  factory _$CaseSummaryResponse(
          [void Function(CaseSummaryResponseBuilder)? updates]) =>
      (CaseSummaryResponseBuilder()..update(updates))._build();

  _$CaseSummaryResponse._(
      {required this.byPriority, required this.byStatus, required this.total})
      : super._();
  @override
  CaseSummaryResponse rebuild(
          void Function(CaseSummaryResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseSummaryResponseBuilder toBuilder() =>
      CaseSummaryResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseSummaryResponse &&
        byPriority == other.byPriority &&
        byStatus == other.byStatus &&
        total == other.total;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, byPriority.hashCode);
    _$hash = $jc(_$hash, byStatus.hashCode);
    _$hash = $jc(_$hash, total.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseSummaryResponse')
          ..add('byPriority', byPriority)
          ..add('byStatus', byStatus)
          ..add('total', total))
        .toString();
  }
}

class CaseSummaryResponseBuilder
    implements Builder<CaseSummaryResponse, CaseSummaryResponseBuilder> {
  _$CaseSummaryResponse? _$v;

  MapBuilder<String, int>? _byPriority;
  MapBuilder<String, int> get byPriority =>
      _$this._byPriority ??= MapBuilder<String, int>();
  set byPriority(MapBuilder<String, int>? byPriority) =>
      _$this._byPriority = byPriority;

  MapBuilder<String, int>? _byStatus;
  MapBuilder<String, int> get byStatus =>
      _$this._byStatus ??= MapBuilder<String, int>();
  set byStatus(MapBuilder<String, int>? byStatus) =>
      _$this._byStatus = byStatus;

  int? _total;
  int? get total => _$this._total;
  set total(int? total) => _$this._total = total;

  CaseSummaryResponseBuilder() {
    CaseSummaryResponse._defaults(this);
  }

  CaseSummaryResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _byPriority = $v.byPriority.toBuilder();
      _byStatus = $v.byStatus.toBuilder();
      _total = $v.total;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseSummaryResponse other) {
    _$v = other as _$CaseSummaryResponse;
  }

  @override
  void update(void Function(CaseSummaryResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseSummaryResponse build() => _build();

  _$CaseSummaryResponse _build() {
    _$CaseSummaryResponse _$result;
    try {
      _$result = _$v ??
          _$CaseSummaryResponse._(
            byPriority: byPriority.build(),
            byStatus: byStatus.build(),
            total: BuiltValueNullFieldError.checkNotNull(
                total, r'CaseSummaryResponse', 'total'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'byPriority';
        byPriority.build();
        _$failedField = 'byStatus';
        byStatus.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseSummaryResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
