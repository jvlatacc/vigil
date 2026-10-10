//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:vigil_api_v1/src/model/twin_connection_in.dart';
import 'package:vigil_api_v1/src/model/twin_process_in.dart';
import 'package:built_collection/built_collection.dart';
import 'package:vigil_api_v1/src/model/twin_device_in.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'twin_ingest_batch.g.dart';

/// One observation envelope from one feed: the source and what it saw.  Re-posting a batch is safe and meaningful — it is how a feed says \"still here\": row counts stay stable and every re-observed row's ``last_seen`` moves forward. A feed aggregating several vendors posts one batch per source.
///
/// Properties:
/// * [connections] 
/// * [devices] 
/// * [processes] 
/// * [source_] 
@BuiltValue()
abstract class TwinIngestBatch implements Built<TwinIngestBatch, TwinIngestBatchBuilder> {
  @BuiltValueField(wireName: r'connections')
  BuiltList<TwinConnectionIn>? get connections;

  @BuiltValueField(wireName: r'devices')
  BuiltList<TwinDeviceIn>? get devices;

  @BuiltValueField(wireName: r'processes')
  BuiltList<TwinProcessIn>? get processes;

  @BuiltValueField(wireName: r'source')
  String get source_;

  TwinIngestBatch._();

  factory TwinIngestBatch([void updates(TwinIngestBatchBuilder b)]) = _$TwinIngestBatch;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(TwinIngestBatchBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<TwinIngestBatch> get serializer => _$TwinIngestBatchSerializer();
}

class _$TwinIngestBatchSerializer implements PrimitiveSerializer<TwinIngestBatch> {
  @override
  final Iterable<Type> types = const [TwinIngestBatch, _$TwinIngestBatch];

  @override
  final String wireName = r'TwinIngestBatch';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    TwinIngestBatch object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.connections != null) {
      yield r'connections';
      yield serializers.serialize(
        object.connections,
        specifiedType: const FullType(BuiltList, [FullType(TwinConnectionIn)]),
      );
    }
    if (object.devices != null) {
      yield r'devices';
      yield serializers.serialize(
        object.devices,
        specifiedType: const FullType(BuiltList, [FullType(TwinDeviceIn)]),
      );
    }
    if (object.processes != null) {
      yield r'processes';
      yield serializers.serialize(
        object.processes,
        specifiedType: const FullType(BuiltList, [FullType(TwinProcessIn)]),
      );
    }
    yield r'source';
    yield serializers.serialize(
      object.source_,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    TwinIngestBatch object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required TwinIngestBatchBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'connections':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(TwinConnectionIn)]),
          ) as BuiltList<TwinConnectionIn>?;
          if (valueDes == null) continue;
          result.connections.replace(valueDes);
          break;
        case r'devices':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(TwinDeviceIn)]),
          ) as BuiltList<TwinDeviceIn>?;
          if (valueDes == null) continue;
          result.devices.replace(valueDes);
          break;
        case r'processes':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(TwinProcessIn)]),
          ) as BuiltList<TwinProcessIn>?;
          if (valueDes == null) continue;
          result.processes.replace(valueDes);
          break;
        case r'source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.source_ = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  TwinIngestBatch deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = TwinIngestBatchBuilder();
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


