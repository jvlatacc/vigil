// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_list_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseListResponse extends CaseListResponse {
  @override
  final BuiltList<CaseQueueItem> cases;
  @override
  final bool hasMore;
  @override
  final int limit;
  @override
  final int offset;
  @override
  final CaseQueueStrip strip;
  @override
  final int total;

  factory _$CaseListResponse(
          [void Function(CaseListResponseBuilder)? updates]) =>
      (CaseListResponseBuilder()..update(updates))._build();

  _$CaseListResponse._(
      {required this.cases,
      required this.hasMore,
      required this.limit,
      required this.offset,
      required this.strip,
      required this.total})
      : super._();
  @override
  CaseListResponse rebuild(void Function(CaseListResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseListResponseBuilder toBuilder() =>
      CaseListResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseListResponse &&
        cases == other.cases &&
        hasMore == other.hasMore &&
        limit == other.limit &&
        offset == other.offset &&
        strip == other.strip &&
        total == other.total;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, cases.hashCode);
    _$hash = $jc(_$hash, hasMore.hashCode);
    _$hash = $jc(_$hash, limit.hashCode);
    _$hash = $jc(_$hash, offset.hashCode);
    _$hash = $jc(_$hash, strip.hashCode);
    _$hash = $jc(_$hash, total.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseListResponse')
          ..add('cases', cases)
          ..add('hasMore', hasMore)
          ..add('limit', limit)
          ..add('offset', offset)
          ..add('strip', strip)
          ..add('total', total))
        .toString();
  }
}

class CaseListResponseBuilder
    implements Builder<CaseListResponse, CaseListResponseBuilder> {
  _$CaseListResponse? _$v;

  ListBuilder<CaseQueueItem>? _cases;
  ListBuilder<CaseQueueItem> get cases =>
      _$this._cases ??= ListBuilder<CaseQueueItem>();
  set cases(ListBuilder<CaseQueueItem>? cases) => _$this._cases = cases;

  bool? _hasMore;
  bool? get hasMore => _$this._hasMore;
  set hasMore(bool? hasMore) => _$this._hasMore = hasMore;

  int? _limit;
  int? get limit => _$this._limit;
  set limit(int? limit) => _$this._limit = limit;

  int? _offset;
  int? get offset => _$this._offset;
  set offset(int? offset) => _$this._offset = offset;

  CaseQueueStripBuilder? _strip;
  CaseQueueStripBuilder get strip => _$this._strip ??= CaseQueueStripBuilder();
  set strip(CaseQueueStripBuilder? strip) => _$this._strip = strip;

  int? _total;
  int? get total => _$this._total;
  set total(int? total) => _$this._total = total;

  CaseListResponseBuilder() {
    CaseListResponse._defaults(this);
  }

  CaseListResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _cases = $v.cases.toBuilder();
      _hasMore = $v.hasMore;
      _limit = $v.limit;
      _offset = $v.offset;
      _strip = $v.strip.toBuilder();
      _total = $v.total;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseListResponse other) {
    _$v = other as _$CaseListResponse;
  }

  @override
  void update(void Function(CaseListResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseListResponse build() => _build();

  _$CaseListResponse _build() {
    _$CaseListResponse _$result;
    try {
      _$result = _$v ??
          _$CaseListResponse._(
            cases: cases.build(),
            hasMore: BuiltValueNullFieldError.checkNotNull(
                hasMore, r'CaseListResponse', 'hasMore'),
            limit: BuiltValueNullFieldError.checkNotNull(
                limit, r'CaseListResponse', 'limit'),
            offset: BuiltValueNullFieldError.checkNotNull(
                offset, r'CaseListResponse', 'offset'),
            strip: strip.build(),
            total: BuiltValueNullFieldError.checkNotNull(
                total, r'CaseListResponse', 'total'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'cases';
        cases.build();

        _$failedField = 'strip';
        strip.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseListResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
