// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'twin_device_out.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$TwinDeviceOut extends TwinDeviceOut {
  @override
  final BuiltMap<String, JsonObject?>? attributes;
  @override
  final String deviceKey;
  @override
  final String deviceType;
  @override
  final String firstSeen;
  @override
  final String? hostname;
  @override
  final JsonObject? id;
  @override
  final String? ipAddress;
  @override
  final String lastSeen;
  @override
  final String? macAddress;
  @override
  final String? osInfo;
  @override
  final String? serialNumber;
  @override
  final String source_;

  factory _$TwinDeviceOut([void Function(TwinDeviceOutBuilder)? updates]) =>
      (TwinDeviceOutBuilder()..update(updates))._build();

  _$TwinDeviceOut._(
      {this.attributes,
      required this.deviceKey,
      required this.deviceType,
      required this.firstSeen,
      this.hostname,
      this.id,
      this.ipAddress,
      required this.lastSeen,
      this.macAddress,
      this.osInfo,
      this.serialNumber,
      required this.source_})
      : super._();
  @override
  TwinDeviceOut rebuild(void Function(TwinDeviceOutBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TwinDeviceOutBuilder toBuilder() => TwinDeviceOutBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TwinDeviceOut &&
        attributes == other.attributes &&
        deviceKey == other.deviceKey &&
        deviceType == other.deviceType &&
        firstSeen == other.firstSeen &&
        hostname == other.hostname &&
        id == other.id &&
        ipAddress == other.ipAddress &&
        lastSeen == other.lastSeen &&
        macAddress == other.macAddress &&
        osInfo == other.osInfo &&
        serialNumber == other.serialNumber &&
        source_ == other.source_;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, attributes.hashCode);
    _$hash = $jc(_$hash, deviceKey.hashCode);
    _$hash = $jc(_$hash, deviceType.hashCode);
    _$hash = $jc(_$hash, firstSeen.hashCode);
    _$hash = $jc(_$hash, hostname.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, ipAddress.hashCode);
    _$hash = $jc(_$hash, lastSeen.hashCode);
    _$hash = $jc(_$hash, macAddress.hashCode);
    _$hash = $jc(_$hash, osInfo.hashCode);
    _$hash = $jc(_$hash, serialNumber.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TwinDeviceOut')
          ..add('attributes', attributes)
          ..add('deviceKey', deviceKey)
          ..add('deviceType', deviceType)
          ..add('firstSeen', firstSeen)
          ..add('hostname', hostname)
          ..add('id', id)
          ..add('ipAddress', ipAddress)
          ..add('lastSeen', lastSeen)
          ..add('macAddress', macAddress)
          ..add('osInfo', osInfo)
          ..add('serialNumber', serialNumber)
          ..add('source_', source_))
        .toString();
  }
}

class TwinDeviceOutBuilder
    implements Builder<TwinDeviceOut, TwinDeviceOutBuilder> {
  _$TwinDeviceOut? _$v;

  MapBuilder<String, JsonObject?>? _attributes;
  MapBuilder<String, JsonObject?> get attributes =>
      _$this._attributes ??= MapBuilder<String, JsonObject?>();
  set attributes(MapBuilder<String, JsonObject?>? attributes) =>
      _$this._attributes = attributes;

  String? _deviceKey;
  String? get deviceKey => _$this._deviceKey;
  set deviceKey(String? deviceKey) => _$this._deviceKey = deviceKey;

  String? _deviceType;
  String? get deviceType => _$this._deviceType;
  set deviceType(String? deviceType) => _$this._deviceType = deviceType;

  String? _firstSeen;
  String? get firstSeen => _$this._firstSeen;
  set firstSeen(String? firstSeen) => _$this._firstSeen = firstSeen;

  String? _hostname;
  String? get hostname => _$this._hostname;
  set hostname(String? hostname) => _$this._hostname = hostname;

  JsonObject? _id;
  JsonObject? get id => _$this._id;
  set id(JsonObject? id) => _$this._id = id;

  String? _ipAddress;
  String? get ipAddress => _$this._ipAddress;
  set ipAddress(String? ipAddress) => _$this._ipAddress = ipAddress;

  String? _lastSeen;
  String? get lastSeen => _$this._lastSeen;
  set lastSeen(String? lastSeen) => _$this._lastSeen = lastSeen;

  String? _macAddress;
  String? get macAddress => _$this._macAddress;
  set macAddress(String? macAddress) => _$this._macAddress = macAddress;

  String? _osInfo;
  String? get osInfo => _$this._osInfo;
  set osInfo(String? osInfo) => _$this._osInfo = osInfo;

  String? _serialNumber;
  String? get serialNumber => _$this._serialNumber;
  set serialNumber(String? serialNumber) => _$this._serialNumber = serialNumber;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  TwinDeviceOutBuilder() {
    TwinDeviceOut._defaults(this);
  }

  TwinDeviceOutBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _attributes = $v.attributes?.toBuilder();
      _deviceKey = $v.deviceKey;
      _deviceType = $v.deviceType;
      _firstSeen = $v.firstSeen;
      _hostname = $v.hostname;
      _id = $v.id;
      _ipAddress = $v.ipAddress;
      _lastSeen = $v.lastSeen;
      _macAddress = $v.macAddress;
      _osInfo = $v.osInfo;
      _serialNumber = $v.serialNumber;
      _source_ = $v.source_;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TwinDeviceOut other) {
    _$v = other as _$TwinDeviceOut;
  }

  @override
  void update(void Function(TwinDeviceOutBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TwinDeviceOut build() => _build();

  _$TwinDeviceOut _build() {
    _$TwinDeviceOut _$result;
    try {
      _$result = _$v ??
          _$TwinDeviceOut._(
            attributes: _attributes?.build(),
            deviceKey: BuiltValueNullFieldError.checkNotNull(
                deviceKey, r'TwinDeviceOut', 'deviceKey'),
            deviceType: BuiltValueNullFieldError.checkNotNull(
                deviceType, r'TwinDeviceOut', 'deviceType'),
            firstSeen: BuiltValueNullFieldError.checkNotNull(
                firstSeen, r'TwinDeviceOut', 'firstSeen'),
            hostname: hostname,
            id: id,
            ipAddress: ipAddress,
            lastSeen: BuiltValueNullFieldError.checkNotNull(
                lastSeen, r'TwinDeviceOut', 'lastSeen'),
            macAddress: macAddress,
            osInfo: osInfo,
            serialNumber: serialNumber,
            source_: BuiltValueNullFieldError.checkNotNull(
                source_, r'TwinDeviceOut', 'source_'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'attributes';
        _attributes?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'TwinDeviceOut', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
