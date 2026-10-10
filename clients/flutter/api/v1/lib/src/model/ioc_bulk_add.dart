//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'ioc_bulk_add.g.dart';

/// Bulk add IOCs.
///
/// Properties:
/// * [iocs] 
@BuiltValue()
abstract class IOCBulkAdd implements Built<IOCBulkAdd, IOCBulkAddBuilder> {
  @BuiltValueField(wireName: r'iocs')
  BuiltList<BuiltMap<String, JsonObject?>> get iocs;

  IOCBulkAdd._();

  factory IOCBulkAdd([void updates(IOCBulkAddBuilder b)]) = _$IOCBulkAdd;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(IOCBulkAddBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<IOCBulkAdd> get serializer => _$IOCBulkAddSerializer();
}

class _$IOCBulkAddSerializer implements PrimitiveSerializer<IOCBulkAdd> {
  @override
  final Iterable<Type> types = const [IOCBulkAdd, _$IOCBulkAdd];

  @override
  final String wireName = r'IOCBulkAdd';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    IOCBulkAdd object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'iocs';
    yield serializers.serialize(
      object.iocs,
      specifiedType: const FullType(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    IOCBulkAdd object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required IOCBulkAddBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'iocs':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
          ) as BuiltList<BuiltMap<String, JsonObject?>>;
          result.iocs.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  IOCBulkAdd deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = IOCBulkAddBuilder();
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


