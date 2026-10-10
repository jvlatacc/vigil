// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'pending_action_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$PendingActionResponse extends PendingActionResponse {
  @override
  final String? actionId;
  @override
  final String? actionType;
  @override
  final String? approvedAt;
  @override
  final String? approvedBy;
  @override
  final num? confidence;
  @override
  final String? createdAt;
  @override
  final String? createdBy;
  @override
  final String? description;
  @override
  final AnyOf? evidence;
  @override
  final String? executedAt;
  @override
  final AnyOf? executionResult;
  @override
  final String? idempotencyKey;
  @override
  final AnyOf? parameters;
  @override
  final String? reason;
  @override
  final String? rejectionReason;
  @override
  final bool? requiresApproval;
  @override
  final String? reversibility;
  @override
  final String? status;
  @override
  final AnyOf? target;
  @override
  final String? title;
  @override
  final String? workflowPhaseId;
  @override
  final String? workflowRunId;

  factory _$PendingActionResponse(
          [void Function(PendingActionResponseBuilder)? updates]) =>
      (PendingActionResponseBuilder()..update(updates))._build();

  _$PendingActionResponse._(
      {this.actionId,
      this.actionType,
      this.approvedAt,
      this.approvedBy,
      this.confidence,
      this.createdAt,
      this.createdBy,
      this.description,
      this.evidence,
      this.executedAt,
      this.executionResult,
      this.idempotencyKey,
      this.parameters,
      this.reason,
      this.rejectionReason,
      this.requiresApproval,
      this.reversibility,
      this.status,
      this.target,
      this.title,
      this.workflowPhaseId,
      this.workflowRunId})
      : super._();
  @override
  PendingActionResponse rebuild(
          void Function(PendingActionResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  PendingActionResponseBuilder toBuilder() =>
      PendingActionResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is PendingActionResponse &&
        actionId == other.actionId &&
        actionType == other.actionType &&
        approvedAt == other.approvedAt &&
        approvedBy == other.approvedBy &&
        confidence == other.confidence &&
        createdAt == other.createdAt &&
        createdBy == other.createdBy &&
        description == other.description &&
        evidence == other.evidence &&
        executedAt == other.executedAt &&
        executionResult == other.executionResult &&
        idempotencyKey == other.idempotencyKey &&
        parameters == other.parameters &&
        reason == other.reason &&
        rejectionReason == other.rejectionReason &&
        requiresApproval == other.requiresApproval &&
        reversibility == other.reversibility &&
        status == other.status &&
        target == other.target &&
        title == other.title &&
        workflowPhaseId == other.workflowPhaseId &&
        workflowRunId == other.workflowRunId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, actionId.hashCode);
    _$hash = $jc(_$hash, actionType.hashCode);
    _$hash = $jc(_$hash, approvedAt.hashCode);
    _$hash = $jc(_$hash, approvedBy.hashCode);
    _$hash = $jc(_$hash, confidence.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, createdBy.hashCode);
    _$hash = $jc(_$hash, description.hashCode);
    _$hash = $jc(_$hash, evidence.hashCode);
    _$hash = $jc(_$hash, executedAt.hashCode);
    _$hash = $jc(_$hash, executionResult.hashCode);
    _$hash = $jc(_$hash, idempotencyKey.hashCode);
    _$hash = $jc(_$hash, parameters.hashCode);
    _$hash = $jc(_$hash, reason.hashCode);
    _$hash = $jc(_$hash, rejectionReason.hashCode);
    _$hash = $jc(_$hash, requiresApproval.hashCode);
    _$hash = $jc(_$hash, reversibility.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, target.hashCode);
    _$hash = $jc(_$hash, title.hashCode);
    _$hash = $jc(_$hash, workflowPhaseId.hashCode);
    _$hash = $jc(_$hash, workflowRunId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'PendingActionResponse')
          ..add('actionId', actionId)
          ..add('actionType', actionType)
          ..add('approvedAt', approvedAt)
          ..add('approvedBy', approvedBy)
          ..add('confidence', confidence)
          ..add('createdAt', createdAt)
          ..add('createdBy', createdBy)
          ..add('description', description)
          ..add('evidence', evidence)
          ..add('executedAt', executedAt)
          ..add('executionResult', executionResult)
          ..add('idempotencyKey', idempotencyKey)
          ..add('parameters', parameters)
          ..add('reason', reason)
          ..add('rejectionReason', rejectionReason)
          ..add('requiresApproval', requiresApproval)
          ..add('reversibility', reversibility)
          ..add('status', status)
          ..add('target', target)
          ..add('title', title)
          ..add('workflowPhaseId', workflowPhaseId)
          ..add('workflowRunId', workflowRunId))
        .toString();
  }
}

