// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'start_run_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$StartRunResponse extends StartRunResponse {
  @override
  final String jobId;
  @override
  final String runId;

  factory _$StartRunResponse(
          [void Function(StartRunResponseBuilder)? updates]) =>
      (StartRunResponseBuilder()..update(updates))._build();

  _$StartRunResponse._({required this.jobId, required this.runId}) : super._();
  @override
  StartRunResponse rebuild(void Function(StartRunResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  StartRunResponseBuilder toBuilder() =>
      StartRunResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is StartRunResponse &&
        jobId == other.jobId &&
        runId == other.runId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, jobId.hashCode);
    _$hash = $jc(_$hash, runId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'StartRunResponse')
          ..add('jobId', jobId)
          ..add('runId', runId))
        .toString();
  }
}

class StartRunResponseBuilder
    implements Builder<StartRunResponse, StartRunResponseBuilder> {
  _$StartRunResponse? _$v;

  String? _jobId;
  String? get jobId => _$this._jobId;
  set jobId(String? jobId) => _$this._jobId = jobId;

  String? _runId;
  String? get runId => _$this._runId;
  set runId(String? runId) => _$this._runId = runId;

  StartRunResponseBuilder() {
    StartRunResponse._defaults(this);
  }

  StartRunResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _jobId = $v.jobId;
      _runId = $v.runId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(StartRunResponse other) {
    _$v = other as _$StartRunResponse;
  }

  @override
  void update(void Function(StartRunResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  StartRunResponse build() => _build();

  _$StartRunResponse _build() {
    final _$result = _$v ??
        _$StartRunResponse._(
          jobId: BuiltValueNullFieldError.checkNotNull(
              jobId, r'StartRunResponse', 'jobId'),
          runId: BuiltValueNullFieldError.checkNotNull(
              runId, r'StartRunResponse', 'runId'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
