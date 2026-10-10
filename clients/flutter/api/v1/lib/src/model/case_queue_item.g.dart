// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_queue_item.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseQueueItem extends CaseQueueItem {
  @override
  final num ageSeconds;
  @override
  final String? assignee;
  @override
  final String? budgetHealth;
  @override
  final String caseId;
  @override
  final String combinedState;
  @override
  final int? commentCount;
  @override
  final num? costUsd;
  @override
  final int? findingsCount;
  @override
  final String? healthStatus;
  @override
  final int? iterationCount;
  @override
  final DateTime? lastActivity;
  @override
  final num? maxCostUsd;
  @override
  final bool? needsYou;
  @override
  final String? priority;
  @override
  final num? slaSecondsLeft;
  @override
  final String title;
  @override
  final String? workflowId;

  factory _$CaseQueueItem([void Function(CaseQueueItemBuilder)? updates]) =>
      (CaseQueueItemBuilder()..update(updates))._build();

  _$CaseQueueItem._(
      {required this.ageSeconds,
      this.assignee,
      this.budgetHealth,
      required this.caseId,
      required this.combinedState,
      this.commentCount,
      this.costUsd,
      this.findingsCount,
      this.healthStatus,
      this.iterationCount,
      this.lastActivity,
      this.maxCostUsd,
      this.needsYou,
      this.priority,
      this.slaSecondsLeft,
      required this.title,
      this.workflowId})
      : super._();
  @override
  CaseQueueItem rebuild(void Function(CaseQueueItemBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseQueueItemBuilder toBuilder() => CaseQueueItemBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseQueueItem &&
        ageSeconds == other.ageSeconds &&
        assignee == other.assignee &&
        budgetHealth == other.budgetHealth &&
        caseId == other.caseId &&
        combinedState == other.combinedState &&
        commentCount == other.commentCount &&
        costUsd == other.costUsd &&
        findingsCount == other.findingsCount &&
        healthStatus == other.healthStatus &&
        iterationCount == other.iterationCount &&
        lastActivity == other.lastActivity &&
        maxCostUsd == other.maxCostUsd &&
        needsYou == other.needsYou &&
        priority == other.priority &&
        slaSecondsLeft == other.slaSecondsLeft &&
        title == other.title &&
        workflowId == other.workflowId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, ageSeconds.hashCode);
    _$hash = $jc(_$hash, assignee.hashCode);
    _$hash = $jc(_$hash, budgetHealth.hashCode);
    _$hash = $jc(_$hash, caseId.hashCode);
    _$hash = $jc(_$hash, combinedState.hashCode);
    _$hash = $jc(_$hash, commentCount.hashCode);
    _$hash = $jc(_$hash, costUsd.hashCode);
    _$hash = $jc(_$hash, findingsCount.hashCode);
    _$hash = $jc(_$hash, healthStatus.hashCode);
    _$hash = $jc(_$hash, iterationCount.hashCode);
    _$hash = $jc(_$hash, lastActivity.hashCode);
    _$hash = $jc(_$hash, maxCostUsd.hashCode);
    _$hash = $jc(_$hash, needsYou.hashCode);
    _$hash = $jc(_$hash, priority.hashCode);
    _$hash = $jc(_$hash, slaSecondsLeft.hashCode);
    _$hash = $jc(_$hash, title.hashCode);
    _$hash = $jc(_$hash, workflowId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseQueueItem')
          ..add('ageSeconds', ageSeconds)
          ..add('assignee', assignee)
          ..add('budgetHealth', budgetHealth)
          ..add('caseId', caseId)
          ..add('combinedState', combinedState)
          ..add('commentCount', commentCount)
          ..add('costUsd', costUsd)
          ..add('findingsCount', findingsCount)
          ..add('healthStatus', healthStatus)
          ..add('iterationCount', iterationCount)
          ..add('lastActivity', lastActivity)
          ..add('maxCostUsd', maxCostUsd)
          ..add('needsYou', needsYou)
          ..add('priority', priority)
          ..add('slaSecondsLeft', slaSecondsLeft)
          ..add('title', title)
          ..add('workflowId', workflowId))
        .toString();
  }
}

