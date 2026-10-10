// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'twin_ingest_result.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$TwinIngestResult extends TwinIngestResult {
  @override
  final int connections;
  @override
  final int devices;
  @override
  final int processes;
  @override
  final String source_;

  factory _$TwinIngestResult(
          [void Function(TwinIngestResultBuilder)? updates]) =>
      (TwinIngestResultBuilder()..update(updates))._build();

  _$TwinIngestResult._(
      {required this.connections,
      required this.devices,
      required this.processes,
      required this.source_})
      : super._();
  @override
  TwinIngestResult rebuild(void Function(TwinIngestResultBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TwinIngestResultBuilder toBuilder() =>
      TwinIngestResultBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TwinIngestResult &&
        connections == other.connections &&
        devices == other.devices &&
        processes == other.processes &&
        source_ == other.source_;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, connections.hashCode);
    _$hash = $jc(_$hash, devices.hashCode);
    _$hash = $jc(_$hash, processes.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TwinIngestResult')
          ..add('connections', connections)
          ..add('devices', devices)
          ..add('processes', processes)
          ..add('source_', source_))
        .toString();
  }
}

class TwinIngestResultBuilder
    implements Builder<TwinIngestResult, TwinIngestResultBuilder> {
  _$TwinIngestResult? _$v;

  int? _connections;
  int? get connections => _$this._connections;
  set connections(int? connections) => _$this._connections = connections;

  int? _devices;
  int? get devices => _$this._devices;
  set devices(int? devices) => _$this._devices = devices;

  int? _processes;
  int? get processes => _$this._processes;
  set processes(int? processes) => _$this._processes = processes;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  TwinIngestResultBuilder() {
    TwinIngestResult._defaults(this);
  }

  TwinIngestResultBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _connections = $v.connections;
      _devices = $v.devices;
      _processes = $v.processes;
      _source_ = $v.source_;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TwinIngestResult other) {
    _$v = other as _$TwinIngestResult;
  }

  @override
  void update(void Function(TwinIngestResultBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TwinIngestResult build() => _build();

  _$TwinIngestResult _build() {
    final _$result = _$v ??
        _$TwinIngestResult._(
          connections: BuiltValueNullFieldError.checkNotNull(
              connections, r'TwinIngestResult', 'connections'),
          devices: BuiltValueNullFieldError.checkNotNull(
              devices, r'TwinIngestResult', 'devices'),
          processes: BuiltValueNullFieldError.checkNotNull(
              processes, r'TwinIngestResult', 'processes'),
          source_: BuiltValueNullFieldError.checkNotNull(
              source_, r'TwinIngestResult', 'source_'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
