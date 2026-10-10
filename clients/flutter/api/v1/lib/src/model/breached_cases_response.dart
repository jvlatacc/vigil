//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'breached_cases_response.g.dart';

/// BreachedCasesResponse
///
/// Properties:
/// * [breachedCases] 
@BuiltValue()
abstract class BreachedCasesResponse implements Built<BreachedCasesResponse, BreachedCasesResponseBuilder> {
  @BuiltValueField(wireName: r'breached_cases')
  BuiltList<BuiltMap<String, JsonObject?>>? get breachedCases;

  BreachedCasesResponse._();

  factory BreachedCasesResponse([void updates(BreachedCasesResponseBuilder b)]) = _$BreachedCasesResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(BreachedCasesResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<BreachedCasesResponse> get serializer => _$BreachedCasesResponseSerializer();
}

class _$BreachedCasesResponseSerializer implements PrimitiveSerializer<BreachedCasesResponse> {
  @override
  final Iterable<Type> types = const [BreachedCasesResponse, _$BreachedCasesResponse];

  @override
  final String wireName = r'BreachedCasesResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    BreachedCasesResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.breachedCases != null) {
      yield r'breached_cases';
      yield serializers.serialize(
        object.breachedCases,
        specifiedType: const FullType(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    BreachedCasesResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object, specifiedType: specifiedType).toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required BreachedCasesResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'breached_cases':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(BuiltList, [FullType(BuiltMap, [FullType(String), FullType.nullable(JsonObject)])]),
          ) as BuiltList<BuiltMap<String, JsonObject?>>?;
          if (valueDes == null) continue;
          result.breachedCases.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  BreachedCasesResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = BreachedCasesResponseBuilder();
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


