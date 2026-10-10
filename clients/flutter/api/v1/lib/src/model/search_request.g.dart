// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'search_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$SearchRequest extends SearchRequest {
  @override
  final BuiltList<String>? assignee;
  @override
  final DateTime? createdAfter;
  @override
  final DateTime? createdBefore;
  @override
  final int? limit;
  @override
  final BuiltList<String>? mitreTechniques;
  @override
  final int? offset;
  @override
  final BuiltList<String>? priority;
  @override
  final String? queryText;
  @override
  final BuiltList<String>? status;
  @override
  final BuiltList<String>? tags;

  factory _$SearchRequest([void Function(SearchRequestBuilder)? updates]) =>
      (SearchRequestBuilder()..update(updates))._build();

  _$SearchRequest._(
      {this.assignee,
      this.createdAfter,
      this.createdBefore,
      this.limit,
      this.mitreTechniques,
      this.offset,
      this.priority,
      this.queryText,
      this.status,
      this.tags})
      : super._();
  @override
  SearchRequest rebuild(void Function(SearchRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  SearchRequestBuilder toBuilder() => SearchRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is SearchRequest &&
        assignee == other.assignee &&
        createdAfter == other.createdAfter &&
        createdBefore == other.createdBefore &&
        limit == other.limit &&
        mitreTechniques == other.mitreTechniques &&
        offset == other.offset &&
        priority == other.priority &&
        queryText == other.queryText &&
        status == other.status &&
        tags == other.tags;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, assignee.hashCode);
    _$hash = $jc(_$hash, createdAfter.hashCode);
    _$hash = $jc(_$hash, createdBefore.hashCode);
    _$hash = $jc(_$hash, limit.hashCode);
    _$hash = $jc(_$hash, mitreTechniques.hashCode);
    _$hash = $jc(_$hash, offset.hashCode);
    _$hash = $jc(_$hash, priority.hashCode);
    _$hash = $jc(_$hash, queryText.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, tags.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'SearchRequest')
          ..add('assignee', assignee)
          ..add('createdAfter', createdAfter)
          ..add('createdBefore', createdBefore)
          ..add('limit', limit)
          ..add('mitreTechniques', mitreTechniques)
          ..add('offset', offset)
          ..add('priority', priority)
          ..add('queryText', queryText)
          ..add('status', status)
          ..add('tags', tags))
        .toString();
  }
}

class SearchRequestBuilder
    implements Builder<SearchRequest, SearchRequestBuilder> {
  _$SearchRequest? _$v;

  ListBuilder<String>? _assignee;
  ListBuilder<String> get assignee =>
      _$this._assignee ??= ListBuilder<String>();
  set assignee(ListBuilder<String>? assignee) => _$this._assignee = assignee;

  DateTime? _createdAfter;
  DateTime? get createdAfter => _$this._createdAfter;
  set createdAfter(DateTime? createdAfter) =>
      _$this._createdAfter = createdAfter;

  DateTime? _createdBefore;
  DateTime? get createdBefore => _$this._createdBefore;
  set createdBefore(DateTime? createdBefore) =>
      _$this._createdBefore = createdBefore;

  int? _limit;
  int? get limit => _$this._limit;
  set limit(int? limit) => _$this._limit = limit;

  ListBuilder<String>? _mitreTechniques;
  ListBuilder<String> get mitreTechniques =>
      _$this._mitreTechniques ??= ListBuilder<String>();
  set mitreTechniques(ListBuilder<String>? mitreTechniques) =>
      _$this._mitreTechniques = mitreTechniques;

  int? _offset;
  int? get offset => _$this._offset;
  set offset(int? offset) => _$this._offset = offset;

  ListBuilder<String>? _priority;
  ListBuilder<String> get priority =>
      _$this._priority ??= ListBuilder<String>();
  set priority(ListBuilder<String>? priority) => _$this._priority = priority;

  String? _queryText;
  String? get queryText => _$this._queryText;
  set queryText(String? queryText) => _$this._queryText = queryText;

  ListBuilder<String>? _status;
  ListBuilder<String> get status => _$this._status ??= ListBuilder<String>();
  set status(ListBuilder<String>? status) => _$this._status = status;

  ListBuilder<String>? _tags;
  ListBuilder<String> get tags => _$this._tags ??= ListBuilder<String>();
  set tags(ListBuilder<String>? tags) => _$this._tags = tags;

  SearchRequestBuilder() {
    SearchRequest._defaults(this);
  }

  SearchRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _assignee = $v.assignee?.toBuilder();
      _createdAfter = $v.createdAfter;
      _createdBefore = $v.createdBefore;
      _limit = $v.limit;
      _mitreTechniques = $v.mitreTechniques?.toBuilder();
      _offset = $v.offset;
      _priority = $v.priority?.toBuilder();
      _queryText = $v.queryText;
      _status = $v.status?.toBuilder();
      _tags = $v.tags?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(SearchRequest other) {
    _$v = other as _$SearchRequest;
  }

  @override
  void update(void Function(SearchRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  SearchRequest build() => _build();

  _$SearchRequest _build() {
    _$SearchRequest _$result;
    try {
      _$result = _$v ??
          _$SearchRequest._(
            assignee: _assignee?.build(),
            createdAfter: createdAfter,
            createdBefore: createdBefore,
            limit: limit,
            mitreTechniques: _mitreTechniques?.build(),
            offset: offset,
            priority: _priority?.build(),
            queryText: queryText,
            status: _status?.build(),
            tags: _tags?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'assignee';
        _assignee?.build();

        _$failedField = 'mitreTechniques';
        _mitreTechniques?.build();

        _$failedField = 'priority';
        _priority?.build();

        _$failedField = 'status';
        _status?.build();
        _$failedField = 'tags';
        _tags?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'SearchRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
