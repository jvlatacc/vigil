// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'twin_edge_out.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const TwinEdgeOutKindEnum _$twinEdgeOutKindEnum_runs =
    const TwinEdgeOutKindEnum._('runs');
const TwinEdgeOutKindEnum _$twinEdgeOutKindEnum_binds =
    const TwinEdgeOutKindEnum._('binds');
const TwinEdgeOutKindEnum _$twinEdgeOutKindEnum_talksTo =
    const TwinEdgeOutKindEnum._('talksTo');

TwinEdgeOutKindEnum _$twinEdgeOutKindEnumValueOf(String name) {
  switch (name) {
    case 'runs':
      return _$twinEdgeOutKindEnum_runs;
    case 'binds':
      return _$twinEdgeOutKindEnum_binds;
    case 'talksTo':
      return _$twinEdgeOutKindEnum_talksTo;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<TwinEdgeOutKindEnum> _$twinEdgeOutKindEnumValues =
    BuiltSet<TwinEdgeOutKindEnum>(const <TwinEdgeOutKindEnum>[
  _$twinEdgeOutKindEnum_runs,
  _$twinEdgeOutKindEnum_binds,
  _$twinEdgeOutKindEnum_talksTo,
]);

Serializer<TwinEdgeOutKindEnum> _$twinEdgeOutKindEnumSerializer =
    _$TwinEdgeOutKindEnumSerializer();

class _$TwinEdgeOutKindEnumSerializer
    implements PrimitiveSerializer<TwinEdgeOutKindEnum> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'runs': 'runs',
    'binds': 'binds',
    'talksTo': 'talks-to',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'runs': 'runs',
    'binds': 'binds',
    'talks-to': 'talksTo',
  };

  @override
  final Iterable<Type> types = const <Type>[TwinEdgeOutKindEnum];
  @override
  final String wireName = 'TwinEdgeOutKindEnum';

  @override
  Object serialize(Serializers serializers, TwinEdgeOutKindEnum object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  TwinEdgeOutKindEnum deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      TwinEdgeOutKindEnum.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

class _$TwinEdgeOut extends TwinEdgeOut {
  @override
  final bool? heuristic;
  @override
  final String id;
  @override
  final TwinEdgeOutKindEnum kind;
  @override
  final String source_;
  @override
  final String target;

  factory _$TwinEdgeOut([void Function(TwinEdgeOutBuilder)? updates]) =>
      (TwinEdgeOutBuilder()..update(updates))._build();

  _$TwinEdgeOut._(
      {this.heuristic,
      required this.id,
      required this.kind,
      required this.source_,
      required this.target})
      : super._();
  @override
  TwinEdgeOut rebuild(void Function(TwinEdgeOutBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TwinEdgeOutBuilder toBuilder() => TwinEdgeOutBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TwinEdgeOut &&
        heuristic == other.heuristic &&
        id == other.id &&
        kind == other.kind &&
        source_ == other.source_ &&
        target == other.target;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, heuristic.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, kind.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jc(_$hash, target.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TwinEdgeOut')
          ..add('heuristic', heuristic)
          ..add('id', id)
          ..add('kind', kind)
          ..add('source_', source_)
          ..add('target', target))
        .toString();
  }
}

class TwinEdgeOutBuilder implements Builder<TwinEdgeOut, TwinEdgeOutBuilder> {
  _$TwinEdgeOut? _$v;

  bool? _heuristic;
  bool? get heuristic => _$this._heuristic;
  set heuristic(bool? heuristic) => _$this._heuristic = heuristic;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  TwinEdgeOutKindEnum? _kind;
  TwinEdgeOutKindEnum? get kind => _$this._kind;
  set kind(TwinEdgeOutKindEnum? kind) => _$this._kind = kind;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  String? _target;
  String? get target => _$this._target;
  set target(String? target) => _$this._target = target;

  TwinEdgeOutBuilder() {
    TwinEdgeOut._defaults(this);
  }

  TwinEdgeOutBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _heuristic = $v.heuristic;
      _id = $v.id;
      _kind = $v.kind;
      _source_ = $v.source_;
      _target = $v.target;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TwinEdgeOut other) {
    _$v = other as _$TwinEdgeOut;
  }

  @override
  void update(void Function(TwinEdgeOutBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TwinEdgeOut build() => _build();

  _$TwinEdgeOut _build() {
    final _$result = _$v ??
        _$TwinEdgeOut._(
          heuristic: heuristic,
          id: BuiltValueNullFieldError.checkNotNull(id, r'TwinEdgeOut', 'id'),
          kind: BuiltValueNullFieldError.checkNotNull(
              kind, r'TwinEdgeOut', 'kind'),
          source_: BuiltValueNullFieldError.checkNotNull(
              source_, r'TwinEdgeOut', 'source_'),
          target: BuiltValueNullFieldError.checkNotNull(
              target, r'TwinEdgeOut', 'target'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