class CaseQueueItemBuilder
    implements Builder<CaseQueueItem, CaseQueueItemBuilder> {
  _$CaseQueueItem? _$v;

  num? _ageSeconds;
  num? get ageSeconds => _$this._ageSeconds;
  set ageSeconds(num? ageSeconds) => _$this._ageSeconds = ageSeconds;

  String? _assignee;
  String? get assignee => _$this._assignee;
  set assignee(String? assignee) => _$this._assignee = assignee;

  String? _budgetHealth;
  String? get budgetHealth => _$this._budgetHealth;
  set budgetHealth(String? budgetHealth) => _$this._budgetHealth = budgetHealth;

  String? _caseId;
  String? get caseId => _$this._caseId;
  set caseId(String? caseId) => _$this._caseId = caseId;

  String? _combinedState;
  String? get combinedState => _$this._combinedState;
  set combinedState(String? combinedState) =>
      _$this._combinedState = combinedState;

  int? _commentCount;
  int? get commentCount => _$this._commentCount;
  set commentCount(int? commentCount) => _$this._commentCount = commentCount;

  num? _costUsd;
  num? get costUsd => _$this._costUsd;
  set costUsd(num? costUsd) => _$this._costUsd = costUsd;

  int? _findingsCount;
  int? get findingsCount => _$this._findingsCount;
  set findingsCount(int? findingsCount) =>
      _$this._findingsCount = findingsCount;

  String? _healthStatus;
  String? get healthStatus => _$this._healthStatus;
  set healthStatus(String? healthStatus) => _$this._healthStatus = healthStatus;

  int? _iterationCount;
  int? get iterationCount => _$this._iterationCount;
  set iterationCount(int? iterationCount) =>
      _$this._iterationCount = iterationCount;

  DateTime? _lastActivity;
  DateTime? get lastActivity => _$this._lastActivity;
  set lastActivity(DateTime? lastActivity) =>
      _$this._lastActivity = lastActivity;

  num? _maxCostUsd;
  num? get maxCostUsd => _$this._maxCostUsd;
  set maxCostUsd(num? maxCostUsd) => _$this._maxCostUsd = maxCostUsd;

  bool? _needsYou;
  bool? get needsYou => _$this._needsYou;
  set needsYou(bool? needsYou) => _$this._needsYou = needsYou;

  String? _priority;
  String? get priority => _$this._priority;
  set priority(String? priority) => _$this._priority = priority;

  num? _slaSecondsLeft;
  num? get slaSecondsLeft => _$this._slaSecondsLeft;
  set slaSecondsLeft(num? slaSecondsLeft) =>
      _$this._slaSecondsLeft = slaSecondsLeft;

  String? _title;
  String? get title => _$this._title;
  set title(String? title) => _$this._title = title;

  String? _workflowId;
  String? get workflowId => _$this._workflowId;
  set workflowId(String? workflowId) => _$this._workflowId = workflowId;

  CaseQueueItemBuilder() {
    CaseQueueItem._defaults(this);
  }

  CaseQueueItemBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _ageSeconds = $v.ageSeconds;
      _assignee = $v.assignee;
      _budgetHealth = $v.budgetHealth;
      _caseId = $v.caseId;
      _combinedState = $v.combinedState;
      _commentCount = $v.commentCount;
      _costUsd = $v.costUsd;
      _findingsCount = $v.findingsCount;
      _healthStatus = $v.healthStatus;
      _iterationCount = $v.iterationCount;
      _lastActivity = $v.lastActivity;
      _maxCostUsd = $v.maxCostUsd;
      _needsYou = $v.needsYou;
      _priority = $v.priority;
      _slaSecondsLeft = $v.slaSecondsLeft;
      _title = $v.title;
      _workflowId = $v.workflowId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseQueueItem other) {
    _$v = other as _$CaseQueueItem;
  }

  @override
  void update(void Function(CaseQueueItemBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseQueueItem build() => _build();

  _$CaseQueueItem _build() {
    final _$result = _$v ??
        _$CaseQueueItem._(
          ageSeconds: BuiltValueNullFieldError.checkNotNull(
              ageSeconds, r'CaseQueueItem', 'ageSeconds'),
          assignee: assignee,
          budgetHealth: budgetHealth,
          caseId: BuiltValueNullFieldError.checkNotNull(
              caseId, r'CaseQueueItem', 'caseId'),
          combinedState: BuiltValueNullFieldError.checkNotNull(
              combinedState, r'CaseQueueItem', 'combinedState'),
          commentCount: commentCount,
          costUsd: costUsd,
          findingsCount: findingsCount,
          healthStatus: healthStatus,
          iterationCount: iterationCount,
          lastActivity: lastActivity,
          maxCostUsd: maxCostUsd,
          needsYou: needsYou,
          priority: priority,
          slaSecondsLeft: slaSecondsLeft,
          title: BuiltValueNullFieldError.checkNotNull(
              title, r'CaseQueueItem', 'title'),
          workflowId: workflowId,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
