// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'case_queue_strip.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CaseQueueStrip extends CaseQueueStrip {
  @override
  final num agentClosureShare;
  @override
  final BuiltMap<String, int> byState;
  @override
  final int closedToday;
  @override
  final int needsYou;
  @override
  final int slaAtRisk;

  factory _$CaseQueueStrip([void Function(CaseQueueStripBuilder)? updates]) =>
      (CaseQueueStripBuilder()..update(updates))._build();

  _$CaseQueueStrip._(
      {required this.agentClosureShare,
      required this.byState,
      required this.closedToday,
      required this.needsYou,
      required this.slaAtRisk})
      : super._();
  @override
  CaseQueueStrip rebuild(void Function(CaseQueueStripBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CaseQueueStripBuilder toBuilder() => CaseQueueStripBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CaseQueueStrip &&
        agentClosureShare == other.agentClosureShare &&
        byState == other.byState &&
        closedToday == other.closedToday &&
        needsYou == other.needsYou &&
        slaAtRisk == other.slaAtRisk;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, agentClosureShare.hashCode);
    _$hash = $jc(_$hash, byState.hashCode);
    _$hash = $jc(_$hash, closedToday.hashCode);
    _$hash = $jc(_$hash, needsYou.hashCode);
    _$hash = $jc(_$hash, slaAtRisk.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CaseQueueStrip')
          ..add('agentClosureShare', agentClosureShare)
          ..add('byState', byState)
          ..add('closedToday', closedToday)
          ..add('needsYou', needsYou)
          ..add('slaAtRisk', slaAtRisk))
        .toString();
  }
}

class CaseQueueStripBuilder
    implements Builder<CaseQueueStrip, CaseQueueStripBuilder> {
  _$CaseQueueStrip? _$v;

  num? _agentClosureShare;
  num? get agentClosureShare => _$this._agentClosureShare;
  set agentClosureShare(num? agentClosureShare) =>
      _$this._agentClosureShare = agentClosureShare;

  MapBuilder<String, int>? _byState;
  MapBuilder<String, int> get byState =>
      _$this._byState ??= MapBuilder<String, int>();
  set byState(MapBuilder<String, int>? byState) => _$this._byState = byState;

  int? _closedToday;
  int? get closedToday => _$this._closedToday;
  set closedToday(int? closedToday) => _$this._closedToday = closedToday;

  int? _needsYou;
  int? get needsYou => _$this._needsYou;
  set needsYou(int? needsYou) => _$this._needsYou = needsYou;

  int? _slaAtRisk;
  int? get slaAtRisk => _$this._slaAtRisk;
  set slaAtRisk(int? slaAtRisk) => _$this._slaAtRisk = slaAtRisk;

  CaseQueueStripBuilder() {
    CaseQueueStrip._defaults(this);
  }

  CaseQueueStripBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _agentClosureShare = $v.agentClosureShare;
      _byState = $v.byState.toBuilder();
      _closedToday = $v.closedToday;
      _needsYou = $v.needsYou;
      _slaAtRisk = $v.slaAtRisk;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CaseQueueStrip other) {
    _$v = other as _$CaseQueueStrip;
  }

  @override
  void update(void Function(CaseQueueStripBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CaseQueueStrip build() => _build();

  _$CaseQueueStrip _build() {
    _$CaseQueueStrip _$result;
    try {
      _$result = _$v ??
          _$CaseQueueStrip._(
            agentClosureShare: BuiltValueNullFieldError.checkNotNull(
                agentClosureShare, r'CaseQueueStrip', 'agentClosureShare'),
            byState: byState.build(),
            closedToday: BuiltValueNullFieldError.checkNotNull(
                closedToday, r'CaseQueueStrip', 'closedToday'),
            needsYou: BuiltValueNullFieldError.checkNotNull(
                needsYou, r'CaseQueueStrip', 'needsYou'),
            slaAtRisk: BuiltValueNullFieldError.checkNotNull(
                slaAtRisk, r'CaseQueueStrip', 'slaAtRisk'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'byState';
        byState.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CaseQueueStrip', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
