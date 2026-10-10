// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'twin_process_out.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$TwinProcessOut extends TwinProcessOut {
  @override
  final BuiltMap<String, JsonObject?>? attributes;
  @override
  final String? command;
  @override
  final JsonObject? deviceId;
  @override
  final String firstSeen;
  @override
  final JsonObject? id;
  @override
  final String lastSeen;
  @override
  final String name;
  @override
  final int pid;
  @override
  final String source_;
  @override
  final String? startedAt;
  @override
  final String? user;

  factory _$TwinProcessOut([void Function(TwinProcessOutBuilder)? updates]) =>
      (TwinProcessOutBuilder()..update(updates))._build();

  _$TwinProcessOut._(
      {this.attributes,
      this.command,
      this.deviceId,
      required this.firstSeen,
      this.id,
      required this.lastSeen,
      required this.name,
      required this.pid,
      required this.source_,
      this.startedAt,
      this.user})
      : super._();
  @override
  TwinProcessOut rebuild(void Function(TwinProcessOutBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TwinProcessOutBuilder toBuilder() => TwinProcessOutBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TwinProcessOut &&
        attributes == other.attributes &&
        command == other.command &&
        deviceId == other.deviceId &&
        firstSeen == other.firstSeen &&
        id == other.id &&
        lastSeen == other.lastSeen &&
        name == other.name &&
        pid == other.pid &&
        source_ == other.source_ &&
        startedAt == other.startedAt &&
        user == other.user;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, attributes.hashCode);
    _$hash = $jc(_$hash, command.hashCode);
    _$hash = $jc(_$hash, deviceId.hashCode);
    _$hash = $jc(_$hash, firstSeen.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, lastSeen.hashCode);
    _$hash = $jc(_$hash, name.hashCode);
    _$hash = $jc(_$hash, pid.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jc(_$hash, startedAt.hashCode);
    _$hash = $jc(_$hash, user.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TwinProcessOut')
          ..add('attributes', attributes)
          ..add('command', command)
          ..add('deviceId', deviceId)
          ..add('firstSeen', firstSeen)
          ..add('id', id)
          ..add('lastSeen', lastSeen)
          ..add('name', name)
          ..add('pid', pid)
          ..add('source_', source_)
          ..add('startedAt', startedAt)
          ..add('user', user))
        .toString();
  }
}

class TwinProcessOutBuilder
    implements Builder<TwinProcessOut, TwinProcessOutBuilder> {
  _$TwinProcessOut? _$v;

  MapBuilder<String, JsonObject?>? _attributes;
  MapBuilder<String, JsonObject?> get attributes =>
      _$this._attributes ??= MapBuilder<String, JsonObject?>();
  set attributes(MapBuilder<String, JsonObject?>? attributes) =>
      _$this._attributes = attributes;

  String? _command;
  String? get command => _$this._command;
  set command(String? command) => _$this._command = command;

  JsonObject? _deviceId;
  JsonObject? get deviceId => _$this._deviceId;
  set deviceId(JsonObject? deviceId) => _$this._deviceId = deviceId;

  String? _firstSeen;
  String? get firstSeen => _$this._firstSeen;
  set firstSeen(String? firstSeen) => _$this._firstSeen = firstSeen;

  JsonObject? _id;
  JsonObject? get id => _$this._id;
  set id(JsonObject? id) => _$this._id = id;

  String? _lastSeen;
  String? get lastSeen => _$this._lastSeen;
  set lastSeen(String? lastSeen) => _$this._lastSeen = lastSeen;

  String? _name;
  String? get name => _$this._name;
  set name(String? name) => _$this._name = name;

  int? _pid;
  int? get pid => _$this._pid;
  set pid(int? pid) => _$this._pid = pid;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  String? _startedAt;
  String? get startedAt => _$this._startedAt;
  set startedAt(String? startedAt) => _$this._startedAt = startedAt;

  String? _user;
  String? get user => _$this._user;
  set user(String? user) => _$this._user = user;

  TwinProcessOutBuilder() {
    TwinProcessOut._defaults(this);
  }

  TwinProcessOutBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _attributes = $v.attributes?.toBuilder();
      _command = $v.command;
      _deviceId = $v.deviceId;
      _firstSeen = $v.firstSeen;
      _id = $v.id;
      _lastSeen = $v.lastSeen;
      _name = $v.name;
      _pid = $v.pid;
      _source_ = $v.source_;
      _startedAt = $v.startedAt;
      _user = $v.user;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TwinProcessOut other) {
    _$v = other as _$TwinProcessOut;
  }

  @override
  void update(void Function(TwinProcessOutBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TwinProcessOut build() => _build();

  _$TwinProcessOut _build() {
    _$TwinProcessOut _$result;
    try {
      _$result = _$v ??
          _$TwinProcessOut._(
            attributes: _attributes?.build(),
            command: command,
            deviceId: deviceId,
            firstSeen: BuiltValueNullFieldError.checkNotNull(
                firstSeen, r'TwinProcessOut', 'firstSeen'),
            id: id,
            lastSeen: BuiltValueNullFieldError.checkNotNull(
                lastSeen, r'TwinProcessOut', 'lastSeen'),
            name: BuiltValueNullFieldError.checkNotNull(
                name, r'TwinProcessOut', 'name'),
            pid: BuiltValueNullFieldError.checkNotNull(
                pid, r'TwinProcessOut', 'pid'),
            source_: BuiltValueNullFieldError.checkNotNull(
                source_, r'TwinProcessOut', 'source_'),
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
            r'TwinProcessOut', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
