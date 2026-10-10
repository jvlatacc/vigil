// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'breaker_status_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$BreakerStatusResponse extends BreakerStatusResponse {
  @override
  final BuiltMap<String, BuiltMap<String, num>>? counters;
  @override
  final bool? escalationFired;
  @override
  final num? openedAt;
  @override
  final String? reason;
  @override
  final String? rule;
  @override
  final int? secondsLeft;
  @override
  final String state;
  @override
  final String? store;

  factory _$BreakerStatusResponse(
          [void Function(BreakerStatusResponseBuilder)? updates]) =>
      (BreakerStatusResponseBuilder()..update(updates))._build();

  _$BreakerStatusResponse._(
      {this.counters,
      this.escalationFired,
      this.openedAt,
      this.reason,
      this.rule,
      this.secondsLeft,
      required this.state,
      this.store})
      : super._();
  @override
  BreakerStatusResponse rebuild(
          void Function(BreakerStatusResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  BreakerStatusResponseBuilder toBuilder() =>
      BreakerStatusResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is BreakerStatusResponse &&
        counters == other.counters &&
        escalationFired == other.escalationFired &&
        openedAt == other.openedAt &&
        reason == other.reason &&
        rule == other.rule &&
        secondsLeft == other.secondsLeft &&
        state == other.state &&
        store == other.store;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, counters.hashCode);
    _$hash = $jc(_$hash, escalationFired.hashCode);
    _$hash = $jc(_$hash, openedAt.hashCode);
    _$hash = $jc(_$hash, reason.hashCode);
    _$hash = $jc(_$hash, rule.hashCode);
    _$hash = $jc(_$hash, secondsLeft.hashCode);
    _$hash = $jc(_$hash, state.hashCode);
    _$hash = $jc(_$hash, store.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'BreakerStatusResponse')
          ..add('counters', counters)
          ..add('escalationFired', escalationFired)
          ..add('openedAt', openedAt)
          ..add('reason', reason)
          ..add('rule', rule)
          ..add('secondsLeft', secondsLeft)
          ..add('state', state)
          ..add('store', store))
        .toString();
  }
}

class BreakerStatusResponseBuilder
    implements Builder<BreakerStatusResponse, BreakerStatusResponseBuilder> {
  _$BreakerStatusResponse? _$v;

  MapBuilder<String, BuiltMap<String, num>>? _counters;
  MapBuilder<String, BuiltMap<String, num>> get counters =>
      _$this._counters ??= MapBuilder<String, BuiltMap<String, num>>();
  set counters(MapBuilder<String, BuiltMap<String, num>>? counters) =>
      _$this._counters = counters;

  bool? _escalationFired;
  bool? get escalationFired => _$this._escalationFired;
  set escalationFired(bool? escalationFired) =>
      _$this._escalationFired = escalationFired;

  num? _openedAt;
  num? get openedAt => _$this._openedAt;
  set openedAt(num? openedAt) => _$this._openedAt = openedAt;

  String? _reason;
  String? get reason => _$this._reason;
  set reason(String? reason) => _$this._reason = reason;

  String? _rule;
  String? get rule => _$this._rule;
  set rule(String? rule) => _$this._rule = rule;

  int? _secondsLeft;
  int? get secondsLeft => _$this._secondsLeft;
  set secondsLeft(int? secondsLeft) => _$this._secondsLeft = secondsLeft;

  String? _state;
  String? get state => _$this._state;
  set state(String? state) => _$this._state = state;

  String? _store;
  String? get store => _$this._store;
  set store(String? store) => _$this._store = store;

  BreakerStatusResponseBuilder() {
    BreakerStatusResponse._defaults(this);
  }

  BreakerStatusResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _counters = $v.counters?.toBuilder();
      _escalationFired = $v.escalationFired;
      _openedAt = $v.openedAt;
      _reason = $v.reason;
      _rule = $v.rule;
      _secondsLeft = $v.secondsLeft;
      _state = $v.state;
      _store = $v.store;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(BreakerStatusResponse other) {
    _$v = other as _$BreakerStatusResponse;
  }

  @override
  void update(void Function(BreakerStatusResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  BreakerStatusResponse build() => _build();

  _$BreakerStatusResponse _build() {
    _$BreakerStatusResponse _$result;
    try {
      _$result = _$v ??
          _$BreakerStatusResponse._(
            counters: _counters?.build(),
            escalationFired: escalationFired,
            openedAt: openedAt,
            reason: reason,
            rule: rule,
            secondsLeft: secondsLeft,
            state: BuiltValueNullFieldError.checkNotNull(
                state, r'BreakerStatusResponse', 'state'),
            store: store,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'counters';
        _counters?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'BreakerStatusResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
