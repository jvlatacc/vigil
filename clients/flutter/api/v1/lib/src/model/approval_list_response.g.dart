// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'approval_list_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ApprovalListResponse extends ApprovalListResponse {
  @override
  final BuiltList<PendingActionResponse>? actions;
  @override
  final int count;

  factory _$ApprovalListResponse(
          [void Function(ApprovalListResponseBuilder)? updates]) =>
      (ApprovalListResponseBuilder()..update(updates))._build();

  _$ApprovalListResponse._({this.actions, required this.count}) : super._();
  @override
  ApprovalListResponse rebuild(
          void Function(ApprovalListResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ApprovalListResponseBuilder toBuilder() =>
      ApprovalListResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ApprovalListResponse &&
        actions == other.actions &&
        count == other.count;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, actions.hashCode);
    _$hash = $jc(_$hash, count.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ApprovalListResponse')
          ..add('actions', actions)
          ..add('count', count))
        .toString();
  }
}

class ApprovalListResponseBuilder
    implements Builder<ApprovalListResponse, ApprovalListResponseBuilder> {
  _$ApprovalListResponse? _$v;

  ListBuilder<PendingActionResponse>? _actions;
  ListBuilder<PendingActionResponse> get actions =>
      _$this._actions ??= ListBuilder<PendingActionResponse>();
  set actions(ListBuilder<PendingActionResponse>? actions) =>
      _$this._actions = actions;

  int? _count;
  int? get count => _$this._count;
  set count(int? count) => _$this._count = count;

  ApprovalListResponseBuilder() {
    ApprovalListResponse._defaults(this);
  }

  ApprovalListResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _actions = $v.actions?.toBuilder();
      _count = $v.count;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ApprovalListResponse other) {
    _$v = other as _$ApprovalListResponse;
  }

  @override
  void update(void Function(ApprovalListResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ApprovalListResponse build() => _build();

  _$ApprovalListResponse _build() {
    _$ApprovalListResponse _$result;
    try {
      _$result = _$v ??
          _$ApprovalListResponse._(
            actions: _actions?.build(),
            count: BuiltValueNullFieldError.checkNotNull(
                count, r'ApprovalListResponse', 'count'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'actions';
        _actions?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ApprovalListResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
