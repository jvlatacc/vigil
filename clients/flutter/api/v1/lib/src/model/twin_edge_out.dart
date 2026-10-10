//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'twin_edge_out.g.dart';

/// One derived relationship between two graph nodes.  ``source``/``target`` are the entity ids the payload's own lists use, so a client can join edges to nodes without a second lookup. ``runs`` and ``binds`` are structural facts; ``talks-to`` is the v1 heuristic (a connection's ``remote_ip`` matching another device's last-known ``ip_address``) and carries ``heuristic=True`` — reused or overlapping addresses can fabricate one.
///
/// Properties:
/// * [heuristic] 
/// * [id] 
/// * [kind] 
/// * [source_] 
/// * [target] 
@BuiltValue()
abstract class TwinEdgeOut implements Built<TwinEdgeOut, TwinEdgeOutBuilder> {
  @BuiltValueField(wireName: r'heuristic')
  bool? get heuristic;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'kind')
  TwinEdgeOutKindEnum get kind;
  // enum kindEnum {  runs,  binds,  talks-to,  };

  @BuiltValueField(wireName: r'source')
  String get source_;

  @BuiltValueField(wireName: r'target')
  String get target;

  TwinEdgeOut._();

  factory TwinEdgeOut([void updates(TwinEdgeOutBuilder b)]) = _$TwinEdgeOut;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(TwinEdgeOutBuilder b) => b
      ..heuristic = false;

  @BuiltValueSerializer(custom: true)
  static Serializer<TwinEdgeOut> get serializer => _$TwinEdgeOutSerializer();
}

class _$TwinEdgeOutSerializer implements PrimitiveSerializer<TwinEdgeOut> {
  @override
  final Iterable<Type> types = const [TwinEdgeOut, _$TwinEdgeOut];

  @override
  final String wireName = r'TwinEdgeOut';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    TwinEdgeOut object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.heuristic != null) {
      yield r'heuristic';
      yield serializers.serialize(
        object.heuristic,
        specifiedType: const FullType(bool),
      );
    }
    yield r'id';
    yield serializers.serialize(
      object.id,
      specifiedType: const FullType(String),
    );
    yield r'kind';
    yield serializers.serialize(
      object.kind,
      specifiedType: const FullType(TwinEdgeOutKindEnum),
    );
    yield r'source';
    yield serializers.serialize(
      object.source_,
      specifiedType: const FullType(String),
    );
    yield r'target';
    yield serializers.serialize(
      object.target,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    TwinEdgeOut object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required TwinEdgeOutBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'heuristic':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.heuristic = valueDes;
          break;
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.id = valueDes;
          break;
        case r'kind':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(TwinEdgeOutKindEnum),
          ) as TwinEdgeOutKindEnum;
          result.kind = valueDes;
          break;
        case r'source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.source_ = valueDes;
          break;
        case r'target':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.target = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  TwinEdgeOut deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = TwinEdgeOutBuilder();
    final serializedList = (serialized as Iterable<Object?>).toList();
    final unhandled = <Object?>[];
    _deserializeProperties(
      serializers,
      serialized,
      specifiedType: specifiedType,
      serializedList: serializedList,
      unhandled: unhandled,
      result: result,
    );
    return result.build();
  }
}


class TwinEdgeOutKindEnum extends EnumClass {

  @BuiltValueEnumConst(wireName: r'runs')
  static const TwinEdgeOutKindEnum runs = _$twinEdgeOutKindEnum_runs;
  @BuiltValueEnumConst(wireName: r'binds')
  static const TwinEdgeOutKindEnum binds = _$twinEdgeOutKindEnum_binds;
  @BuiltValueEnumConst(wireName: r'talks-to')
  static const TwinEdgeOutKindEnum talksTo = _$twinEdgeOutKindEnum_talksTo;

  static Serializer<TwinEdgeOutKindEnum> get serializer => _$twinEdgeOutKindEnumSerializer;

  const TwinEdgeOutKindEnum._(String name): super(name);

  static BuiltSet<TwinEdgeOutKindEnum> get values => _$twinEdgeOutKindEnumValues;
  static TwinEdgeOutKindEnum valueOf(String name) => _$twinEdgeOutKindEnumValueOf(name);
}

