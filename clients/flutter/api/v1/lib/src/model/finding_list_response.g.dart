// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'finding_list_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$FindingListResponse extends FindingListResponse {
  @override
  final BuiltList<FindingRecord>? findings;
  @override
  final bool hasMore;
  @override
  final int limit;
  @override
  final int offset;
  @override
  final int total;

  factory _$FindingListResponse(
          [void Function(FindingListResponseBuilder)? updates]) =>
      (FindingListResponseBuilder()..update(updates))._build();

  _$FindingListResponse._(
      {this.findings,
      required this.hasMore,
      required this.limit,
      required this.offset,
      required this.total})
      : super._();
  @override
  FindingListResponse rebuild(
          void Function(FindingListResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  FindingListResponseBuilder toBuilder() =>
      FindingListResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is FindingListResponse &&
        findings == other.findings &&
        hasMore == other.hasMore &&
        limit == other.limit &&
        offset == other.offset &&
        total == other.total;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, findings.hashCode);
    _$hash = $jc(_$hash, hasMore.hashCode);
    _$hash = $jc(_$hash, limit.hashCode);
    _$hash = $jc(_$hash, offset.hashCode);
    _$hash = $jc(_$hash, total.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'FindingListResponse')
          ..add('findings', findings)
          ..add('hasMore', hasMore)
          ..add('limit', limit)
          ..add('offset', offset)
          ..add('total', total))
        .toString();
  }
}

class FindingListResponseBuilder
    implements Builder<FindingListResponse, FindingListResponseBuilder> {
  _$FindingListResponse? _$v;

  ListBuilder<FindingRecord>? _findings;
  ListBuilder<FindingRecord> get findings =>
      _$this._findings ??= ListBuilder<FindingRecord>();
  set findings(ListBuilder<FindingRecord>? findings) =>
      _$this._findings = findings;

  bool? _hasMore;
  bool? get hasMore => _$this._hasMore;
  set hasMore(bool? hasMore) => _$this._hasMore = hasMore;

  int? _limit;
  int? get limit => _$this._limit;
  set limit(int? limit) => _$this._limit = limit;

  int? _offset;
  int? get offset => _$this._offset;
  set offset(int? offset) => _$this._offset = offset;

  int? _total;
  int? get total => _$this._total;
  set total(int? total) => _$this._total = total;

  FindingListResponseBuilder() {
    FindingListResponse._defaults(this);
  }

  FindingListResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _findings = $v.findings?.toBuilder();
      _hasMore = $v.hasMore;
      _limit = $v.limit;
      _offset = $v.offset;
      _total = $v.total;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(FindingListResponse other) {
    _$v = other as _$FindingListResponse;
  }

  @override
  void update(void Function(FindingListResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  FindingListResponse build() => _build();

  _$FindingListResponse _build() {
    _$FindingListResponse _$result;
    try {
      _$result = _$v ??
          _$FindingListResponse._(
            findings: _findings?.build(),
            hasMore: BuiltValueNullFieldError.checkNotNull(
                hasMore, r'FindingListResponse', 'hasMore'),
            limit: BuiltValueNullFieldError.checkNotNull(
                limit, r'FindingListResponse', 'limit'),
            offset: BuiltValueNullFieldError.checkNotNull(
                offset, r'FindingListResponse', 'offset'),
            total: BuiltValueNullFieldError.checkNotNull(
                total, r'FindingListResponse', 'total'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'findings';
        _findings?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'FindingListResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
