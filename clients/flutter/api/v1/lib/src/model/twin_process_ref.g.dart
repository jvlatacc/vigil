// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'twin_process_ref.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$TwinProcessRef extends TwinProcessRef {
  @override
  final String device;
  @override
  final String name;
  @override
  final int pid;

  factory _$TwinProcessRef([void Function(TwinProcessRefBuilder)? updates]) =>
      (TwinProcessRefBuilder()..update(updates))._build();

  _$TwinProcessRef._(
      {required this.device, required this.name, required this.pid})
      : super._();
  @override
  TwinProcessRef rebuild(void Function(TwinProcessRefBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TwinProcessRefBuilder toBuilder() => TwinProcessRefBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TwinProcessRef &&
        device == other.device &&
        name == other.name &&
        pid == other.pid;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, device.hashCode);
    _$hash = $jc(_$hash, name.hashCode);
    _$hash = $jc(_$hash, pid.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TwinProcessRef')
          ..add('device', device)
          ..add('name', name)
          ..add('pid', pid))
        .toString();
  }
}

class TwinProcessRefBuilder
    implements Builder<TwinProcessRef, TwinProcessRefBuilder> {
  _$TwinProcessRef? _$v;

  String? _device;
  String? get device => _$this._device;
  set device(String? device) => _$this._device = device;

  String? _name;
  String? get name => _$this._name;
  set name(String? name) => _$this._name = name;

  int? _pid;
  int? get pid => _$this._pid;
  set pid(int? pid) => _$this._pid = pid;

  TwinProcessRefBuilder() {
    TwinProcessRef._defaults(this);
  }

  TwinProcessRefBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _device = $v.device;
      _name = $v.name;
      _pid = $v.pid;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TwinProcessRef other) {
    _$v = other as _$TwinProcessRef;
  }

  @override
  void update(void Function(TwinProcessRefBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TwinProcessRef build() => _build();

  _$TwinProcessRef _build() {
    final _$result = _$v ??
        _$TwinProcessRef._(
          device: BuiltValueNullFieldError.checkNotNull(
              device, r'TwinProcessRef', 'device'),
          name: BuiltValueNullFieldError.checkNotNull(
              name, r'TwinProcessRef', 'name'),
          pid: BuiltValueNullFieldError.checkNotNull(
              pid, r'TwinProcessRef', 'pid'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
