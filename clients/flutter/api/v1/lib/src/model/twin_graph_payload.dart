//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:vigil_api_v1/src/model/twin_process_out.dart';
import 'package:built_collection/built_collection.dart';
import 'package:vigil_api_v1/src/model/twin_edge_out.dart';
import 'package:vigil_api_v1/src/model/twin_connection_out.dart';
import 'package:vigil_api_v1/src/model/twin_device_out.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'twin_graph_payload.g.dart';

/// The whole twin in one payload; every node carries its entity attributes.  The three entity lists are the wire shape the console screen consumes; ``edges`` is the same derivation server-side (``runs`` device→process, ``binds`` process→connection, heuristic ``talks-to`` device→device) for callers that would rather not re-derive it.
///
/// Properties:
/// * [connections] 
/// * [devices] 
/// * [edges] 
/// * [generatedAt] 
/// * [processes] 
@BuiltValue()
abstract class TwinGraphPayload implements Built<TwinGraphPayload, TwinGraphPayloadBuilder> {
  @BuiltValueField(wireName: r'connections')
  BuiltList<TwinConnectionOut>? get connections;

  @BuiltValueField(wireName: r'devices')
  BuiltList<TwinDeviceOut>? get devices;

  @BuiltValueField(wireName: r'edges')
  BuiltList<TwinEdgeOut>? get edges;

  @BuiltValueField(wireName: r'generated_at')
  String get generatedAt;

  @BuiltValueField(wireName: r'processes')
  BuiltList<TwinProcessOut>? get processes;

  TwinGraphPayload._();

  factory TwinGraphPayload([void updates(TwinGraphPayloadBuilder b)]) = _$TwinGraphPayload;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(TwinGraphPayloadBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<TwinGraphPayload> get serializer => _$TwinGraphPayloadSerializer();
}

class _$TwinGraphPayloadSerializer implements PrimitiveSerializer<TwinGraphPayload> {
  @override
  final Iterable<Type> types = const [TwinGraphPayload, _$TwinGraphPayload];

  @override
  final String wireName = r'TwinGraphPayload';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    TwinGraphPayload object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.connections != null) {
      yield r'connections';
      yield serializers.serialize(
        object.connections,
        specifiedType: const FullType(BuiltList, [FullType(TwinConnectionOut)]),
      );
    }
    if (object.devices != null) {
      yield r'devices';
      yield serializers.serialize(
        object.devices,
        specifiedType: const FullType(BuiltList, [FullType(TwinDeviceOut)]),
      );
    }
    if (object.edges != null) {
      yield r'edges';
      yield serializers.serialize(
        object.edges,
        specifiedType: const FullType(BuiltList, [FullType(TwinEdgeOut)]),
      );
    }
    yield r'generated_at';
    yield serializers.serialize(
      object.generatedAt,
      specifiedType: const FullType(String),
    );
    if (object.processes != null) {
      yield r'processes';
      yield serializers.serialize(
        object.processes,
        specifiedType: const FullType(BuiltList, [FullType(TwinProcessOut)]),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    TwinGraphPayload object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required TwinGraphPayloadBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'connections':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(TwinConnectionOut)]),
          ) as BuiltList<TwinConnectionOut>?;
          if (valueDes == null) continue;
          result.connections.replace(valueDes);
          break;
        case r'devices':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(TwinDeviceOut)]),
          ) as BuiltList<TwinDeviceOut>?;
          if (valueDes == null) continue;
          result.devices.replace(valueDes);
          break;
        case r'edges':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(TwinEdgeOut)]),
          ) as BuiltList<TwinEdgeOut>?;
          if (valueDes == null) continue;
          result.edges.replace(valueDes);
          break;
        case r'generated_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.generatedAt = valueDes;
          break;
        case r'processes':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(TwinProcessOut)]),
          ) as BuiltList<TwinProcessOut>?;
          if (valueDes == null) continue;
          result.processes.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  TwinGraphPayload deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = TwinGraphPayloadBuilder();
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


