// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'twin_device_in.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$TwinDeviceIn extends TwinDeviceIn {
  @override
  final BuiltMap<String, JsonObject?>? attributes;
  @override
  final String? deviceType;
  @override
  final String? hostname;
  @override
  final String? ipAddress;
  @override
  final String? macAddress;
  @override
  final String? osInfo;
  @override
  final String? serialNumber;

  factory _$TwinDeviceIn([void Function(TwinDeviceInBuilder)? updates]) =>
      (TwinDeviceInBuilder()..update(updates))._build();

  _$TwinDeviceIn._(
      {this.attributes,
      this.deviceType,
      this.hostname,
      this.ipAddress,
      this.macAddress,
      this.osInfo,
      this.serialNumber})
      : super._();
  @override
  TwinDeviceIn rebuild(void Function(TwinDeviceInBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TwinDeviceInBuilder toBuilder() => TwinDeviceInBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TwinDeviceIn &&
        attributes == other.attributes &&
        deviceType == other.deviceType &&
        hostname == other.hostname &&
        ipAddress == other.ipAddress &&
        macAddress == other.macAddress &&
        osInfo == other.osInfo &&
        serialNumber == other.serialNumber;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, attributes.hashCode);
    _$hash = $jc(_$hash, deviceType.hashCode);
    _$hash = $jc(_$hash, hostname.hashCode);
    _$hash = $jc(_$hash, ipAddress.hashCode);
    _$hash = $jc(_$hash, macAddress.hashCode);
    _$hash = $jc(_$hash, osInfo.hashCode);
    _$hash = $jc(_$hash, serialNumber.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TwinDeviceIn')
          ..add('attributes', attributes)
          ..add('deviceType', deviceType)
          ..add('hostname', hostname)
          ..add('ipAddress', ipAddress)
          ..add('macAddress', macAddress)
          ..add('osInfo', osInfo)
          ..add('serialNumber', serialNumber))
        .toString();
  }
}

class TwinDeviceInBuilder
    implements Builder<TwinDeviceIn, TwinDeviceInBuilder> {
  _$TwinDeviceIn? _$v;

  MapBuilder<String, JsonObject?>? _attributes;
  MapBuilder<String, JsonObject?> get attributes =>
      _$this._attributes ??= MapBuilder<String, JsonObject?>();
  set attributes(MapBuilder<String, JsonObject?>? attributes) =>
      _$this._attributes = attributes;

  String? _deviceType;
  String? get deviceType => _$this._deviceType;
  set deviceType(String? deviceType) => _$this._deviceType = deviceType;

  String? _hostname;
  String? get hostname => _$this._hostname;
  set hostname(String? hostname) => _$this._hostname = hostname;

  String? _ipAddress;
  String? get ipAddress => _$this._ipAddress;
  set ipAddress(String? ipAddress) => _$this._ipAddress = ipAddress;

  String? _macAddress;
  String? get macAddress => _$this._macAddress;
  set macAddress(String? macAddress) => _$this._macAddress = macAddress;

  String? _osInfo;
  String? get osInfo => _$this._osInfo;
  set osInfo(String? osInfo) => _$this._osInfo = osInfo;

  String? _serialNumber;
  String? get serialNumber => _$this._serialNumber;
  set serialNumber(String? serialNumber) => _$this._serialNumber = serialNumber;

  TwinDeviceInBuilder() {
    TwinDeviceIn._defaults(this);
  }

  TwinDeviceInBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _attributes = $v.attributes?.toBuilder();
      _deviceType = $v.deviceType;
      _hostname = $v.hostname;
      _ipAddress = $v.ipAddress;
      _macAddress = $v.macAddress;
      _osInfo = $v.osInfo;
      _serialNumber = $v.serialNumber;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TwinDeviceIn other) {
    _$v = other as _$TwinDeviceIn;
  }

  @override
  void update(void Function(TwinDeviceInBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TwinDeviceIn build() => _build();

  _$TwinDeviceIn _build() {
    _$TwinDeviceIn _$result;
    try {
      _$result = _$v ??
          _$TwinDeviceIn._(
            attributes: _attributes?.build(),
            deviceType: deviceType,
            hostname: hostname,
            ipAddress: ipAddress,
            macAddress: macAddress,
            osInfo: osInfo,
            serialNumber: serialNumber,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'attributes';
        _attributes?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'TwinDeviceIn', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
