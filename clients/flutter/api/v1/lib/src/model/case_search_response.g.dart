// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_search_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseSearchResponse extends CaseSearchResponse {
  @override
  final bool hasMore;
  @override
  final int limit;
  @override
  final int offset;
  @override
  final BuiltList<CaseSchema> results;
  @override
  final int total;

  factory _$CaseSearchResponse(
          [void Function(CaseSearchResponseBuilder)? updates]) =>
      (CaseSearchResponseBuilder()..update(updates))._build();

  _$CaseSearchResponse._(
      {required this.hasMore,
      required this.limit,
      required this.offset,
      required this.results,
      required this.total})
      : super._();
  @override
  CaseSearchResponse rebuild(
          void Function(CaseSearchResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseSearchResponseBuilder toBuilder() =>
      CaseSearchResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseSearchResponse &&
        hasMore == other.hasMore &&
        limit == other.limit &&
        offset == other.offset &&
        results == other.results &&
        total == other.total;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, hasMore.hashCode);
    _$hash = $jc(_$hash, limit.hashCode);
    _$hash = $jc(_$hash, offset.hashCode);
    _$hash = $jc(_$hash, results.hashCode);
    _$hash = $jc(_$hash, total.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseSearchResponse')
          ..add('hasMore', hasMore)
          ..add('limit', limit)
          ..add('offset', offset)
          ..add('results', results)
          ..add('total', total))
        .toString();
  }
}

class CaseSearchResponseBuilder
    implements Builder<CaseSearchResponse, CaseSearchResponseBuilder> {
  _$CaseSearchResponse? _$v;

  bool? _hasMore;
  bool? get hasMore => _$this._hasMore;
  set hasMore(bool? hasMore) => _$this._hasMore = hasMore;

  int? _limit;
  int? get limit => _$this._limit;
  set limit(int? limit) => _$this._limit = limit;

  int? _offset;
  int? get offset => _$this._offset;
  set offset(int? offset) => _$this._offset = offset;

  ListBuilder<CaseSchema>? _results;
  ListBuilder<CaseSchema> get results =>
      _$this._results ??= ListBuilder<CaseSchema>();
  set results(ListBuilder<CaseSchema>? results) => _$this._results = results;

  int? _total;
  int? get total => _$this._total;
  set total(int? total) => _$this._total = total;

  CaseSearchResponseBuilder() {
    CaseSearchResponse._defaults(this);
  }

  CaseSearchResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _hasMore = $v.hasMore;
      _limit = $v.limit;
      _offset = $v.offset;
      _results = $v.results.toBuilder();
      _total = $v.total;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseSearchResponse other) {
    _$v = other as _$CaseSearchResponse;
  }

  @override
  void update(void Function(CaseSearchResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseSearchResponse build() => _build();

  _$CaseSearchResponse _build() {
    _$CaseSearchResponse _$result;
    try {
      _$result = _$v ??
          _$CaseSearchResponse._(
            hasMore: BuiltValueNullFieldError.checkNotNull(
                hasMore, r'CaseSearchResponse', 'hasMore'),
            limit: BuiltValueNullFieldError.checkNotNull(
                limit, r'CaseSearchResponse', 'limit'),
            offset: BuiltValueNullFieldError.checkNotNull(
                offset, r'CaseSearchResponse', 'offset'),
            results: results.build(),
            total: BuiltValueNullFieldError.checkNotNull(
                total, r'CaseSearchResponse', 'total'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'results';
        results.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseSearchResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
