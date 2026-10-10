// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'breaker_reset_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$BreakerResetRequest extends BreakerResetRequest {
  @override
  final String reason;

  factory _$BreakerResetRequest(
          [void Function(BreakerResetRequestBuilder)? updates]) =>
      (BreakerResetRequestBuilder()..update(updates))._build();

  _$BreakerResetRequest._({required this.reason}) : super._();
  @override
  BreakerResetRequest rebuild(
          void Function(BreakerResetRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  BreakerResetRequestBuilder toBuilder() =>
      BreakerResetRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is BreakerResetRequest && reason == other.reason;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, reason.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'BreakerResetRequest')
          ..add('reason', reason))
        .toString();
  }
}

class BreakerResetRequestBuilder
    implements Builder<BreakerResetRequest, BreakerResetRequestBuilder> {
  _$BreakerResetRequest? _$v;

  String? _reason;
  String? get reason => _$this._reason;
  set reason(String? reason) => _$this._reason = reason;

  BreakerResetRequestBuilder() {
    BreakerResetRequest._defaults(this);
  }

  BreakerResetRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _reason = $v.reason;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(BreakerResetRequest other) {
    _$v = other as _$BreakerResetRequest;
  }

  @override
  void update(void Function(BreakerResetRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  BreakerResetRequest build() => _build();

  _$BreakerResetRequest _build() {
    final _$result = _$v ??
        _$BreakerResetRequest._(
          reason: BuiltValueNullFieldError.checkNotNull(
              reason, r'BreakerResetRequest', 'reason'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
