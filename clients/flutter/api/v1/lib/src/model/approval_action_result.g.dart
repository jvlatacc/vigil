// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'approval_action_result.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ApprovalActionResult extends ApprovalActionResult {
  @override
  final PendingActionResponse action;
  @override
  final BuiltMap<String, JsonObject?>? resumeResult;

  factory _$ApprovalActionResult(
          [void Function(ApprovalActionResultBuilder)? updates]) =>
      (ApprovalActionResultBuilder()..update(updates))._build();

  _$ApprovalActionResult._({required this.action, this.resumeResult})
      : super._();
  @override
  ApprovalActionResult rebuild(
          void Function(ApprovalActionResultBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ApprovalActionResultBuilder toBuilder() =>
      ApprovalActionResultBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ApprovalActionResult &&
        action == other.action &&
        resumeResult == other.resumeResult;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, action.hashCode);
    _$hash = $jc(_$hash, resumeResult.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ApprovalActionResult')
          ..add('action', action)
          ..add('resumeResult', resumeResult))
        .toString();
  }
}

class ApprovalActionResultBuilder
    implements Builder<ApprovalActionResult, ApprovalActionResultBuilder> {
  _$ApprovalActionResult? _$v;

  PendingActionResponseBuilder? _action;
  PendingActionResponseBuilder get action =>
      _$this._action ??= PendingActionResponseBuilder();
  set action(PendingActionResponseBuilder? action) => _$this._action = action;

  MapBuilder<String, JsonObject?>? _resumeResult;
  MapBuilder<String, JsonObject?> get resumeResult =>
      _$this._resumeResult ??= MapBuilder<String, JsonObject?>();
  set resumeResult(MapBuilder<String, JsonObject?>? resumeResult) =>
      _$this._resumeResult = resumeResult;

  ApprovalActionResultBuilder() {
    ApprovalActionResult._defaults(this);
  }

  ApprovalActionResultBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _action = $v.action.toBuilder();
      _resumeResult = $v.resumeResult?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ApprovalActionResult other) {
    _$v = other as _$ApprovalActionResult;
  }

  @override
  void update(void Function(ApprovalActionResultBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ApprovalActionResult build() => _build();

  _$ApprovalActionResult _build() {
    _$ApprovalActionResult _$result;
    try {
      _$result = _$v ??
          _$ApprovalActionResult._(
            action: action.build(),
            resumeResult: _resumeResult?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'action';
        action.build();
        _$failedField = 'resumeResult';
        _resumeResult?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ApprovalActionResult', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
