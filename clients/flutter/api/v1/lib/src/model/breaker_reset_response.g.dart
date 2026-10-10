// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'breaker_reset_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$BreakerResetResponse extends BreakerResetResponse {
  @override
  final BreakerStatusResponse after;
  @override
  final BreakerStatusResponse before;
  @override
  final String? rule;

  factory _$BreakerResetResponse(
          [void Function(BreakerResetResponseBuilder)? updates]) =>
      (BreakerResetResponseBuilder()..update(updates))._build();

  _$BreakerResetResponse._(
      {required this.after, required this.before, this.rule})
      : super._();
  @override
  BreakerResetResponse rebuild(
          void Function(BreakerResetResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  BreakerResetResponseBuilder toBuilder() =>
      BreakerResetResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is BreakerResetResponse &&
        after == other.after &&
        before == other.before &&
        rule == other.rule;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, after.hashCode);
    _$hash = $jc(_$hash, before.hashCode);
    _$hash = $jc(_$hash, rule.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'BreakerResetResponse')
          ..add('after', after)
          ..add('before', before)
          ..add('rule', rule))
        .toString();
  }
}

class BreakerResetResponseBuilder
    implements Builder<BreakerResetResponse, BreakerResetResponseBuilder> {
  _$BreakerResetResponse? _$v;

  BreakerStatusResponseBuilder? _after;
  BreakerStatusResponseBuilder get after =>
      _$this._after ??= BreakerStatusResponseBuilder();
  set after(BreakerStatusResponseBuilder? after) => _$this._after = after;

  BreakerStatusResponseBuilder? _before;
  BreakerStatusResponseBuilder get before =>
      _$this._before ??= BreakerStatusResponseBuilder();
  set before(BreakerStatusResponseBuilder? before) => _$this._before = before;

  String? _rule;
  String? get rule => _$this._rule;
  set rule(String? rule) => _$this._rule = rule;

  BreakerResetResponseBuilder() {
    BreakerResetResponse._defaults(this);
  }

  BreakerResetResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _after = $v.after.toBuilder();
      _before = $v.before.toBuilder();
      _rule = $v.rule;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(BreakerResetResponse other) {
    _$v = other as _$BreakerResetResponse;
  }

  @override
  void update(void Function(BreakerResetResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  BreakerResetResponse build() => _build();

  _$BreakerResetResponse _build() {
    _$BreakerResetResponse _$result;
    try {
      _$result = _$v ??
          _$BreakerResetResponse._(
            after: after.build(),
            before: before.build(),
            rule: rule,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'after';
        after.build();
        _$failedField = 'before';
        before.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'BreakerResetResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
