// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'mttd_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$MttdResponse extends MttdResponse {
  @override
  final num? averageMttdHours;
  @override
  final num? averageMttdSeconds;
  @override
  final BuiltMap<String, num?>? mttdByPriority;
  @override
  final int totalCases;

  factory _$MttdResponse([void Function(MttdResponseBuilder)? updates]) =>
      (MttdResponseBuilder()..update(updates))._build();

  _$MttdResponse._(
      {this.averageMttdHours,
      this.averageMttdSeconds,
      this.mttdByPriority,
      required this.totalCases})
      : super._();
  @override
  MttdResponse rebuild(void Function(MttdResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  MttdResponseBuilder toBuilder() => MttdResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is MttdResponse &&
        averageMttdHours == other.averageMttdHours &&
        averageMttdSeconds == other.averageMttdSeconds &&
        mttdByPriority == other.mttdByPriority &&
        totalCases == other.totalCases;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, averageMttdHours.hashCode);
    _$hash = $jc(_$hash, averageMttdSeconds.hashCode);
    _$hash = $jc(_$hash, mttdByPriority.hashCode);
    _$hash = $jc(_$hash, totalCases.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'MttdResponse')
          ..add('averageMttdHours', averageMttdHours)
          ..add('averageMttdSeconds', averageMttdSeconds)
          ..add('mttdByPriority', mttdByPriority)
          ..add('totalCases', totalCases))
        .toString();
  }
}

class MttdResponseBuilder
    implements Builder<MttdResponse, MttdResponseBuilder> {
  _$MttdResponse? _$v;

  num? _averageMttdHours;
  num? get averageMttdHours => _$this._averageMttdHours;
  set averageMttdHours(num? averageMttdHours) =>
      _$this._averageMttdHours = averageMttdHours;

  num? _averageMttdSeconds;
  num? get averageMttdSeconds => _$this._averageMttdSeconds;
  set averageMttdSeconds(num? averageMttdSeconds) =>
      _$this._averageMttdSeconds = averageMttdSeconds;

  MapBuilder<String, num?>? _mttdByPriority;
  MapBuilder<String, num?> get mttdByPriority =>
      _$this._mttdByPriority ??= MapBuilder<String, num?>();
  set mttdByPriority(MapBuilder<String, num?>? mttdByPriority) =>
      _$this._mttdByPriority = mttdByPriority;

  int? _totalCases;
  int? get totalCases => _$this._totalCases;
  set totalCases(int? totalCases) => _$this._totalCases = totalCases;

  MttdResponseBuilder() {
    MttdResponse._defaults(this);
  }

  MttdResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _averageMttdHours = $v.averageMttdHours;
      _averageMttdSeconds = $v.averageMttdSeconds;
      _mttdByPriority = $v.mttdByPriority?.toBuilder();
      _totalCases = $v.totalCases;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(MttdResponse other) {
    _$v = other as _$MttdResponse;
  }

  @override
  void update(void Function(MttdResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  MttdResponse build() => _build();

  _$MttdResponse _build() {
    _$MttdResponse _$result;
    try {
      _$result = _$v ??
          _$MttdResponse._(
            averageMttdHours: averageMttdHours,
            averageMttdSeconds: averageMttdSeconds,
            mttdByPriority: _mttdByPriority?.build(),
            totalCases: BuiltValueNullFieldError.checkNotNull(
                totalCases, r'MttdResponse', 'totalCases'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'mttdByPriority';
        _mttdByPriority?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'MttdResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
