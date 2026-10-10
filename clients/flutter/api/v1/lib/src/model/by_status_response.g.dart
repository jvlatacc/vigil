// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'by_status_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ByStatusResponse extends ByStatusResponse {
  @override
  final BuiltList<StatusBreakdownRow>? statusBreakdown;

  factory _$ByStatusResponse(
          [void Function(ByStatusResponseBuilder)? updates]) =>
      (ByStatusResponseBuilder()..update(updates))._build();

  _$ByStatusResponse._({this.statusBreakdown}) : super._();
  @override
  ByStatusResponse rebuild(void Function(ByStatusResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ByStatusResponseBuilder toBuilder() =>
      ByStatusResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ByStatusResponse &&
        statusBreakdown == other.statusBreakdown;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, statusBreakdown.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ByStatusResponse')
          ..add('statusBreakdown', statusBreakdown))
        .toString();
  }
}

class ByStatusResponseBuilder
    implements Builder<ByStatusResponse, ByStatusResponseBuilder> {
  _$ByStatusResponse? _$v;

  ListBuilder<StatusBreakdownRow>? _statusBreakdown;
  ListBuilder<StatusBreakdownRow> get statusBreakdown =>
      _$this._statusBreakdown ??= ListBuilder<StatusBreakdownRow>();
  set statusBreakdown(ListBuilder<StatusBreakdownRow>? statusBreakdown) =>
      _$this._statusBreakdown = statusBreakdown;

  ByStatusResponseBuilder() {
    ByStatusResponse._defaults(this);
  }

  ByStatusResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _statusBreakdown = $v.statusBreakdown?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ByStatusResponse other) {
    _$v = other as _$ByStatusResponse;
  }

  @override
  void update(void Function(ByStatusResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ByStatusResponse build() => _build();

  _$ByStatusResponse _build() {
    _$ByStatusResponse _$result;
    try {
      _$result = _$v ??
          _$ByStatusResponse._(
            statusBreakdown: _statusBreakdown?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'statusBreakdown';
        _statusBreakdown?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ByStatusResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
