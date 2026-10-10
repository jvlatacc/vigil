// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'findings_summary_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$FindingsSummaryResponse extends FindingsSummaryResponse {
  @override
  final BuiltMap<String, int>? byDataSource;
  @override
  final BuiltMap<String, int>? bySeverity;
  @override
  final int total;

  factory _$FindingsSummaryResponse(
          [void Function(FindingsSummaryResponseBuilder)? updates]) =>
      (FindingsSummaryResponseBuilder()..update(updates))._build();

  _$FindingsSummaryResponse._(
      {this.byDataSource, this.bySeverity, required this.total})
      : super._();
  @override
  FindingsSummaryResponse rebuild(
          void Function(FindingsSummaryResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  FindingsSummaryResponseBuilder toBuilder() =>
      FindingsSummaryResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is FindingsSummaryResponse &&
        byDataSource == other.byDataSource &&
        bySeverity == other.bySeverity &&
        total == other.total;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, byDataSource.hashCode);
    _$hash = $jc(_$hash, bySeverity.hashCode);
    _$hash = $jc(_$hash, total.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'FindingsSummaryResponse')
          ..add('byDataSource', byDataSource)
          ..add('bySeverity', bySeverity)
          ..add('total', total))
        .toString();
  }
}

class FindingsSummaryResponseBuilder
    implements
        Builder<FindingsSummaryResponse, FindingsSummaryResponseBuilder> {
  _$FindingsSummaryResponse? _$v;

  MapBuilder<String, int>? _byDataSource;
  MapBuilder<String, int> get byDataSource =>
      _$this._byDataSource ??= MapBuilder<String, int>();
  set byDataSource(MapBuilder<String, int>? byDataSource) =>
      _$this._byDataSource = byDataSource;

  MapBuilder<String, int>? _bySeverity;
  MapBuilder<String, int> get bySeverity =>
      _$this._bySeverity ??= MapBuilder<String, int>();
  set bySeverity(MapBuilder<String, int>? bySeverity) =>
      _$this._bySeverity = bySeverity;

  int? _total;
  int? get total => _$this._total;
  set total(int? total) => _$this._total = total;

  FindingsSummaryResponseBuilder() {
    FindingsSummaryResponse._defaults(this);
  }

  FindingsSummaryResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _byDataSource = $v.byDataSource?.toBuilder();
      _bySeverity = $v.bySeverity?.toBuilder();
      _total = $v.total;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(FindingsSummaryResponse other) {
    _$v = other as _$FindingsSummaryResponse;
  }

  @override
  void update(void Function(FindingsSummaryResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  FindingsSummaryResponse build() => _build();

  _$FindingsSummaryResponse _build() {
    _$FindingsSummaryResponse _$result;
    try {
      _$result = _$v ??
          _$FindingsSummaryResponse._(
            byDataSource: _byDataSource?.build(),
            bySeverity: _bySeverity?.build(),
            total: BuiltValueNullFieldError.checkNotNull(
                total, r'FindingsSummaryResponse', 'total'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'byDataSource';
        _byDataSource?.build();
        _$failedField = 'bySeverity';
        _bySeverity?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'FindingsSummaryResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
