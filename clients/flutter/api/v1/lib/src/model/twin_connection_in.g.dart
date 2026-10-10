// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'twin_connection_in.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const TwinConnectionInConnectionTypeEnum
    _$twinConnectionInConnectionTypeEnum_socket =
    const TwinConnectionInConnectionTypeEnum._('socket');
const TwinConnectionInConnectionTypeEnum
    _$twinConnectionInConnectionTypeEnum_stream =
    const TwinConnectionInConnectionTypeEnum._('stream');
const TwinConnectionInConnectionTypeEnum
    _$twinConnectionInConnectionTypeEnum_session =
    const TwinConnectionInConnectionTypeEnum._('session');

TwinConnectionInConnectionTypeEnum _$twinConnectionInConnectionTypeEnumValueOf(
    String name) {
  switch (name) {
    case 'socket':
      return _$twinConnectionInConnectionTypeEnum_socket;
    case 'stream':
      return _$twinConnectionInConnectionTypeEnum_stream;
    case 'session':
      return _$twinConnectionInConnectionTypeEnum_session;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<TwinConnectionInConnectionTypeEnum>
    _$twinConnectionInConnectionTypeEnumValues = BuiltSet<
        TwinConnectionInConnectionTypeEnum>(const <TwinConnectionInConnectionTypeEnum>[
  _$twinConnectionInConnectionTypeEnum_socket,
  _$twinConnectionInConnectionTypeEnum_stream,
  _$twinConnectionInConnectionTypeEnum_session,
]);

const TwinConnectionInDirectionEnum _$twinConnectionInDirectionEnum_inbound =
    const TwinConnectionInDirectionEnum._('inbound');
const TwinConnectionInDirectionEnum _$twinConnectionInDirectionEnum_outbound =
    const TwinConnectionInDirectionEnum._('outbound');

TwinConnectionInDirectionEnum _$twinConnectionInDirectionEnumValueOf(
    String name) {
  switch (name) {
    case 'inbound':
      return _$twinConnectionInDirectionEnum_inbound;
    case 'outbound':
      return _$twinConnectionInDirectionEnum_outbound;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<TwinConnectionInDirectionEnum>
    _$twinConnectionInDirectionEnumValues = BuiltSet<
        TwinConnectionInDirectionEnum>(const <TwinConnectionInDirectionEnum>[
  _$twinConnectionInDirectionEnum_inbound,
  _$twinConnectionInDirectionEnum_outbound,
]);

Serializer<TwinConnectionInConnectionTypeEnum>
    _$twinConnectionInConnectionTypeEnumSerializer =
    _$TwinConnectionInConnectionTypeEnumSerializer();
Serializer<TwinConnectionInDirectionEnum>
    _$twinConnectionInDirectionEnumSerializer =
    _$TwinConnectionInDirectionEnumSerializer();

class _$TwinConnectionInConnectionTypeEnumSerializer
    implements PrimitiveSerializer<TwinConnectionInConnectionTypeEnum> {
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
  final Iterable<Type> types = const <Type>[TwinConnectionInConnectionTypeEnum];
  @override
  final String wireName = 'TwinConnectionInConnectionTypeEnum';

  @override
  Object serialize(
          Serializers serializers, TwinConnectionInConnectionTypeEnum object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  TwinConnectionInConnectionTypeEnum deserialize(
          Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      TwinConnectionInConnectionTypeEnum.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

class _$TwinConnectionInDirectionEnumSerializer
    implements PrimitiveSerializer<TwinConnectionInDirectionEnum> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'inbound': 'inbound',
    'outbound': 'outbound',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'inbound': 'inbound',
    'outbound': 'outbound',
  };

  @override
  final Iterable<Type> types = const <Type>[TwinConnectionInDirectionEnum];
  @override
  final String wireName = 'TwinConnectionInDirectionEnum';

  @override
  Object serialize(
          Serializers serializers, TwinConnectionInDirectionEnum object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  TwinConnectionInDirectionEnum deserialize(
          Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      TwinConnectionInDirectionEnum.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

class _$TwinConnectionIn extends TwinConnectionIn {
  @override
  final BuiltMap<String, JsonObject?>? attributes;
  @override
  final TwinConnectionInConnectionTypeEnum connectionType;
  @override
  final String? device;
  @override
  final TwinConnectionInDirectionEnum? direction;
  @override
  final String? localIp;
  @override
  final int? localPort;
  @override
  final TwinProcessRef? process;
  @override
  final String? protocol;
  @override
  final String? remoteIp;
  @override
  final int? remotePort;
  @override
  final DateTime? startedAt;
  @override
  final String? state;

  factory _$TwinConnectionIn(
          [void Function(TwinConnectionInBuilder)? updates]) =>
      (TwinConnectionInBuilder()..update(updates))._build();

  _$TwinConnectionIn._(
      {this.attributes,
      required this.connectionType,
      this.device,
      this.direction,
      this.localIp,
      this.localPort,
      this.process,
      this.protocol,
      this.remoteIp,
      this.remotePort,
      this.startedAt,
      this.state})
      : super._();
  @override
  TwinConnectionIn rebuild(void Function(TwinConnectionInBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TwinConnectionInBuilder toBuilder() =>
      TwinConnectionInBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TwinConnectionIn &&
        attributes == other.attributes &&
        connectionType == other.connectionType &&
        device == other.device &&
        direction == other.direction &&
        localIp == other.localIp &&
        localPort == other.localPort &&
        process == other.process &&
        protocol == other.protocol &&
        remoteIp == other.remoteIp &&
        remotePort == other.remotePort &&
        startedAt == other.startedAt &&
        state == other.state;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, attributes.hashCode);
    _$hash = $jc(_$hash, connectionType.hashCode);
    _$hash = $jc(_$hash, device.hashCode);
    _$hash = $jc(_$hash, direction.hashCode);
    _$hash = $jc(_$hash, localIp.hashCode);
    _$hash = $jc(_$hash, localPort.hashCode);
    _$hash = $jc(_$hash, process.hashCode);
    _$hash = $jc(_$hash, protocol.hashCode);
    _$hash = $jc(_$hash, remoteIp.hashCode);
    _$hash = $jc(_$hash, remotePort.hashCode);
    _$hash = $jc(_$hash, startedAt.hashCode);
    _$hash = $jc(_$hash, state.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TwinConnectionIn')
          ..add('attributes', attributes)
          ..add('connectionType', connectionType)
          ..add('device', device)
          ..add('direction', direction)
          ..add('localIp', localIp)
          ..add('localPort', localPort)
          ..add('process', process)
          ..add('protocol', protocol)
          ..add('remoteIp', remoteIp)
          ..add('remotePort', remotePort)
          ..add('startedAt', startedAt)
          ..add('state', state))
        .toString();
  }
}

class TwinConnectionInBuilder
    implements Builder<TwinConnectionIn, TwinConnectionInBuilder> {
  _$TwinConnectionIn? _$v;

  MapBuilder<String, JsonObject?>? _attributes;
  MapBuilder<String, JsonObject?> get attributes =>
      _$this._attributes ??= MapBuilder<String, JsonObject?>();
  set attributes(MapBuilder<String, JsonObject?>? attributes) =>
      _$this._attributes = attributes;

  TwinConnectionInConnectionTypeEnum? _connectionType;
  TwinConnectionInConnectionTypeEnum? get connectionType =>
      _$this._connectionType;
  set connectionType(TwinConnectionInConnectionTypeEnum? connectionType) =>
      _$this._connectionType = connectionType;

  String? _device;
  String? get device => _$this._device;
  set device(String? device) => _$this._device = device;

  TwinConnectionInDirectionEnum? _direction;
  TwinConnectionInDirectionEnum? get direction => _$this._direction;
  set direction(TwinConnectionInDirectionEnum? direction) =>
      _$this._direction = direction;

  String? _localIp;
  String? get localIp => _$this._localIp;
  set localIp(String? localIp) => _$this._localIp = localIp;

  int? _localPort;
  int? get localPort => _$this._localPort;
  set localPort(int? localPort) => _$this._localPort = localPort;

  TwinProcessRefBuilder? _process;
  TwinProcessRefBuilder get process =>
      _$this._process ??= TwinProcessRefBuilder();
  set process(TwinProcessRefBuilder? process) => _$this._process = process;

  String? _protocol;
  String? get protocol => _$this._protocol;
  set protocol(String? protocol) => _$this._protocol = protocol;

  String? _remoteIp;
  String? get remoteIp => _$this._remoteIp;
  set remoteIp(String? remoteIp) => _$this._remoteIp = remoteIp;

  int? _remotePort;
  int? get remotePort => _$this._remotePort;
  set remotePort(int? remotePort) => _$this._remotePort = remotePort;

  DateTime? _startedAt;
  DateTime? get startedAt => _$this._startedAt;
  set startedAt(DateTime? startedAt) => _$this._startedAt = startedAt;

  String? _state;
  String? get state => _$this._state;
  set state(String? state) => _$this._state = state;

  TwinConnectionInBuilder() {
    TwinConnectionIn._defaults(this);
  }

  TwinConnectionInBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _attributes = $v.attributes?.toBuilder();
      _connectionType = $v.connectionType;
      _device = $v.device;
      _direction = $v.direction;
      _localIp = $v.localIp;
      _localPort = $v.localPort;
      _process = $v.process?.toBuilder();
      _protocol = $v.protocol;
      _remoteIp = $v.remoteIp;
      _remotePort = $v.remotePort;
      _startedAt = $v.startedAt;
      _state = $v.state;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TwinConnectionIn other) {
    _$v = other as _$TwinConnectionIn;
  }

  @override
  void update(void Function(TwinConnectionInBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TwinConnectionIn build() => _build();

  _$TwinConnectionIn _build() {
    _$TwinConnectionIn _$result;
    try {
      _$result = _$v ??
          _$TwinConnectionIn._(
            attributes: _attributes?.build(),
            connectionType: BuiltValueNullFieldError.checkNotNull(
                connectionType, r'TwinConnectionIn', 'connectionType'),
            device: device,
            direction: direction,
            localIp: localIp,
            localPort: localPort,
            process: _process?.build(),
            protocol: protocol,
            remoteIp: remoteIp,
            remotePort: remotePort,
            startedAt: startedAt,
            state: state,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'attributes';
        _attributes?.build();

        _$failedField = 'process';
        _process?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'TwinConnectionIn', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
