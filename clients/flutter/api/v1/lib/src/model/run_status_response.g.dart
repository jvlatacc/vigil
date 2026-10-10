// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'run_status_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$RunStatusResponse extends RunStatusResponse {
  @override
  final int events;
  @override
  final String? outcome;
  @override
  final String? reason;
  @override
  final String runId;
  @override
  final String status;

  factory _$RunStatusResponse(
          [void Function(RunStatusResponseBuilder)? updates]) =>
      (RunStatusResponseBuilder()..update(updates))._build();

  _$RunStatusResponse._(
      {required this.events,
      this.outcome,
      this.reason,
      required this.runId,
      required this.status})
      : super._();
  @override
  RunStatusResponse rebuild(void Function(RunStatusResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  RunStatusResponseBuilder toBuilder() =>
      RunStatusResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is RunStatusResponse &&
        events == other.events &&
        outcome == other.outcome &&
        reason == other.reason &&
        runId == other.runId &&
        status == other.status;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, events.hashCode);
    _$hash = $jc(_$hash, outcome.hashCode);
    _$hash = $jc(_$hash, reason.hashCode);
    _$hash = $jc(_$hash, runId.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'RunStatusResponse')
          ..add('events', events)
          ..add('outcome', outcome)
          ..add('reason', reason)
          ..add('runId', runId)
          ..add('status', status))
        .toString();
  }
}

class RunStatusResponseBuilder
    implements Builder<RunStatusResponse, RunStatusResponseBuilder> {
  _$RunStatusResponse? _$v;

  int? _events;
  int? get events => _$this._events;
  set events(int? events) => _$this._events = events;

  String? _outcome;
  String? get outcome => _$this._outcome;
  set outcome(String? outcome) => _$this._outcome = outcome;

  String? _reason;
  String? get reason => _$this._reason;
  set reason(String? reason) => _$this._reason = reason;

  String? _runId;
  String? get runId => _$this._runId;
  set runId(String? runId) => _$this._runId = runId;

  String? _status;
  String? get status => _$this._status;
  set status(String? status) => _$this._status = status;

  RunStatusResponseBuilder() {
    RunStatusResponse._defaults(this);
  }

  RunStatusResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _events = $v.events;
      _outcome = $v.outcome;
      _reason = $v.reason;
      _runId = $v.runId;
      _status = $v.status;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(RunStatusResponse other) {
    _$v = other as _$RunStatusResponse;
  }

  @override
  void update(void Function(RunStatusResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  RunStatusResponse build() => _build();

  _$RunStatusResponse _build() {
    final _$result = _$v ??
        _$RunStatusResponse._(
          events: BuiltValueNullFieldError.checkNotNull(
              events, r'RunStatusResponse', 'events'),
          outcome: outcome,
          reason: reason,
          runId: BuiltValueNullFieldError.checkNotNull(
              runId, r'RunStatusResponse', 'runId'),
          status: BuiltValueNullFieldError.checkNotNull(
              status, r'RunStatusResponse', 'status'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
