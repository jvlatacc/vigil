// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'twin_graph_payload.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$TwinGraphPayload extends TwinGraphPayload {
  @override
  final BuiltList<TwinConnectionOut>? connections;
  @override
  final BuiltList<TwinDeviceOut>? devices;
  @override
  final BuiltList<TwinEdgeOut>? edges;
  @override
  final String generatedAt;
  @override
  final BuiltList<TwinProcessOut>? processes;

  factory _$TwinGraphPayload(
          [void Function(TwinGraphPayloadBuilder)? updates]) =>
      (TwinGraphPayloadBuilder()..update(updates))._build();

  _$TwinGraphPayload._(
      {this.connections,
      this.devices,
      this.edges,
      required this.generatedAt,
      this.processes})
      : super._();
  @override
  TwinGraphPayload rebuild(void Function(TwinGraphPayloadBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TwinGraphPayloadBuilder toBuilder() =>
      TwinGraphPayloadBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TwinGraphPayload &&
        connections == other.connections &&
        devices == other.devices &&
        edges == other.edges &&
        generatedAt == other.generatedAt &&
        processes == other.processes;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, connections.hashCode);
    _$hash = $jc(_$hash, devices.hashCode);
    _$hash = $jc(_$hash, edges.hashCode);
    _$hash = $jc(_$hash, generatedAt.hashCode);
    _$hash = $jc(_$hash, processes.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TwinGraphPayload')
          ..add('connections', connections)
          ..add('devices', devices)
          ..add('edges', edges)
          ..add('generatedAt', generatedAt)
          ..add('processes', processes))
        .toString();
  }
}

class TwinGraphPayloadBuilder
    implements Builder<TwinGraphPayload, TwinGraphPayloadBuilder> {
  _$TwinGraphPayload? _$v;

  ListBuilder<TwinConnectionOut>? _connections;
  ListBuilder<TwinConnectionOut> get connections =>
      _$this._connections ??= ListBuilder<TwinConnectionOut>();
  set connections(ListBuilder<TwinConnectionOut>? connections) =>
      _$this._connections = connections;

  ListBuilder<TwinDeviceOut>? _devices;
  ListBuilder<TwinDeviceOut> get devices =>
      _$this._devices ??= ListBuilder<TwinDeviceOut>();
  set devices(ListBuilder<TwinDeviceOut>? devices) => _$this._devices = devices;

  ListBuilder<TwinEdgeOut>? _edges;
  ListBuilder<TwinEdgeOut> get edges =>
      _$this._edges ??= ListBuilder<TwinEdgeOut>();
  set edges(ListBuilder<TwinEdgeOut>? edges) => _$this._edges = edges;

  String? _generatedAt;
  String? get generatedAt => _$this._generatedAt;
  set generatedAt(String? generatedAt) => _$this._generatedAt = generatedAt;

  ListBuilder<TwinProcessOut>? _processes;
  ListBuilder<TwinProcessOut> get processes =>
      _$this._processes ??= ListBuilder<TwinProcessOut>();
  set processes(ListBuilder<TwinProcessOut>? processes) =>
      _$this._processes = processes;

  TwinGraphPayloadBuilder() {
    TwinGraphPayload._defaults(this);
  }

  TwinGraphPayloadBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _connections = $v.connections?.toBuilder();
      _devices = $v.devices?.toBuilder();
      _edges = $v.edges?.toBuilder();
      _generatedAt = $v.generatedAt;
      _processes = $v.processes?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TwinGraphPayload other) {
    _$v = other as _$TwinGraphPayload;
  }

  @override
  void update(void Function(TwinGraphPayloadBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TwinGraphPayload build() => _build();

  _$TwinGraphPayload _build() {
    _$TwinGraphPayload _$result;
    try {
      _$result = _$v ??
          _$TwinGraphPayload._(
            connections: _connections?.build(),
            devices: _devices?.build(),
            edges: _edges?.build(),
            generatedAt: BuiltValueNullFieldError.checkNotNull(
                generatedAt, r'TwinGraphPayload', 'generatedAt'),
            processes: _processes?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'connections';
        _connections?.build();
        _$failedField = 'devices';
        _devices?.build();
        _$failedField = 'edges';
        _edges?.build();

        _$failedField = 'processes';
        _processes?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'TwinGraphPayload', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
