// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'run_list_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$RunListResponse extends RunListResponse {
  @override
  final int count;
  @override
  final BuiltList<RunListItem> runs;

  factory _$RunListResponse([void Function(RunListResponseBuilder)? updates]) =>
      (RunListResponseBuilder()..update(updates))._build();

  _$RunListResponse._({required this.count, required this.runs}) : super._();
  @override
  RunListResponse rebuild(void Function(RunListResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  RunListResponseBuilder toBuilder() => RunListResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is RunListResponse &&
        count == other.count &&
        runs == other.runs;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, count.hashCode);
    _$hash = $jc(_$hash, runs.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'RunListResponse')
          ..add('count', count)
          ..add('runs', runs))
        .toString();
  }
}

class RunListResponseBuilder
    implements Builder<RunListResponse, RunListResponseBuilder> {
  _$RunListResponse? _$v;

  int? _count;
  int? get count => _$this._count;
  set count(int? count) => _$this._count = count;

  ListBuilder<RunListItem>? _runs;
  ListBuilder<RunListItem> get runs =>
      _$this._runs ??= ListBuilder<RunListItem>();
  set runs(ListBuilder<RunListItem>? runs) => _$this._runs = runs;

  RunListResponseBuilder() {
    RunListResponse._defaults(this);
  }

  RunListResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _count = $v.count;
      _runs = $v.runs.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(RunListResponse other) {
    _$v = other as _$RunListResponse;
  }

  @override
  void update(void Function(RunListResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  RunListResponse build() => _build();

  _$RunListResponse _build() {
    _$RunListResponse _$result;
    try {
      _$result = _$v ??
          _$RunListResponse._(
            count: BuiltValueNullFieldError.checkNotNull(
                count, r'RunListResponse', 'count'),
            runs: runs.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'runs';
        runs.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'RunListResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