class PendingActionResponseBuilder
    implements Builder<PendingActionResponse, PendingActionResponseBuilder> {
  _$PendingActionResponse? _$v;

  String? _actionId;
  String? get actionId => _$this._actionId;
  set actionId(String? actionId) => _$this._actionId = actionId;

  String? _actionType;
  String? get actionType => _$this._actionType;
  set actionType(String? actionType) => _$this._actionType = actionType;

  String? _approvedAt;
  String? get approvedAt => _$this._approvedAt;
  set approvedAt(String? approvedAt) => _$this._approvedAt = approvedAt;

  String? _approvedBy;
  String? get approvedBy => _$this._approvedBy;
  set approvedBy(String? approvedBy) => _$this._approvedBy = approvedBy;

  num? _confidence;
  num? get confidence => _$this._confidence;
  set confidence(num? confidence) => _$this._confidence = confidence;

  String? _createdAt;
  String? get createdAt => _$this._createdAt;
  set createdAt(String? createdAt) => _$this._createdAt = createdAt;

  String? _createdBy;
  String? get createdBy => _$this._createdBy;
  set createdBy(String? createdBy) => _$this._createdBy = createdBy;

  String? _description;
  String? get description => _$this._description;
  set description(String? description) => _$this._description = description;

  AnyOf? _evidence;
  AnyOf? get evidence => _$this._evidence;
  set evidence(AnyOf? evidence) => _$this._evidence = evidence;

  String? _executedAt;
  String? get executedAt => _$this._executedAt;
  set executedAt(String? executedAt) => _$this._executedAt = executedAt;

  AnyOf? _executionResult;
  AnyOf? get executionResult => _$this._executionResult;
  set executionResult(AnyOf? executionResult) =>
      _$this._executionResult = executionResult;

  String? _idempotencyKey;
  String? get idempotencyKey => _$this._idempotencyKey;
  set idempotencyKey(String? idempotencyKey) =>
      _$this._idempotencyKey = idempotencyKey;

  AnyOf? _parameters;
  AnyOf? get parameters => _$this._parameters;
  set parameters(AnyOf? parameters) => _$this._parameters = parameters;

  String? _reason;
  String? get reason => _$this._reason;
  set reason(String? reason) => _$this._reason = reason;

  String? _rejectionReason;
  String? get rejectionReason => _$this._rejectionReason;
  set rejectionReason(String? rejectionReason) =>
      _$this._rejectionReason = rejectionReason;

  bool? _requiresApproval;
  bool? get requiresApproval => _$this._requiresApproval;
  set requiresApproval(bool? requiresApproval) =>
      _$this._requiresApproval = requiresApproval;

  String? _reversibility;
  String? get reversibility => _$this._reversibility;
  set reversibility(String? reversibility) =>
      _$this._reversibility = reversibility;

  String? _status;
  String? get status => _$this._status;
  set status(String? status) => _$this._status = status;

  AnyOf? _target;
  AnyOf? get target => _$this._target;
  set target(AnyOf? target) => _$this._target = target;

  String? _title;
  String? get title => _$this._title;
  set title(String? title) => _$this._title = title;

  String? _workflowPhaseId;
  String? get workflowPhaseId => _$this._workflowPhaseId;
  set workflowPhaseId(String? workflowPhaseId) =>
      _$this._workflowPhaseId = workflowPhaseId;

  String? _workflowRunId;
  String? get workflowRunId => _$this._workflowRunId;
  set workflowRunId(String? workflowRunId) =>
      _$this._workflowRunId = workflowRunId;

  PendingActionResponseBuilder() {
    PendingActionResponse._defaults(this);
  }

  PendingActionResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _actionId = $v.actionId;
      _actionType = $v.actionType;
      _approvedAt = $v.approvedAt;
      _approvedBy = $v.approvedBy;
      _confidence = $v.confidence;
      _createdAt = $v.createdAt;
      _createdBy = $v.createdBy;
      _description = $v.description;
      _evidence = $v.evidence;
      _executedAt = $v.executedAt;
      _executionResult = $v.executionResult;
      _idempotencyKey = $v.idempotencyKey;
      _parameters = $v.parameters;
      _reason = $v.reason;
      _rejectionReason = $v.rejectionReason;
      _requiresApproval = $v.requiresApproval;
      _reversibility = $v.reversibility;
      _status = $v.status;
      _target = $v.target;
      _title = $v.title;
      _workflowPhaseId = $v.workflowPhaseId;
      _workflowRunId = $v.workflowRunId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(PendingActionResponse other) {
    _$v = other as _$PendingActionResponse;
  }

  @override
  void update(void Function(PendingActionResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  PendingActionResponse build() => _build();

  _$PendingActionResponse _build() {
    final _$result = _$v ??
        _$PendingActionResponse._(
          actionId: actionId,
          actionType: actionType,
          approvedAt: approvedAt,
          approvedBy: approvedBy,
          confidence: confidence,
          createdAt: createdAt,
          createdBy: createdBy,
          description: description,
          evidence: evidence,
          executedAt: executedAt,
          executionResult: executionResult,
          idempotencyKey: idempotencyKey,
          parameters: parameters,
          reason: reason,
          rejectionReason: rejectionReason,
          requiresApproval: requiresApproval,
          reversibility: reversibility,
          status: status,
          target: target,
          title: title,
          workflowPhaseId: workflowPhaseId,
          workflowRunId: workflowRunId,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
