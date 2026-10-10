// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_investigation_ref.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseInvestigationRef extends CaseInvestigationRef {
  @override
  final String? budgetHealth;
  @override
  final num? costUsd;
  @override
  final String? createdAt;
  @override
  final String? investigationId;
  @override
  final int? iterationCount;
  @override
  final bool? live;
  @override
  final num? maxCostUsd;
  @override
  final String runId;
  @override
  final String status;
  @override
  final String workflowId;

  factory _$CaseInvestigationRef(
          [void Function(CaseInvestigationRefBuilder)? updates]) =>
      (CaseInvestigationRefBuilder()..update(updates))._build();

  _$CaseInvestigationRef._(
      {this.budgetHealth,
      this.costUsd,
      this.createdAt,
      this.investigationId,
      this.iterationCount,
      this.live,
      this.maxCostUsd,
      required this.runId,
      required this.status,
      required this.workflowId})
      : super._();
  @override
  CaseInvestigationRef rebuild(
          void Function(CaseInvestigationRefBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseInvestigationRefBuilder toBuilder() =>
      CaseInvestigationRefBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseInvestigationRef &&
        budgetHealth == other.budgetHealth &&
        costUsd == other.costUsd &&
        createdAt == other.createdAt &&
        investigationId == other.investigationId &&
        iterationCount == other.iterationCount &&
        live == other.live &&
        maxCostUsd == other.maxCostUsd &&
        runId == other.runId &&
        status == other.status &&
        workflowId == other.workflowId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, budgetHealth.hashCode);
    _$hash = $jc(_$hash, costUsd.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, investigationId.hashCode);
    _$hash = $jc(_$hash, iterationCount.hashCode);
    _$hash = $jc(_$hash, live.hashCode);
    _$hash = $jc(_$hash, maxCostUsd.hashCode);
    _$hash = $jc(_$hash, runId.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, workflowId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseInvestigationRef')
          ..add('budgetHealth', budgetHealth)
          ..add('costUsd', costUsd)
          ..add('createdAt', createdAt)
          ..add('investigationId', investigationId)
          ..add('iterationCount', iterationCount)
          ..add('live', live)
          ..add('maxCostUsd', maxCostUsd)
          ..add('runId', runId)
          ..add('status', status)
          ..add('workflowId', workflowId))
        .toString();
  }
}

class CaseInvestigationRefBuilder
    implements Builder<CaseInvestigationRef, CaseInvestigationRefBuilder> {
  _$CaseInvestigationRef? _$v;

  String? _budgetHealth;
  String? get budgetHealth => _$this._budgetHealth;
  set budgetHealth(String? budgetHealth) => _$this._budgetHealth = budgetHealth;

  num? _costUsd;
  num? get costUsd => _$this._costUsd;
  set costUsd(num? costUsd) => _$this._costUsd = costUsd;

  String? _createdAt;
  String? get createdAt => _$this._createdAt;
  set createdAt(String? createdAt) => _$this._createdAt = createdAt;

  String? _investigationId;
  String? get investigationId => _$this._investigationId;
  set investigationId(String? investigationId) =>
      _$this._investigationId = investigationId;

  int? _iterationCount;
  int? get iterationCount => _$this._iterationCount;
  set iterationCount(int? iterationCount) =>
      _$this._iterationCount = iterationCount;

  bool? _live;
  bool? get live => _$this._live;
  set live(bool? live) => _$this._live = live;

  num? _maxCostUsd;
  num? get maxCostUsd => _$this._maxCostUsd;
  set maxCostUsd(num? maxCostUsd) => _$this._maxCostUsd = maxCostUsd;

  String? _runId;
  String? get runId => _$this._runId;
  set runId(String? runId) => _$this._runId = runId;

  String? _status;
  String? get status => _$this._status;
  set status(String? status) => _$this._status = status;

  String? _workflowId;
  String? get workflowId => _$this._workflowId;
  set workflowId(String? workflowId) => _$this._workflowId = workflowId;

  CaseInvestigationRefBuilder() {
    CaseInvestigationRef._defaults(this);
  }

  CaseInvestigationRefBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _budgetHealth = $v.budgetHealth;
      _costUsd = $v.costUsd;
      _createdAt = $v.createdAt;
      _investigationId = $v.investigationId;
      _iterationCount = $v.iterationCount;
      _live = $v.live;
      _maxCostUsd = $v.maxCostUsd;
      _runId = $v.runId;
      _status = $v.status;
      _workflowId = $v.workflowId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseInvestigationRef other) {
    _$v = other as _$CaseInvestigationRef;
  }

  @override
  void update(void Function(CaseInvestigationRefBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseInvestigationRef build() => _build();

  _$CaseInvestigationRef _build() {
    final _$result = _$v ??
        _$CaseInvestigationRef._(
          budgetHealth: budgetHealth,
          costUsd: costUsd,
          createdAt: createdAt,
          investigationId: investigationId,
          iterationCount: iterationCount,
          live: live,
          maxCostUsd: maxCostUsd,
          runId: BuiltValueNullFieldError.checkNotNull(
              runId, r'CaseInvestigationRef', 'runId'),
          status: BuiltValueNullFieldError.checkNotNull(
              status, r'CaseInvestigationRef', 'status'),
          workflowId: BuiltValueNullFieldError.checkNotNull(
              workflowId, r'CaseInvestigationRef', 'workflowId'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
