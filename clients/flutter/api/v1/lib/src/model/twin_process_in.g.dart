// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'twin_process_in.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$TwinProcessIn extends TwinProcessIn {
  @override
  final BuiltMap<String, JsonObject?>? attributes;
  @override
  final String? command;
  @override
  final String device;
  @override
  final String name;
  @override
  final int pid;
  @override
  final DateTime? startedAt;
  @override
  final String? user;

  factory _$TwinProcessIn([void Function(TwinProcessInBuilder)? updates]) =>
      (TwinProcessInBuilder()..update(updates))._build();

  _$TwinProcessIn._(
      {this.attributes,
      this.command,
      required this.device,
      required this.name,
      required this.pid,
      this.startedAt,
      this.user})
      : super._();
  @override
  TwinProcessIn rebuild(void Function(TwinProcessInBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TwinProcessInBuilder toBuilder() => TwinProcessInBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TwinProcessIn &&
        attributes == other.attributes &&
        command == other.command &&
        device == other.device &&
        name == other.name &&
        pid == other.pid &&
        startedAt == other.startedAt &&
        user == other.user;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, attributes.hashCode);
    _$hash = $jc(_$hash, command.hashCode);
    _$hash = $jc(_$hash, device.hashCode);
    _$hash = $jc(_$hash, name.hashCode);
    _$hash = $jc(_$hash, pid.hashCode);
    _$hash = $jc(_$hash, startedAt.hashCode);
    _$hash = $jc(_$hash, user.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TwinProcessIn')
          ..add('attributes', attributes)
          ..add('command', command)
          ..add('device', device)
          ..add('name', name)
          ..add('pid', pid)
          ..add('startedAt', startedAt)
          ..add('user', user))
        .toString();
  }
}

class TwinProcessInBuilder
    implements Builder<TwinProcessIn, TwinProcessInBuilder> {
  _$TwinProcessIn? _$v;

  MapBuilder<String, JsonObject?>? _attributes;
  MapBuilder<String, JsonObject?> get attributes =>
      _$this._attributes ??= MapBuilder<String, JsonObject?>();
  set attributes(MapBuilder<String, JsonObject?>? attributes) =>
      _$this._attributes = attributes;

  String? _command;
  String? get command => _$this._command;
  set command(String? command) => _$this._command = command;

  String? _device;
  String? get device => _$this._device;
  set device(String? device) => _$this._device = device;

  String? _name;
  String? get name => _$this._name;
  set name(String? name) => _$this._name = name;

  int? _pid;
  int? get pid => _$this._pid;
  set pid(int? pid) => _$this._pid = pid;

  DateTime? _startedAt;
  DateTime? get startedAt => _$this._startedAt;
  set startedAt(DateTime? startedAt) => _$this._startedAt = startedAt;

  String? _user;
  String? get user => _$this._user;
  set user(String? user) => _$this._user = user;

  TwinProcessInBuilder() {
    TwinProcessIn._defaults(this);
  }

  TwinProcessInBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _attributes = $v.attributes?.toBuilder();
      _command = $v.command;
      _device = $v.device;
      _name = $v.name;
      _pid = $v.pid;
      _startedAt = $v.startedAt;
      _user = $v.user;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TwinProcessIn other) {
    _$v = other as _$TwinProcessIn;
  }

  @override
  void update(void Function(TwinProcessInBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TwinProcessIn build() => _build();

  _$TwinProcessIn _build() {
    _$TwinProcessIn _$result;
    try {
      _$result = _$v ??
          _$TwinProcessIn._(
            attributes: _attributes?.build(),
            command: command,
            device: BuiltValueNullFieldError.checkNotNull(
                device, r'TwinProcessIn', 'device'),
            name: BuiltValueNullFieldError.checkNotNull(
                name, r'TwinProcessIn', 'name'),
            pid: BuiltValueNullFieldError.checkNotNull(
                pid, r'TwinProcessIn', 'pid'),
            startedAt: startedAt,
            user: user,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'attributes';
        _attributes?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'TwinProcessIn', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
