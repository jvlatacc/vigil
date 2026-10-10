//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'finding_update_response.g.dart';

/// FindingUpdateResponse
///
/// Properties:
/// * [finding] 
/// * [success] 
/// * [updatedFields] 
@BuiltValue()
abstract class FindingUpdateResponse implements Built<FindingUpdateResponse, FindingUpdateResponseBuilder> {
  @BuiltValueField(wireName: r'finding')
  BuiltMap<String, JsonObject?>? get finding;

  @BuiltValueField(wireName: r'success')
  bool get success;

  @BuiltValueField(wireName: r'updated_fields')
  BuiltList<String>? get updatedFields;

  FindingUpdateResponse._();

  factory FindingUpdateResponse([void updates(FindingUpdateResponseBuilder b)]) = _$FindingUpdateResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(FindingUpdateResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<FindingUpdateResponse> get serializer => _$FindingUpdateResponseSerializer();
}

class _$FindingUpdateResponseSerializer implements PrimitiveSerializer<FindingUpdateResponse> {
  @override
  final Iterable<Type> types = const [FindingUpdateResponse, _$FindingUpdateResponse];

  @override
  final String wireName = r'FindingUpdateResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    FindingUpdateResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.finding != null) {
      yield r'finding';
      yield serializers.serialize(
        object.finding,
        specifiedType: const FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
      );
    }
    yield r'success';
    yield serializers.serialize(
      object.success,
      specifiedType: const FullType(bool),
    );
    if (object.updatedFields != null) {
      yield r'updated_fields';
      yield serializers.serialize(
        object.updatedFields,
        specifiedType: const FullType(BuiltList, [FullType(String)]),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    FindingUpdateResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required FindingUpdateResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'finding':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltMap, [FullType(String), FullType.nullable(JsonObject)]),
          ) as BuiltMap<String, JsonObject?>?;
          if (valueDes == null) continue;
          result.finding.replace(valueDes);
          break;
        case r'success':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.success = valueDes;
          break;
        case r'updated_fields':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.updatedFields.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  FindingUpdateResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = FindingUpdateResponseBuilder();
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


