//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'twin_ingest_result.g.dart';

/// Counts of observations the batch carried, per entity class.  These echo the batch, not the database: idempotency means a re-post returns the same numbers while the row counts stay put.
///
/// Properties:
/// * [connections] 
/// * [devices] 
/// * [processes] 
/// * [source_] 
@BuiltValue()
abstract class TwinIngestResult implements Built<TwinIngestResult, TwinIngestResultBuilder> {
  @BuiltValueField(wireName: r'connections')
  int get connections;

  @BuiltValueField(wireName: r'devices')
  int get devices;

  @BuiltValueField(wireName: r'processes')
  int get processes;

  @BuiltValueField(wireName: r'source')
  String get source_;

  TwinIngestResult._();

  factory TwinIngestResult([void updates(TwinIngestResultBuilder b)]) = _$TwinIngestResult;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(TwinIngestResultBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<TwinIngestResult> get serializer => _$TwinIngestResultSerializer();
}

class _$TwinIngestResultSerializer implements PrimitiveSerializer<TwinIngestResult> {
  @override
  final Iterable<Type> types = const [TwinIngestResult, _$TwinIngestResult];

  @override
  final String wireName = r'TwinIngestResult';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    TwinIngestResult object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'connections';
    yield serializers.serialize(
      object.connections,
      specifiedType: const FullType(int),
    );
    yield r'devices';
    yield serializers.serialize(
      object.devices,
      specifiedType: const FullType(int),
    );
    yield r'processes';
    yield serializers.serialize(
      object.processes,
      specifiedType: const FullType(int),
    );
    yield r'source';
    yield serializers.serialize(
      object.source_,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    TwinIngestResult object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required TwinIngestResultBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'connections':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.connections = valueDes;
          break;
        case r'devices':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.devices = valueDes;
          break;
        case r'processes':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.processes = valueDes;
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
  TwinIngestResult deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = TwinIngestResultBuilder();
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


