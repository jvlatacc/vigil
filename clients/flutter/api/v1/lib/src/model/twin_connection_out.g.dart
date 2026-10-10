// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'twin_connection_out.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const TwinConnectionOutConnectionTypeEnum
    _$twinConnectionOutConnectionTypeEnum_socket =
    const TwinConnectionOutConnectionTypeEnum._('socket');
const TwinConnectionOutConnectionTypeEnum
    _$twinConnectionOutConnectionTypeEnum_stream =
    const TwinConnectionOutConnectionTypeEnum._('stream');
const TwinConnectionOutConnectionTypeEnum
    _$twinConnectionOutConnectionTypeEnum_session =
    const TwinConnectionOutConnectionTypeEnum._('session');

TwinConnectionOutConnectionTypeEnum
    _$twinConnectionOutConnectionTypeEnumValueOf(String name) {
  switch (name) {
    case 'socket':
      return _$twinConnectionOutConnectionTypeEnum_socket;
    case 'stream':
      return _$twinConnectionOutConnectionTypeEnum_stream;
    case 'session':
      return _$twinConnectionOutConnectionTypeEnum_session;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<TwinConnectionOutConnectionTypeEnum>
    _$twinConnectionOutConnectionTypeEnumValues = BuiltSet<
        TwinConnectionOutConnectionTypeEnum>(const <TwinConnectionOutConnectionTypeEnum>[
  _$twinConnectionOutConnectionTypeEnum_socket,
  _$twinConnectionOutConnectionTypeEnum_stream,
  _$twinConnectionOutConnectionTypeEnum_session,
]);

Serializer<TwinConnectionOutConnectionTypeEnum>
    _$twinConnectionOutConnectionTypeEnumSerializer =
    _$TwinConnectionOutConnectionTypeEnumSerializer();

class _$TwinConnectionOutConnectionTypeEnumSerializer
    implements PrimitiveSerializer<TwinConnectionOutConnectionTypeEnum> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'socket': 'socket',
    'stream': 'stream',
    'session': 'session',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'socket': 'socket',
    'stream': 'stream',
    'session': 'session',
  };

  @override
  final Iterable<Type> types = const <Type>[
    TwinConnectionOutConnectionTypeEnum
  ];
  @override
  final String wireName = 'TwinConnectionOutConnectionTypeEnum';

  @override
  Object serialize(
          Serializers serializers, TwinConnectionOutConnectionTypeEnum object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  TwinConnectionOutConnectionTypeEnum deserialize(
          Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      TwinConnectionOutConnectionTypeEnum.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

class _$TwinConnectionOut extends TwinConnectionOut {
  @override
  final BuiltMap<String, JsonObject?>? attributes;
  @override
  final TwinConnectionOutConnectionTypeEnum connectionType;
  @override
  final JsonObject? deviceId;
  @override
  final String? direction;
  @override
  final String firstSeen;
  @override
  final JsonObject? id;
  @override
  final String lastSeen;
  @override
  final String? localIp;
  @override
  final int? localPort;
  @override
  final AnyOf? processId;
  @override
  final String? protocol;
  @override
  final String? remoteIp;
  @override
  final int? remotePort;
  @override
  final String source_;
  @override
  final String? startedAt;
  @override
  final String? state;

  factory _$TwinConnectionOut(
          [void Function(TwinConnectionOutBuilder)? updates]) =>
      (TwinConnectionOutBuilder()..update(updates))._build();

  _$TwinConnectionOut._(
      {this.attributes,
      required this.connectionType,
      this.deviceId,
      this.direction,
      required this.firstSeen,
      this.id,
      required this.lastSeen,
      this.localIp,
      this.localPort,
      this.processId,
      this.protocol,
      this.remoteIp,
      this.remotePort,
      required this.source_,
      this.startedAt,
      this.state})
      : super._();
  @override
  TwinConnectionOut rebuild(void Function(TwinConnectionOutBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TwinConnectionOutBuilder toBuilder() =>
      TwinConnectionOutBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TwinConnectionOut &&
        attributes == other.attributes &&
        connectionType == other.connectionType &&
        deviceId == other.deviceId &&
        direction == other.direction &&
        firstSeen == other.firstSeen &&
        id == other.id &&
        lastSeen == other.lastSeen &&
        localIp == other.localIp &&
        localPort == other.localPort &&
        processId == other.processId &&
        protocol == other.protocol &&
        remoteIp == other.remoteIp &&
        remotePort == other.remotePort &&
        source_ == other.source_ &&
        startedAt == other.startedAt &&
        state == other.state;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, attributes.hashCode);
    _$hash = $jc(_$hash, connectionType.hashCode);
    _$hash = $jc(_$hash, deviceId.hashCode);
    _$hash = $jc(_$hash, direction.hashCode);
    _$hash = $jc(_$hash, firstSeen.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, lastSeen.hashCode);
    _$hash = $jc(_$hash, localIp.hashCode);
    _$hash = $jc(_$hash, localPort.hashCode);
    _$hash = $jc(_$hash, processId.hashCode);
    _$hash = $jc(_$hash, protocol.hashCode);
    _$hash = $jc(_$hash, remoteIp.hashCode);
    _$hash = $jc(_$hash, remotePort.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jc(_$hash, startedAt.hashCode);
    _$hash = $jc(_$hash, state.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TwinConnectionOut')
          ..add('attributes', attributes)
          ..add('connectionType', connectionType)
          ..add('deviceId', deviceId)
          ..add('direction', direction)
          ..add('firstSeen', firstSeen)
          ..add('id', id)
          ..add('lastSeen', lastSeen)
          ..add('localIp', localIp)
          ..add('localPort', localPort)
          ..add('processId', processId)
          ..add('protocol', protocol)
          ..add('remoteIp', remoteIp)
          ..add('remotePort', remotePort)
          ..add('source_', source_)
          ..add('startedAt', startedAt)
          ..add('state', state))
        .toString();
  }
}

class TwinConnectionOutBuilder
    implements Builder<TwinConnectionOut, TwinConnectionOutBuilder> {
  _$TwinConnectionOut? _$v;

  MapBuilder<String, JsonObject?>? _attributes;
  MapBuilder<String, JsonObject?> get attributes =>
      _$this._attributes ??= MapBuilder<String, JsonObject?>();
  set attributes(MapBuilder<String, JsonObject?>? attributes) =>
      _$this._attributes = attributes;

  TwinConnectionOutConnectionTypeEnum? _connectionType;
  TwinConnectionOutConnectionTypeEnum? get connectionType =>
      _$this._connectionType;
  set connectionType(TwinConnectionOutConnectionTypeEnum? connectionType) =>
      _$this._connectionType = connectionType;

  JsonObject? _deviceId;
  JsonObject? get deviceId => _$this._deviceId;
  set deviceId(JsonObject? deviceId) => _$this._deviceId = deviceId;

  String? _direction;
  String? get direction => _$this._direction;
  set direction(String? direction) => _$this._direction = direction;

  String? _firstSeen;
  String? get firstSeen => _$this._firstSeen;
  set firstSeen(String? firstSeen) => _$this._firstSeen = firstSeen;

  JsonObject? _id;
  JsonObject? get id => _$this._id;
  set id(JsonObject? id) => _$this._id = id;

  String? _lastSeen;
  String? get lastSeen => _$this._lastSeen;
  set lastSeen(String? lastSeen) => _$this._lastSeen = lastSeen;

  String? _localIp;
  String? get localIp => _$this._localIp;
  set localIp(String? localIp) => _$this._localIp = localIp;

  int? _localPort;
  int? get localPort => _$this._localPort;
  set localPort(int? localPort) => _$this._localPort = localPort;

  AnyOf? _processId;
  AnyOf? get processId => _$this._processId;
  set processId(AnyOf? processId) => _$this._processId = processId;

  String? _protocol;
  String? get protocol => _$this._protocol;
  set protocol(String? protocol) => _$this._protocol = protocol;

  String? _remoteIp;
  String? get remoteIp => _$this._remoteIp;
  set remoteIp(String? remoteIp) => _$this._remoteIp = remoteIp;

  int? _remotePort;
  int? get remotePort => _$this._remotePort;
  set remotePort(int? remotePort) => _$this._remotePort = remotePort;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  String? _startedAt;
  String? get startedAt => _$this._startedAt;
  set startedAt(String? startedAt) => _$this._startedAt = startedAt;

  String? _state;
  String? get state => _$this._state;
  set state(String? state) => _$this._state = state;

  TwinConnectionOutBuilder() {
    TwinConnectionOut._defaults(this);
  }

  TwinConnectionOutBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _attributes = $v.attributes?.toBuilder();
      _connectionType = $v.connectionType;
      _deviceId = $v.deviceId;
      _direction = $v.direction;
      _firstSeen = $v.firstSeen;
      _id = $v.id;
      _lastSeen = $v.lastSeen;
      _localIp = $v.localIp;
      _localPort = $v.localPort;
      _processId = $v.processId;
      _protocol = $v.protocol;
      _remoteIp = $v.remoteIp;
      _remotePort = $v.remotePort;
      _source_ = $v.source_;
      _startedAt = $v.startedAt;
      _state = $v.state;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TwinConnectionOut other) {
    _$v = other as _$TwinConnectionOut;
  }

  @override
  void update(void Function(TwinConnectionOutBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TwinConnectionOut build() => _build();

  _$TwinConnectionOut _build() {
    _$TwinConnectionOut _$result;
    try {
      _$result = _$v ??
          _$TwinConnectionOut._(
            attributes: _attributes?.build(),
            connectionType: BuiltValueNullFieldError.checkNotNull(
                connectionType, r'TwinConnectionOut', 'connectionType'),
            deviceId: deviceId,
            direction: direction,
            firstSeen: BuiltValueNullFieldError.checkNotNull(
                firstSeen, r'TwinConnectionOut', 'firstSeen'),
            id: id,
            lastSeen: BuiltValueNullFieldError.checkNotNull(
                lastSeen, r'TwinConnectionOut', 'lastSeen'),
            localIp: localIp,
            localPort: localPort,
            processId: processId,
            protocol: protocol,
            remoteIp: remoteIp,
            remotePort: remotePort,
            source_: BuiltValueNullFieldError.checkNotNull(
                source_, r'TwinConnectionOut', 'source_'),
            startedAt: startedAt,
            state: state,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'attributes';
        _attributes?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'TwinConnectionOut', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
