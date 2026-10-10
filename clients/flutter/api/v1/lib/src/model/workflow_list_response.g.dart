// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'workflow_list_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$WorkflowListResponse extends WorkflowListResponse {
  @override
  final int count;
  @override
  final BuiltList<BuiltMap<String, JsonObject?>>? workflows;

  factory _$WorkflowListResponse(
          [void Function(WorkflowListResponseBuilder)? updates]) =>
      (WorkflowListResponseBuilder()..update(updates))._build();

  _$WorkflowListResponse._({required this.count, this.workflows}) : super._();
  @override
  WorkflowListResponse rebuild(
          void Function(WorkflowListResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  WorkflowListResponseBuilder toBuilder() =>
      WorkflowListResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is WorkflowListResponse &&
        count == other.count &&
        workflows == other.workflows;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, count.hashCode);
    _$hash = $jc(_$hash, workflows.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'WorkflowListResponse')
          ..add('count', count)
          ..add('workflows', workflows))
        .toString();
  }
}

class WorkflowListResponseBuilder
    implements Builder<WorkflowListResponse, WorkflowListResponseBuilder> {
  _$WorkflowListResponse? _$v;

  int? _count;
  int? get count => _$this._count;
  set count(int? count) => _$this._count = count;

  ListBuilder<BuiltMap<String, JsonObject?>>? _workflows;
  ListBuilder<BuiltMap<String, JsonObject?>> get workflows =>
      _$this._workflows ??= ListBuilder<BuiltMap<String, JsonObject?>>();
  set workflows(ListBuilder<BuiltMap<String, JsonObject?>>? workflows) =>
      _$this._workflows = workflows;

  WorkflowListResponseBuilder() {
    WorkflowListResponse._defaults(this);
  }

  WorkflowListResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _count = $v.count;
      _workflows = $v.workflows?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(WorkflowListResponse other) {
    _$v = other as _$WorkflowListResponse;
  }

  @override
  void update(void Function(WorkflowListResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  WorkflowListResponse build() => _build();

  _$WorkflowListResponse _build() {
    _$WorkflowListResponse _$result;
    try {
      _$result = _$v ??
          _$WorkflowListResponse._(
            count: BuiltValueNullFieldError.checkNotNull(
                count, r'WorkflowListResponse', 'count'),
            workflows: _workflows?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'workflows';
        _workflows?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'WorkflowListResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
