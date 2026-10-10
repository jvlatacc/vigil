// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'twin_ingest_batch.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$TwinIngestBatch extends TwinIngestBatch {
  @override
  final BuiltList<TwinConnectionIn>? connections;
  @override
  final BuiltList<TwinDeviceIn>? devices;
  @override
  final BuiltList<TwinProcessIn>? processes;
  @override
  final String source_;

  factory _$TwinIngestBatch([void Function(TwinIngestBatchBuilder)? updates]) =>
      (TwinIngestBatchBuilder()..update(updates))._build();

  _$TwinIngestBatch._(
      {this.connections, this.devices, this.processes, required this.source_})
      : super._();
  @override
  TwinIngestBatch rebuild(void Function(TwinIngestBatchBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TwinIngestBatchBuilder toBuilder() => TwinIngestBatchBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TwinIngestBatch &&
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
    return (newBuiltValueToStringHelper(r'TwinIngestBatch')
          ..add('connections', connections)
          ..add('devices', devices)
          ..add('processes', processes)
          ..add('source_', source_))
        .toString();
  }
}

class TwinIngestBatchBuilder
    implements Builder<TwinIngestBatch, TwinIngestBatchBuilder> {
  _$TwinIngestBatch? _$v;

  ListBuilder<TwinConnectionIn>? _connections;
  ListBuilder<TwinConnectionIn> get connections =>
      _$this._connections ??= ListBuilder<TwinConnectionIn>();
  set connections(ListBuilder<TwinConnectionIn>? connections) =>
      _$this._connections = connections;

  ListBuilder<TwinDeviceIn>? _devices;
  ListBuilder<TwinDeviceIn> get devices =>
      _$this._devices ??= ListBuilder<TwinDeviceIn>();
  set devices(ListBuilder<TwinDeviceIn>? devices) => _$this._devices = devices;

  ListBuilder<TwinProcessIn>? _processes;
  ListBuilder<TwinProcessIn> get processes =>
      _$this._processes ??= ListBuilder<TwinProcessIn>();
  set processes(ListBuilder<TwinProcessIn>? processes) =>
      _$this._processes = processes;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  TwinIngestBatchBuilder() {
    TwinIngestBatch._defaults(this);
  }

  TwinIngestBatchBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _connections = $v.connections?.toBuilder();
      _devices = $v.devices?.toBuilder();
      _processes = $v.processes?.toBuilder();
      _source_ = $v.source_;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TwinIngestBatch other) {
    _$v = other as _$TwinIngestBatch;
  }

  @override
  void update(void Function(TwinIngestBatchBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TwinIngestBatch build() => _build();

  _$TwinIngestBatch _build() {
    _$TwinIngestBatch _$result;
    try {
      _$result = _$v ??
          _$TwinIngestBatch._(
            connections: _connections?.build(),
            devices: _devices?.build(),
            processes: _processes?.build(),
            source_: BuiltValueNullFieldError.checkNotNull(
                source_, r'TwinIngestBatch', 'source_'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'connections';
        _connections?.build();
        _$failedField = 'devices';
        _devices?.build();
        _$failedField = 'processes';
        _processes?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'TwinIngestBatch', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
