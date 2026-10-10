// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'mttr_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$MttrResponse extends MttrResponse {
  @override
  final num? averageMttrHours;
  @override
  final num? averageMttrSeconds;
  @override
  final BuiltMap<String, num?>? mttrByPriority;
  @override
  final int totalCases;
  @override
  final BuiltList<BuiltMap<String, JsonObject?>>? trendData;

  factory _$MttrResponse([void Function(MttrResponseBuilder)? updates]) =>
      (MttrResponseBuilder()..update(updates))._build();

  _$MttrResponse._(
      {this.averageMttrHours,
      this.averageMttrSeconds,
      this.mttrByPriority,
      required this.totalCases,
      this.trendData})
      : super._();
  @override
  MttrResponse rebuild(void Function(MttrResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  MttrResponseBuilder toBuilder() => MttrResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is MttrResponse &&
        averageMttrHours == other.averageMttrHours &&
        averageMttrSeconds == other.averageMttrSeconds &&
        mttrByPriority == other.mttrByPriority &&
        totalCases == other.totalCases &&
        trendData == other.trendData;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, averageMttrHours.hashCode);
    _$hash = $jc(_$hash, averageMttrSeconds.hashCode);
    _$hash = $jc(_$hash, mttrByPriority.hashCode);
    _$hash = $jc(_$hash, totalCases.hashCode);
    _$hash = $jc(_$hash, trendData.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'MttrResponse')
          ..add('averageMttrHours', averageMttrHours)
          ..add('averageMttrSeconds', averageMttrSeconds)
          ..add('mttrByPriority', mttrByPriority)
          ..add('totalCases', totalCases)
          ..add('trendData', trendData))
        .toString();
  }
}

class MttrResponseBuilder
    implements Builder<MttrResponse, MttrResponseBuilder> {
  _$MttrResponse? _$v;

  num? _averageMttrHours;
  num? get averageMttrHours => _$this._averageMttrHours;
  set averageMttrHours(num? averageMttrHours) =>
      _$this._averageMttrHours = averageMttrHours;

  num? _averageMttrSeconds;
  num? get averageMttrSeconds => _$this._averageMttrSeconds;
  set averageMttrSeconds(num? averageMttrSeconds) =>
      _$this._averageMttrSeconds = averageMttrSeconds;

  MapBuilder<String, num?>? _mttrByPriority;
  MapBuilder<String, num?> get mttrByPriority =>
      _$this._mttrByPriority ??= MapBuilder<String, num?>();
  set mttrByPriority(MapBuilder<String, num?>? mttrByPriority) =>
      _$this._mttrByPriority = mttrByPriority;

  int? _totalCases;
  int? get totalCases => _$this._totalCases;
  set totalCases(int? totalCases) => _$this._totalCases = totalCases;

  ListBuilder<BuiltMap<String, JsonObject?>>? _trendData;
  ListBuilder<BuiltMap<String, JsonObject?>> get trendData =>
      _$this._trendData ??= ListBuilder<BuiltMap<String, JsonObject?>>();
  set trendData(ListBuilder<BuiltMap<String, JsonObject?>>? trendData) =>
      _$this._trendData = trendData;

  MttrResponseBuilder() {
    MttrResponse._defaults(this);
  }

  MttrResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _averageMttrHours = $v.averageMttrHours;
      _averageMttrSeconds = $v.averageMttrSeconds;
      _mttrByPriority = $v.mttrByPriority?.toBuilder();
      _totalCases = $v.totalCases;
      _trendData = $v.trendData?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(MttrResponse other) {
    _$v = other as _$MttrResponse;
  }

  @override
  void update(void Function(MttrResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  MttrResponse build() => _build();

  _$MttrResponse _build() {
    _$MttrResponse _$result;
    try {
      _$result = _$v ??
          _$MttrResponse._(
            averageMttrHours: averageMttrHours,
            averageMttrSeconds: averageMttrSeconds,
            mttrByPriority: _mttrByPriority?.build(),
            totalCases: BuiltValueNullFieldError.checkNotNull(
                totalCases, r'MttrResponse', 'totalCases'),
            trendData: _trendData?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'mttrByPriority';
        _mttrByPriority?.build();

        _$failedField = 'trendData';
        _trendData?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'MttrResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
