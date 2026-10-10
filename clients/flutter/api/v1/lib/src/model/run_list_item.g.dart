// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'run_list_item.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$RunListItem extends RunListItem {
  @override
  final String? finishedAt;
  @override
  final String? runId;
  @override
  final String? runKind;
  @override
  final String? startedAt;
  @override
  final String? status;
  @override
  final String? triggeredBy;

  factory _$RunListItem([void Function(RunListItemBuilder)? updates]) =>
      (RunListItemBuilder()..update(updates))._build();

  _$RunListItem._(
      {this.finishedAt,
      this.runId,
      this.runKind,
      this.startedAt,
      this.status,
      this.triggeredBy})
      : super._();
  @override
  RunListItem rebuild(void Function(RunListItemBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  RunListItemBuilder toBuilder() => RunListItemBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is RunListItem &&
        finishedAt == other.finishedAt &&
        runId == other.runId &&
        runKind == other.runKind &&
        startedAt == other.startedAt &&
        status == other.status &&
        triggeredBy == other.triggeredBy;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, finishedAt.hashCode);
    _$hash = $jc(_$hash, runId.hashCode);
    _$hash = $jc(_$hash, runKind.hashCode);
    _$hash = $jc(_$hash, startedAt.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, triggeredBy.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'RunListItem')
          ..add('finishedAt', finishedAt)
          ..add('runId', runId)
          ..add('runKind', runKind)
          ..add('startedAt', startedAt)
          ..add('status', status)
          ..add('triggeredBy', triggeredBy))
        .toString();
  }
}

class RunListItemBuilder implements Builder<RunListItem, RunListItemBuilder> {
  _$RunListItem? _$v;

  String? _finishedAt;
  String? get finishedAt => _$this._finishedAt;
  set finishedAt(String? finishedAt) => _$this._finishedAt = finishedAt;

  String? _runId;
  String? get runId => _$this._runId;
  set runId(String? runId) => _$this._runId = runId;

  String? _runKind;
  String? get runKind => _$this._runKind;
  set runKind(String? runKind) => _$this._runKind = runKind;

  String? _startedAt;
  String? get startedAt => _$this._startedAt;
  set startedAt(String? startedAt) => _$this._startedAt = startedAt;

  String? _status;
  String? get status => _$this._status;
  set status(String? status) => _$this._status = status;

  String? _triggeredBy;
  String? get triggeredBy => _$this._triggeredBy;
  set triggeredBy(String? triggeredBy) => _$this._triggeredBy = triggeredBy;

  RunListItemBuilder() {
    RunListItem._defaults(this);
  }

  RunListItemBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _finishedAt = $v.finishedAt;
      _runId = $v.runId;
      _runKind = $v.runKind;
      _startedAt = $v.startedAt;
      _status = $v.status;
      _triggeredBy = $v.triggeredBy;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(RunListItem other) {
    _$v = other as _$RunListItem;
  }

  @override
  void update(void Function(RunListItemBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  RunListItem build() => _build();

  _$RunListItem _build() {
    final _$result = _$v ??
        _$RunListItem._(
          finishedAt: finishedAt,
          runId: runId,
          runKind: runKind,
          startedAt: startedAt,
          status: status,
          triggeredBy: triggeredBy,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
