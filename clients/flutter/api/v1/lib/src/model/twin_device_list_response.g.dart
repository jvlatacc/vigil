// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'twin_device_list_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$TwinDeviceListResponse extends TwinDeviceListResponse {
  @override
  final BuiltList<TwinDeviceOut>? devices;
  @override
  final int total;

  factory _$TwinDeviceListResponse(
          [void Function(TwinDeviceListResponseBuilder)? updates]) =>
      (TwinDeviceListResponseBuilder()..update(updates))._build();

  _$TwinDeviceListResponse._({this.devices, required this.total}) : super._();
  @override
  TwinDeviceListResponse rebuild(
          void Function(TwinDeviceListResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TwinDeviceListResponseBuilder toBuilder() =>
      TwinDeviceListResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TwinDeviceListResponse &&
        devices == other.devices &&
        total == other.total;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, devices.hashCode);
    _$hash = $jc(_$hash, total.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TwinDeviceListResponse')
          ..add('devices', devices)
          ..add('total', total))
        .toString();
  }
}

class TwinDeviceListResponseBuilder
    implements Builder<TwinDeviceListResponse, TwinDeviceListResponseBuilder> {
  _$TwinDeviceListResponse? _$v;

  ListBuilder<TwinDeviceOut>? _devices;
  ListBuilder<TwinDeviceOut> get devices =>
      _$this._devices ??= ListBuilder<TwinDeviceOut>();
  set devices(ListBuilder<TwinDeviceOut>? devices) => _$this._devices = devices;

  int? _total;
  int? get total => _$this._total;
  set total(int? total) => _$this._total = total;

  TwinDeviceListResponseBuilder() {
    TwinDeviceListResponse._defaults(this);
  }

  TwinDeviceListResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _devices = $v.devices?.toBuilder();
      _total = $v.total;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TwinDeviceListResponse other) {
    _$v = other as _$TwinDeviceListResponse;
  }

  @override
  void update(void Function(TwinDeviceListResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TwinDeviceListResponse build() => _build();

  _$TwinDeviceListResponse _build() {
    _$TwinDeviceListResponse _$result;
    try {
      _$result = _$v ??
          _$TwinDeviceListResponse._(
            devices: _devices?.build(),
            total: BuiltValueNullFieldError.checkNotNull(
                total, r'TwinDeviceListResponse', 'total'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'devices';
        _devices?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'TwinDeviceListResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
