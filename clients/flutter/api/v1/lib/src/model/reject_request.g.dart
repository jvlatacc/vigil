// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'reject_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$RejectRequest extends RejectRequest {
  @override
  final String reason;
  @override
  final String? rejectedBy;

  factory _$RejectRequest([void Function(RejectRequestBuilder)? updates]) =>
      (RejectRequestBuilder()..update(updates))._build();

  _$RejectRequest._({required this.reason, this.rejectedBy}) : super._();
  @override
  RejectRequest rebuild(void Function(RejectRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  RejectRequestBuilder toBuilder() => RejectRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is RejectRequest &&
        reason == other.reason &&
        rejectedBy == other.rejectedBy;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, reason.hashCode);
    _$hash = $jc(_$hash, rejectedBy.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'RejectRequest')
          ..add('reason', reason)
          ..add('rejectedBy', rejectedBy))
        .toString();
  }
}

class RejectRequestBuilder
    implements Builder<RejectRequest, RejectRequestBuilder> {
  _$RejectRequest? _$v;

  String? _reason;
  String? get reason => _$this._reason;
  set reason(String? reason) => _$this._reason = reason;

  String? _rejectedBy;
  String? get rejectedBy => _$this._rejectedBy;
  set rejectedBy(String? rejectedBy) => _$this._rejectedBy = rejectedBy;

  RejectRequestBuilder() {
    RejectRequest._defaults(this);
  }

  RejectRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _reason = $v.reason;
      _rejectedBy = $v.rejectedBy;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(RejectRequest other) {
    _$v = other as _$RejectRequest;
  }

  @override
  void update(void Function(RejectRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  RejectRequest build() => _build();

  _$RejectRequest _build() {
    final _$result = _$v ??
        _$RejectRequest._(
          reason: BuiltValueNullFieldError.checkNotNull(
              reason, r'RejectRequest', 'reason'),
          rejectedBy: rejectedBy,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
